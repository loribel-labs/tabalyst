"""Private, exhaustive staging validation against the authoritative Scan.

This is deliberately not a public project opener. d2 must bind artifacts to
an atomic manifest before any consumer can use this database.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import duckdb

from tabalyst.projects._codec import (
    DatabaseCompatibilityError,
    DatabaseOpenError,
    DatabaseValidationError,
    bigint,
    decode_path,
    decode_value,
    json_text,
)
from tabalyst.projects._query_budget import apply_spill_limit
from tabalyst.projects._schema import (
    DUCKDB_VERSION,
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    LOADER_VERSION,
    RECORD_SEMANTICS_VERSION,
    STORAGE_COMPATIBILITY,
)
from tabalyst.scanner.config import config_sha256
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.observations import Location, Observation, Record
from tabalyst.scanner.paths import Column
from tabalyst.scanner.records import (
    PathTokens,
    RecordContext,
    TableLayout,
    record_digest,
)

LISTINGS = ("records.with_missing", "records.empty", "records.duplicates")


def record_flags(record: Record, context: RecordContext) -> tuple[bool, bool]:
    scalars = missing = 0
    for _, native, value in record.observations:
        if native in ("object", "array"):
            continue
        scalars += 1
        missing += (native == "null" and context.null_missing) or (
            native == "string" and context.is_missing(value)
        )
    return bool(missing), bool(scalars and missing == scalars)


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise DatabaseValidationError(detail)


def _rows(connection, query, parameters=None):
    # cursor() is a separate DuckDB transaction and cannot see staging DDL.
    # Callers do not execute another query until this iterator is exhausted.
    connection.execute(query, parameters)
    while rows := connection.fetchmany(1024):
        yield from rows


def validate_database(
    connection,
    result: ScanResult,
    *,
    project_id: str,
    workspace_id: str,
    generation_id: str,
    scan_sha256: str,
) -> None:
    revision = connection.execute("SELECT format_revision FROM meta.format").fetchall()
    if revision == [(2,)]:
        from tabalyst.projects._bounded_values import validate_bounded_database

        return validate_bounded_database(
            connection,
            result,
            project_id=project_id,
            workspace_id=workspace_id,
            generation_id=generation_id,
            scan_sha256=scan_sha256,
        )
    objects = connection.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables "
        "WHERE table_schema NOT IN ('information_schema','pg_catalog')"
    ).fetchall()
    expected_objects = {
        ("meta", name, "BASE TABLE")
        for name in ("format", "datasets", "fields", "listings")
    } | {
        ("data", name, "BASE TABLE")
        for name in ("records", "observations", "listing_records")
    }
    _require(
        set(objects) == expected_objects,
        "Unexpected database objects or ingestion tables",
    )
    metadata = connection.execute("SELECT * FROM meta.format").fetchall()
    _require(len(metadata) == 1, "Expected singleton database format")
    row = metadata[0]
    if row[0:4] != (1, FORMAT, FORMAT_VERSION, FORMAT_REVISION) or row[10:] != (
        LOADER_VERSION,
        RECORD_SEMANTICS_VERSION,
    ):
        raise DatabaseCompatibilityError("Unsupported Tabalyst project-db version")
    _require(
        row[4:8] == (project_id, workspace_id, generation_id, scan_sha256),
        "Database artifact binding mismatch",
    )
    _require(
        row[8:10] == (DUCKDB_VERSION, STORAGE_COMPATIBILITY),
        "Unsupported DuckDB writer/storage target",
    )
    _require(
        config_sha256(result.config) == result.config_sha256,
        "Scan configuration fingerprint mismatch",
    )
    expected_datasets = [
        (
            d.id,
            i,
            d.kind,
            None
            if d.collection_path is None
            else json_text([p.model_dump() for p in d.collection_path]),
            bigint(d.record_count),
        )
        for i, d in enumerate(result.datasets, 1)
    ]
    _require(
        connection.execute("SELECT * FROM meta.datasets ORDER BY ordinal").fetchall()
        == expected_datasets,
        "Dataset metadata mismatch",
    )
    expected_fields = [
        (
            d.id,
            f.id,
            i,
            json_text([p.model_dump() for p in f.path]),
            f.name,
            f.display,
            f.parent,
            f.collection,
        )
        for d in result.datasets
        for i, f in enumerate(d.fields, 1)
    ]
    actual_fields = connection.execute(
        "SELECT f.* FROM meta.fields f JOIN meta.datasets d USING(dataset_id) "
        "ORDER BY d.ordinal, f.ordinal"
    ).fetchall()
    _require(actual_fields == expected_fields, "Field metadata mismatch")
    # Required links that DuckDB cannot express as cross-schema FKs, plus
    # nullable parent/collection links (potentially discovered after a field).
    checks = [
        "SELECT 1 FROM data.records r ANTI JOIN meta.datasets d USING(dataset_id)",
        (
            "SELECT 1 FROM data.observations o LEFT JOIN meta.fields f "
            "ON o.dataset_id=f.dataset_id AND o.path_json=f.path_json "
            "WHERE o.field_id IS DISTINCT FROM f.field_id"
        ),
        (
            "SELECT 1 FROM meta.fields f LEFT JOIN meta.fields p "
            "ON f.dataset_id=p.dataset_id AND f.parent_field_id=p.field_id "
            "WHERE f.parent_field_id IS NOT NULL AND p.field_id IS NULL"
        ),
        (
            "SELECT 1 FROM meta.fields f LEFT JOIN meta.datasets d "
            "ON f.collection_dataset_id=d.dataset_id "
            "WHERE f.collection_dataset_id IS NOT NULL AND d.dataset_id IS NULL"
        ),
        (
            "SELECT 1 FROM data.listing_records r ANTI JOIN meta.listings l "
            "USING(dataset_id,listing_id)"
        ),
        (
            "SELECT 1 FROM data.records r LEFT JOIN "
            "(SELECT dataset_id,record_index,count(*) n,min(observation_index) lo,"
            " max(observation_index) hi FROM data.observations GROUP BY ALL) o "
            "USING(dataset_id,record_index) WHERE r.observation_count != coalesce(n,0) "
            "OR (n>0 AND (lo!=1 OR hi!=n))"
        ),
    ]
    for query in checks:
        _require(
            connection.execute(query + " LIMIT 1").fetchone() is None,
            "Invalid database mapping or observation sequence",
        )
    _require(
        sum(d.record_count for d in result.datasets) == result.scope.records_analyzed,
        "Scan analyzed scope mismatch",
    )
    context = RecordContext(
        result.config,
        StringClassifier(
            result.config.values.null_markers,
            result.config.values.null_markers_case_sensitive,
        ),
    )
    for dataset in result.datasets:
        _require(
            connection.execute(
                "SELECT count(*) FROM data.records WHERE dataset_id=?", [dataset.id]
            ).fetchone()[0]
            == dataset.record_count,
            "Analyzed record count mismatch",
        )
        table = None
        if result.source.csv is not None:
            table = TableLayout(
                tuple((Column(i),) for i in range(1, len(result.source.csv.header) + 1))
            )
        paths = PathTokens()
        native_counts = {}
        for field_id, native, count in connection.execute(
            "SELECT field_id,native_type,count(*) FROM data.observations "
            "WHERE dataset_id=? AND field_id IS NOT NULL GROUP BY field_id,native_type",
            [dataset.id],
        ).fetchall():
            native_counts.setdefault(field_id, {})[native] = count
        array_stats = {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT field_id,count(*),count(*) FILTER (WHERE array_length=0),"
                "min(array_length),max(array_length),sum(array_length) "
                "FROM data.observations WHERE dataset_id=? AND field_id IS NOT NULL "
                "AND native_type='array' GROUP BY field_id",
                [dataset.id],
            ).fetchall()
        }
        for field in dataset.fields:
            counts = native_counts.get(field.id, {})
            _require(
                counts == {k: v for k, v in field.native_types.items() if v}
                and sum(counts.values()) == field.occurrences,
                "Field native counts mismatch",
            )
            _require(
                field.presence.present == field.occurrences,
                "Field presence count mismatch",
            )
            if field.arrays is not None:
                expected_arrays = tuple(field.arrays.model_dump().values())
                _require(
                    array_stats.get(field.id) == expected_arrays,
                    "Field array statistics mismatch",
                )
            else:
                _require(field.id not in array_stats, "Unexpected field arrays")
        truncated = connection.execute(
            "SELECT coalesce(sum(depth_truncated),0) FROM data.records WHERE dataset_id=?",
            [dataset.id],
        ).fetchone()[0]
        _require(
            truncated == dataset.structure.depth_truncated_observations,
            "Depth-truncated scope mismatch",
        )
        # One record at a time, at most max_record_observations. No full
        # record registry or value table; the join itself can spill on disk.
        stream = _rows(
            connection,
            "SELECT r.record_index,r.location_json,r.depth_truncated, "
            "r.with_missing,r.is_empty,r.duplicate_key,o.observation_index, "
            "o.path_json,o.native_type,o.raw_text,o.array_length "
            "FROM data.records r LEFT JOIN data.observations o "
            "USING(dataset_id,record_index) WHERE r.dataset_id=? "
            "ORDER BY r.record_index,o.observation_index",
            [dataset.id],
        )
        previous = None
        observations = []

        def verify_record(
            header, observed, dataset_id=dataset.id, table=table, paths=paths
        ):
            index, location_text, depth, missing, empty, digest = header
            location = json.loads(location_text)
            _require(
                json_text(location) == location_text
                and set(location) <= {"record", "line", "element"}
                and location.get("record") == index,
                "Invalid record location",
            )
            for key, value in location.items():
                bigint(value, minimum=0 if key == "element" else 1)
            record = Record(dataset_id, index, Location(**location), observed, depth)
            _require(
                record_flags(record, context) == (missing, empty),
                "Record missing/empty flags mismatch",
            )
            expected = (
                record_digest(record, table, paths) if context.duplicates else None
            )
            _require(digest == expected, "Record digest mismatch")

        for item in stream:
            header = item[:6]
            if previous is not None and header != previous:
                verify_record(previous, observations)
                observations = []
            previous = header
            if item[6] is not None:
                observations.append(
                    Observation(
                        decode_path(item[7]), item[8], decode_value(*item[8:11])
                    )
                )
        if previous is not None:
            verify_record(previous, observations)
        for listing in LISTINGS:
            duplicate = listing == "records.duplicates"
            enabled = not duplicate or context.duplicates
            if duplicate:
                expected_query = (
                    (
                        "SELECT record_index FROM data.records WHERE dataset_id=? "
                        "QUALIFY record_index > min(record_index) OVER "
                        "(PARTITION BY duplicate_key)"
                    )
                    if enabled
                    else "SELECT record_index FROM data.records WHERE FALSE"
                )
                parameters = [dataset.id] if enabled else []
            else:
                flag = "is_empty" if listing == "records.empty" else "with_missing"
                expected_query = f"SELECT record_index FROM data.records WHERE dataset_id=? AND {flag}"
                parameters = [dataset.id]
            actual_query = "SELECT record_index FROM data.listing_records WHERE dataset_id=? AND listing_id=?"
            difference = f"({expected_query} EXCEPT {actual_query}) UNION ALL ({actual_query} EXCEPT {expected_query})"
            _require(
                connection.execute(
                    difference,
                    [
                        *parameters,
                        dataset.id,
                        listing,
                        dataset.id,
                        listing,
                        *parameters,
                    ],
                ).fetchone()
                is None,
                "Record listing membership mismatch",
            )
            count = connection.execute(
                f"SELECT count(*) FROM ({actual_query})", [dataset.id, listing]
            ).fetchone()[0]
            expected_meta = (
                dataset.id,
                listing,
                "complete" if enabled else "disabled",
                count if enabled else None,
                None if enabled else "duplicates_disabled",
                1,
            )
            _require(
                connection.execute(
                    "SELECT * FROM meta.listings WHERE dataset_id=? AND listing_id=?",
                    [dataset.id, listing],
                ).fetchone()
                == expected_meta,
                "Listing metadata mismatch",
            )
            scan_list = getattr(dataset.records, listing.split(".")[1])
            if not duplicate or scan_list.count.status == "complete":
                scan_count = scan_list.count.value if duplicate else scan_list.count
                _require(count == scan_count, "Complete Scan listing count mismatch")
                prefix = connection.execute(
                    actual_query + " ORDER BY record_index LIMIT ?",
                    [dataset.id, listing, len(scan_list.records)],
                ).fetchall()
                _require(
                    [r[0] for r in prefix] == scan_list.records,
                    "Complete Scan listing prefix mismatch",
                )
            elif scan_list.count.status == "limited":
                _require(
                    count >= scan_list.count.lower_bound,
                    "Duplicate lower bound mismatch",
                )
                for index in scan_list.records:
                    _require(
                        connection.execute(
                            actual_query + " AND record_index=?",
                            [dataset.id, listing, index],
                        ).fetchone()
                        is not None,
                        "Limited Scan listing is not a subset",
                    )
    _require(
        connection.execute("SELECT count(*) FROM meta.listings").fetchone()[0]
        == 3 * len(result.datasets),
        "Unexpected listings",
    )


def validate_staging(
    database_path: Path,
    scan_path: Path,
    result: ScanResult,
    *,
    project_id: str,
    workspace_id: str,
    generation_id: str,
    database_config: dict | None = None,
) -> None:
    """Reopen closed artifacts without the source. No manifest/publication."""
    document = scan_path.read_bytes()
    _require(
        ScanResult.model_validate_json(document) == result,
        "Staged scan document mismatch",
    )
    try:
        connection = duckdb.connect(
            str(database_path),
            read_only=True,
            config=database_config or {"enable_external_access": False},
        )
    except duckdb.Error as exc:
        raise DatabaseOpenError("Cannot physically open staging DuckDB") from exc
    try:
        if database_config and "max_temp_directory_size" in database_config:
            apply_spill_limit(connection, database_config["max_temp_directory_size"])
        with database_path.open("rb") as stream:
            magic, physical_version = struct.unpack("<8x4sQ", stream.read(20))
        _require(
            magic == b"DUCK" and physical_version == 67,
            "Database physical storage target mismatch",
        )
        validate_database(
            connection,
            result,
            project_id=project_id,
            workspace_id=workspace_id,
            generation_id=generation_id,
            scan_sha256=hashlib.sha256(document).hexdigest(),
        )
    except duckdb.OutOfMemoryException as exc:
        raise DatabaseValidationError(
            f"Project-db validation exhausted its memory/spill budget: {exc}"
        ) from exc
    except duckdb.Error as exc:
        raise DatabaseValidationError("Invalid project-db schema/data") from exc
    finally:
        connection.close()
