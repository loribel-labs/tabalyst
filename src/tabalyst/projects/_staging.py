"""Private staged loader (7.storage-d1); it cannot publish or open a project.

The caller supplies a fresh, writer-owned staging directory. It stays private
on success and failure. No project.json, index or generations rename occurs.
d2 must supply locking, durability, publication and recovery around this.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb

from tabalyst.progress import ProgressCallback
from tabalyst.projects._codec import (
    DatabaseCompatibilityError,
    DatabaseValidationError,
    bigint,
    encode_value,
    json_text,
    path_text,
)
from tabalyst.projects._query_budget import apply_spill_limit
from tabalyst.projects._schema import (
    DUCKDB_VERSION,
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    INGESTION,
    LOADER_VERSION,
    RECORD_SEMANTICS_VERSION,
    SCHEMA,
    STORAGE_COMPATIBILITY,
)
from tabalyst.projects._validation import (
    record_flags,
    validate_database,
    validate_staging,
)
from tabalyst.projects.identity import is_project_id
from tabalyst.scan_service import scan_document
from tabalyst.scanner import ScanConfig, ScanResult, scan
from tabalyst.scanner.config import (
    config_sha256,
    resolve_config_defaults,
    resolve_scan_config,
)
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import ROOT, Column
from tabalyst.scanner.records import (
    PathTokens,
    RecordContext,
    TableLayout,
    record_digest,
)

# Both rows and encoded payload bytes are bounded. A single observation may
# exceed the byte threshold: flush it alone, as the Scan reader already does.
BATCH_ROWS = 2048
BATCH_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class StagedScan:
    result: ScanResult
    scan_path: Path
    database_path: Path
    scan_sha256: str
    database_sha256: str


class _Buffer:
    def __init__(self, connection, table: str, types: tuple[str, ...]):
        self.connection = connection
        self.query = f"INSERT INTO {table} SELECT " + ",".join(
            f"unnest(?::{kind}[])" for kind in types
        )
        self.columns = [[] for _ in types]
        self.rows = self.bytes = 0

    def append(self, values: tuple) -> None:
        for column, value in zip(self.columns, values, strict=True):
            column.append(value)
            if isinstance(value, str):
                self.bytes += len(value.encode("utf-8"))
            elif isinstance(value, bytes):
                self.bytes += len(value)
            else:
                self.bytes += 8
        self.rows += 1
        if self.rows >= BATCH_ROWS or self.bytes >= BATCH_BYTES:
            self.flush()

    def flush(self) -> None:
        if self.rows:
            self.connection.execute(self.query, self.columns)
            self.columns = [[] for _ in self.columns]
            self.rows = self.bytes = 0


class _Sink:
    def __init__(self, connection, config: ScanConfig, *, csv: bool):
        self.context = RecordContext(
            config,
            StringClassifier(
                config.values.null_markers, config.values.null_markers_case_sensitive
            ),
        )
        self.csv = csv
        self.layouts: dict[str, TableLayout] = {}
        self.paths: dict[str, PathTokens] = {}
        self.records = _Buffer(
            connection,
            "ingest_records",
            (
                "VARCHAR",
                "BIGINT",
                "VARCHAR",
                "BIGINT",
                "BIGINT",
                "BOOLEAN",
                "BOOLEAN",
                "BLOB",
            ),
        )
        self.observations = _Buffer(
            connection,
            "ingest_observations",
            ("VARCHAR", "BIGINT", "BIGINT", "VARCHAR", "VARCHAR", "VARCHAR", "BIGINT"),
        )

    def _record(self, record: Record) -> None:
        index = bigint(record.index, minimum=1)
        if self.csv and record.dataset not in self.layouts:
            declared = tuple(o.path for o in record.observations[1:])
            expected = tuple((Column(i),) for i in range(1, len(declared) + 1))
            if (
                declared != expected
                or not record.observations
                or record.observations[0].path != ROOT
            ):
                raise DatabaseValidationError("Invalid first CSV record layout")
            self.layouts[record.dataset] = TableLayout(declared)
        missing, empty = record_flags(record, self.context)
        digest = None
        if self.context.duplicates:
            paths = self.paths.setdefault(record.dataset, PathTokens())
            digest = record_digest(record, self.layouts.get(record.dataset), paths)
        self.records.append(
            (
                record.dataset,
                index,
                json_text(record.location.to_dict()),
                bigint(record.depth_truncated),
                bigint(len(record.observations)),
                missing,
                empty,
                digest,
            )
        )

    def __call__(self, record: Record) -> None:
        self._record(record)
        index = record.index
        for ordinal, observation in enumerate(record.observations, 1):
            text, length = encode_value(observation)
            self.observations.append(
                (
                    record.dataset,
                    index,
                    bigint(ordinal, minimum=1),
                    path_text(observation.path),
                    observation.type,
                    text,
                    length,
                )
            )

    def finalize(self, connection, result: ScanResult) -> None:
        self.records.flush()
        self.observations.flush()
        if result.source.csv is not None:
            expected = (
                ROOT,
                *((Column(i),) for i in range(1, len(result.source.csv.header) + 1)),
            )
            for layout in self.layouts.values():
                if layout.paths != expected:
                    raise DatabaseValidationError(
                        "CSV layout differs from final header"
                    )
        for ordinal, dataset in enumerate(result.datasets, 1):
            connection.execute(
                "INSERT INTO meta.datasets VALUES (?,?,?,?,?)",
                (
                    dataset.id,
                    ordinal,
                    dataset.kind,
                    None
                    if dataset.collection_path is None
                    else json_text([p.model_dump() for p in dataset.collection_path]),
                    bigint(dataset.record_count),
                ),
            )
            for field_ordinal, field in enumerate(dataset.fields, 1):
                connection.execute(
                    "INSERT INTO meta.fields VALUES (?,?,?,?,?,?,?,?)",
                    (
                        dataset.id,
                        field.id,
                        field_ordinal,
                        json_text([p.model_dump() for p in field.path]),
                        field.name,
                        field.display,
                        field.parent,
                        field.collection,
                    ),
                )
        connection.execute("INSERT INTO data.records SELECT * FROM ingest_records")
        self.finalize_observations(connection, result)
        connection.execute(
            "INSERT INTO data.listing_records "
            "SELECT dataset_id,'records.with_missing',record_index "
            "FROM data.records WHERE with_missing"
        )
        connection.execute(
            "INSERT INTO data.listing_records "
            "SELECT dataset_id,'records.empty',record_index FROM data.records WHERE is_empty"
        )
        if self.context.duplicates:
            connection.execute(
                "INSERT INTO data.listing_records "
                "SELECT dataset_id,'records.duplicates',record_index FROM data.records "
                "QUALIFY record_index > min(record_index) OVER "
                "(PARTITION BY dataset_id,duplicate_key)"
            )
        for dataset in result.datasets:
            for listing in (
                "records.with_missing",
                "records.empty",
                "records.duplicates",
            ):
                enabled = listing != "records.duplicates" or self.context.duplicates
                count = connection.execute(
                    "SELECT count(*) FROM data.listing_records WHERE dataset_id=? AND listing_id=?",
                    [dataset.id, listing],
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO meta.listings VALUES (?,?,?,?,?,?)",
                    (
                        dataset.id,
                        listing,
                        "complete" if enabled else "disabled",
                        count if enabled else None,
                        None if enabled else "duplicates_disabled",
                        RECORD_SEMANTICS_VERSION,
                    ),
                )

    def finalize_observations(self, connection, result):
        connection.execute(
            "INSERT INTO data.observations SELECT o.dataset_id,o.record_index, "
            "o.observation_index,o.path_json,f.field_id,o.native_type,o.raw_text, "
            "o.array_length FROM ingest_observations o LEFT JOIN meta.fields f "
            "ON o.dataset_id=f.dataset_id AND o.path_json=f.path_json"
        )
        connection.execute("DROP TABLE ingest_observations; DROP TABLE ingest_records")


def _source_stamp(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_staging(
    source: str | Path,
    staging_dir: str | Path,
    *,
    project_id: str,
    generation_id: str,
    workspace_id: str = "local",
    config: ScanConfig | None = None,
    config_paths=(),
    delimiter: str | None = None,
    encoding: str | None = None,
    collections=None,
    workers: int | None = None,
    memory_limit: str = "256MiB",
    spill_limit: str = "1GiB",
    value_limit: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> StagedScan:
    """Build only an unpublished pair in a NEW private staging directory.

    Effective settings or config layers are accepted, never both. Failures
    preserve private staging evidence for d2's ownership-aware recovery.
    No value-query/public exposure API is provided by this module.
    """
    if duckdb.__version__ != DUCKDB_VERSION:
        raise DatabaseCompatibilityError(f"Expected DuckDB {DUCKDB_VERSION}")
    if not is_project_id(project_id) or not is_project_id(generation_id):
        raise DatabaseValidationError("Project/generation ids must be ULIDs")
    if workspace_id != "local":
        raise DatabaseValidationError("Only local staging is supported")
    if config is not None and (
        config_paths
        or delimiter is not None
        or encoding is not None
        or collections is not None
    ):
        raise ValueError("Pass effective config or config layers, not both")
    effective = (
        config.model_copy(deep=True)
        if config is not None
        else resolve_scan_config(
            config_paths,
            delimiter=delimiter,
            encoding=encoding,
            collections=collections,
        )
    )
    path = Path(source)
    before = _source_stamp(path)
    stage = Path(staging_dir)
    stage.mkdir(mode=0o700)  # exclusive reservation, never reuse an existing build
    database_path = stage / "project.duckdb"
    scan_path = stage / "scan.json"
    spill_directory = str(stage / "spill")
    # The exclusive owner-only directory protects creation too. Windows
    # inherits the caller's local directory ACL.
    connection = duckdb.connect(
        str(database_path),
        config={
            "storage_compatibility_version": STORAGE_COMPATIBILITY,
            "memory_limit": memory_limit,
            "threads": 1,
            "preserve_insertion_order": False,
            "temp_directory": spill_directory,
            "max_temp_directory_size": spill_limit,
        },
    )
    try:
        database_path.chmod(0o600)
        if not apply_spill_limit(connection, spill_limit):
            spill_directory = ""
        connection.execute("SET enable_external_access=false")
        if value_limit is None:
            connection.execute("BEGIN TRANSACTION")
        connection.execute(SCHEMA)
        connection.execute(INGESTION)
        if value_limit is None:
            sink = _Sink(connection, effective, csv=path.suffix.lower() != ".json")
        else:
            from tabalyst.projects._bounded_values import BoundedSink

            sink = BoundedSink(
                connection, effective, csv=path.suffix.lower() != ".json", limit=value_limit
            )
        result = scan(
            path,
            config=effective,
            on_record=sink,
            workers=workers,
            on_progress=on_progress,
        )
        if before != _source_stamp(path):
            raise DatabaseValidationError("Source changed while building staging")
        if config_sha256(result.config) != config_sha256(
            resolve_config_defaults(effective, result.source.format)
        ):
            raise DatabaseValidationError("Effective Scan configuration changed")
        if value_limit is not None:
            # This stage is private. Commit bounded ingestion batches rather
            # than accumulating catalog-update undo for the whole source.
            sink.records.flush()
            sink.observations.flush()
            connection.execute("BEGIN TRANSACTION")
        sink.finalize(connection, result)
        document = scan_document(result).encode("utf-8")
        scan_sha256 = hashlib.sha256(document).hexdigest()
        connection.execute(
            "INSERT INTO meta.format VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                1,
                FORMAT,
                FORMAT_VERSION,
                FORMAT_REVISION if value_limit is None else 2,
                project_id,
                workspace_id,
                generation_id,
                scan_sha256,
                DUCKDB_VERSION,
                STORAGE_COMPATIBILITY,
                LOADER_VERSION if value_limit is None else 2,
                RECORD_SEMANTICS_VERSION,
            ),
        )
        validate_database(
            connection,
            result,
            project_id=project_id,
            workspace_id=workspace_id,
            generation_id=generation_id,
            scan_sha256=scan_sha256,
        )
        descriptor = os.open(scan_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document)
        connection.execute("COMMIT")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    if database_path.with_suffix(".duckdb.wal").exists():
        raise DatabaseValidationError("Staging database still requires a WAL")
    validate_staging(
        database_path,
        scan_path,
        result,
        project_id=project_id,
        workspace_id=workspace_id,
        generation_id=generation_id,
        database_config={
            "enable_external_access": False,
            "memory_limit": memory_limit,
            "threads": 1,
            "preserve_insertion_order": False,
            "temp_directory": spill_directory,
            "max_temp_directory_size": spill_limit,
        },
    )
    return StagedScan(
        result, scan_path, database_path, scan_sha256, _file_hash(database_path)
    )
