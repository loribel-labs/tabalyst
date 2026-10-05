# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Project-db revision 2: capped raw value catalog, complete record facts.

The first N distinct analyzable values of each profiled field are retained.
Later occurrences of these keys still count. Other payloads are discarded
while the ordinary Scan and record digest continue over every observation.
Revision 1 remains an independently supported, exhaustive observation store.
"""

import json

from tabalyst.projects._codec import (
    bigint,
    decode_value,
    encode_value,
    json_text,
    path_text,
)
from tabalyst.projects._schema import (
    DUCKDB_VERSION,
    FORMAT,
    FORMAT_VERSION,
    STORAGE_COMPATIBILITY,
)
from tabalyst.projects._staging import _Buffer, _Sink
from tabalyst.projects._validation import LISTINGS, _require, _rows
from tabalyst.scanner.config import config_sha256
from tabalyst.scanner.paths import ROOT

MAX_STORED_VALUES = 10000

SCHEMA = """
DROP TABLE data.observations;
DROP TABLE ingest_observations;
CREATE TABLE data.values (
    dataset_id VARCHAR NOT NULL,
    field_id VARCHAR NOT NULL,
    value_index BIGINT NOT NULL CHECK (value_index>0),
    native_type VARCHAR NOT NULL CHECK (native_type IN ('string','integer','number','boolean')),
    raw_text VARCHAR NOT NULL,
    count BIGINT NOT NULL CHECK (count>0),
    PRIMARY KEY(dataset_id,field_id,value_index)
);
CREATE TABLE meta.value_storage (
    dataset_id VARCHAR NOT NULL,
    field_id VARCHAR NOT NULL,
    distinct_limit BIGINT NOT NULL CHECK (distinct_limit BETWEEN 1 AND 10000),
    retained_distinct BIGINT NOT NULL CHECK (retained_distinct BETWEEN 0 AND 10000),
    retained_occurrences BIGINT NOT NULL CHECK (retained_occurrences>=0),
    omitted_occurrences BIGINT NOT NULL CHECK (omitted_occurrences>=0),
    PRIMARY KEY(dataset_id,field_id)
);
CREATE TEMP TABLE value_batch(dataset_id VARCHAR,path_json VARCHAR,native_type VARCHAR,raw_text VARCHAR,seen BIGINT);
CREATE TEMP TABLE value_catalog(dataset_id VARCHAR,path_json VARCHAR,native_type VARCHAR,raw_text VARCHAR,count BIGINT,seen BIGINT);
"""


class _CatalogBuffer(_Buffer):
    def __init__(self, connection, limit):
        super().__init__(
            connection,
            "value_batch",
            ("VARCHAR", "VARCHAR", "VARCHAR", "VARCHAR", "BIGINT"),
        )
        self.limit = limit

    def flush(self):
        if not self.rows:
            return
        self.connection.execute("BEGIN TRANSACTION")
        try:
            self._flush_catalog()
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def _flush_catalog(self):
        super().flush()
        c = self.connection
        c.execute(
            "CREATE TEMP TABLE grouped_values AS SELECT dataset_id,path_json,native_type,raw_text,"
            "count(*)::BIGINT AS count,min(seen) AS seen FROM value_batch GROUP BY ALL"
        )
        c.execute(
            "UPDATE value_catalog v SET count=v.count+b.count FROM grouped_values b "
            "WHERE v.dataset_id=b.dataset_id AND v.path_json=b.path_json "
            "AND v.native_type=b.native_type AND v.raw_text=b.raw_text"
        )
        c.execute(
            "CREATE TEMP TABLE candidates AS SELECT b.* FROM grouped_values b ANTI JOIN value_catalog v "
            "USING(dataset_id,path_json,native_type,raw_text)"
        )
        c.execute(
            "INSERT INTO value_catalog SELECT c.dataset_id,c.path_json,c.native_type,c.raw_text,c.count,c.seen "
            "FROM candidates c LEFT JOIN (SELECT dataset_id,path_json,count(*) retained "
            "FROM value_catalog GROUP BY ALL) t USING(dataset_id,path_json) "
            "QUALIFY row_number() OVER(PARTITION BY dataset_id,path_json ORDER BY c.seen) "
            "<= ?-coalesce(retained,0)",
            [self.limit],
        )
        c.execute(
            "DROP TABLE grouped_values; DROP TABLE candidates; DELETE FROM value_batch"
        )


class BoundedSink(_Sink):
    def __init__(self, connection, config, *, csv, limit):
        if type(limit) is not int or not 1 <= limit <= MAX_STORED_VALUES:
            raise ValueError("Stored distinct value limit must be between 1 and 10000")
        super().__init__(connection, config, csv=csv)
        connection.execute(SCHEMA)
        self.observations = _CatalogBuffer(connection, limit)
        self.limit = limit
        self.max_fields = config.limits.max_fields
        self.fields = {}
        self.seen = 0

    def __call__(self, record):
        self._record(record)
        fields = self.fields.setdefault(record.dataset, {ROOT: path_text(ROOT)})
        for observation in record.observations:
            path = fields.get(observation.path)
            if path is None:
                if len(fields) > self.max_fields:
                    continue
                path = fields[observation.path] = path_text(observation.path)
            native = observation.type
            if native not in ("string", "integer", "number", "boolean"):
                continue
            if (
                native == "string"
                and self.context.strings.category(observation.value) != "content"
            ):
                continue
            raw, _ = encode_value(observation)
            self.seen += 1
            self.observations.append((record.dataset, path, native, raw, self.seen))

    def finalize_observations(self, connection, result):
        connection.execute(
            "INSERT INTO data.values SELECT dataset_id,field_id,"
            "row_number() OVER(PARTITION BY dataset_id,field_id ORDER BY seen),native_type,raw_text,count "
            "FROM value_catalog JOIN meta.fields USING(dataset_id,path_json)"
        )
        for dataset in result.datasets:
            for field in dataset.fields:
                distinct, retained = connection.execute(
                    "SELECT count(*),coalesce(sum(count),0) FROM data.values WHERE dataset_id=? AND field_id=?",
                    [dataset.id, field.id],
                ).fetchone()
                connection.execute(
                    "INSERT INTO meta.value_storage VALUES (?,?,?,?,?,?)",
                    [
                        dataset.id,
                        field.id,
                        self.limit,
                        distinct,
                        retained,
                        field.values.count - retained,
                    ],
                )
        connection.execute(
            "DROP TABLE value_batch; DROP TABLE value_catalog; DROP TABLE ingest_records"
        )


def validate_bounded_database(
    connection, result, *, project_id, workspace_id, generation_id, scan_sha256
):
    """Validate the bounded catalog and complete memberships, not discarded cells.

    Record flags/digests originate from the full Scan hook and are hash-bound
    to the manifest. Reopen cannot independently reconstruct discarded rows.
    """
    expected_objects = {
        ("meta", n)
        for n in ("format", "datasets", "fields", "listings", "value_storage")
    } | {("data", n) for n in ("records", "listing_records", "values")}
    actual = connection.execute(
        "SELECT table_schema,table_name,table_type FROM information_schema.tables WHERE table_schema NOT IN ('information_schema','pg_catalog')"
    ).fetchall()
    _require(
        {(s, n) for s, n, t in actual if t == "BASE TABLE"} == expected_objects
        and len(actual) == len(expected_objects),
        "Unexpected bounded database objects",
    )
    _require(
        connection.execute("SELECT * FROM meta.format").fetchall()
        == [
            (
                1,
                FORMAT,
                FORMAT_VERSION,
                2,
                project_id,
                workspace_id,
                generation_id,
                scan_sha256,
                DUCKDB_VERSION,
                STORAGE_COMPATIBILITY,
                2,
                1,
            )
        ],
        "Bounded database artifact binding/version mismatch",
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
            d.record_count,
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
    _require(
        connection.execute(
            "SELECT f.* FROM meta.fields f JOIN meta.datasets d USING(dataset_id) ORDER BY d.ordinal,f.ordinal"
        ).fetchall()
        == expected_fields,
        "Field metadata mismatch",
    )
    for query in (
        "SELECT 1 FROM data.records ANTI JOIN meta.datasets USING(dataset_id)",
        "SELECT 1 FROM data.values ANTI JOIN meta.fields USING(dataset_id,field_id)",
        "SELECT 1 FROM meta.value_storage ANTI JOIN meta.fields USING(dataset_id,field_id)",
        "SELECT 1 FROM data.listing_records ANTI JOIN meta.listings USING(dataset_id,listing_id)",
        "SELECT 1 FROM data.values GROUP BY dataset_id,field_id,native_type,raw_text HAVING count(*)>1",
        "SELECT 1 FROM data.values GROUP BY dataset_id,field_id HAVING min(value_index)!=1 OR max(value_index)!=count(*)",
        "SELECT 1 FROM data.records WHERE is_empty AND NOT with_missing",
    ):
        _require(
            connection.execute(query + " LIMIT 1").fetchone() is None,
            "Invalid bounded database mapping/catalog",
        )
    _require(
        sum(d.record_count for d in result.datasets) == result.scope.records_analyzed,
        "Scan analyzed scope mismatch",
    )
    field_map = {(d.id, f.id): f for d in result.datasets for f in d.fields}
    from tabalyst.scanner.field import StringClassifier

    strings = StringClassifier(
        result.config.values.null_markers,
        result.config.values.null_markers_case_sensitive,
    )
    for dataset_id, field_id, native, raw, count in _rows(
        connection,
        "SELECT dataset_id,field_id,native_type,raw_text,count FROM data.values",
    ):
        decode_value(native, raw, None)
        _require(
            native != "string" or strings.category(raw) == "content",
            "Non-content catalog value",
        )
        field = field_map[(dataset_id, field_id)]
        population = (
            field.strings.content
            if native == "string"
            else field.native_types.get(native, 0)
        )
        _require(count <= population, "Catalog count exceeds native population")
    for dataset in result.datasets:
        count, truncated = connection.execute(
            "SELECT count(*),coalesce(sum(depth_truncated),0) FROM data.records WHERE dataset_id=?",
            [dataset.id],
        ).fetchone()
        _require(
            count == dataset.record_count
            and truncated == dataset.structure.depth_truncated_observations,
            "Record scope mismatch",
        )
        for index, location in _rows(
            connection,
            "SELECT record_index,location_json FROM data.records WHERE dataset_id=?",
            [dataset.id],
        ):
            value = json.loads(location)
            _require(
                isinstance(value, dict)
                and json_text(value) == location
                and value.get("record") == index
                and set(value) <= {"record", "line", "element"},
                "Invalid record location",
            )
            for key, coordinate in value.items():
                bigint(coordinate, minimum=0 if key == "element" else 1)
        _require(
            connection.execute(
                "SELECT 1 FROM data.records WHERE dataset_id=? AND "
                + (
                    "duplicate_key IS NULL"
                    if result.config.records.duplicates
                    else "duplicate_key IS NOT NULL"
                )
                + " LIMIT 1",
                [dataset.id],
            ).fetchone()
            is None,
            "Duplicate digest availability mismatch",
        )
        for field in dataset.fields:
            stored = connection.execute(
                "SELECT * FROM meta.value_storage WHERE dataset_id=? AND field_id=?",
                [dataset.id, field.id],
            ).fetchone()
            distinct, retained = connection.execute(
                "SELECT count(*),coalesce(sum(count),0) FROM data.values WHERE dataset_id=? AND field_id=?",
                [dataset.id, field.id],
            ).fetchone()
            _require(stored is not None, "Missing value storage metadata")
            for native, native_count in connection.execute(
                "SELECT native_type,sum(count) FROM data.values WHERE dataset_id=? AND field_id=? GROUP BY native_type",
                [dataset.id, field.id],
            ).fetchall():
                population = (
                    field.strings.content
                    if native == "string"
                    else field.native_types.get(native, 0)
                )
                _require(
                    native_count <= population,
                    "Catalog native total exceeds population",
                )
            _require(
                stored[3:5] == (distinct, retained)
                and retained + stored[5] == field.values.count
                and distinct <= stored[2]
                and (stored[5] == 0 or distinct == stored[2]),
                "Value storage budget/population mismatch",
            )
            if field.values.cardinality.status == "complete":
                _require(
                    (stored[5] > 0 and distinct < field.values.cardinality.value)
                    or (stored[5] == 0 and distinct == field.values.cardinality.value),
                    "Complete raw cardinality mismatch",
                )
        for listing in LISTINGS:
            enabled = (
                listing != "records.duplicates" or result.config.records.duplicates
            )
            if listing == "records.duplicates":
                expected = (
                    "SELECT record_index FROM data.records WHERE dataset_id=? QUALIFY record_index>min(record_index) OVER(PARTITION BY duplicate_key)"
                    if enabled
                    else "SELECT record_index FROM data.records WHERE FALSE"
                )
                params = [dataset.id] if enabled else []
            else:
                flag = "is_empty" if listing == "records.empty" else "with_missing"
                expected = f"SELECT record_index FROM data.records WHERE dataset_id=? AND {flag}"
                params = [dataset.id]
            actual = "SELECT record_index FROM data.listing_records WHERE dataset_id=? AND listing_id=?"
            delta = (
                f"({expected} EXCEPT {actual}) UNION ALL ({actual} EXCEPT {expected})"
            )
            _require(
                connection.execute(
                    delta, [*params, dataset.id, listing, dataset.id, listing, *params]
                ).fetchone()
                is None,
                "Record listing membership mismatch",
            )
            count = connection.execute(
                f"SELECT count(*) FROM ({actual})", [dataset.id, listing]
            ).fetchone()[0]
            _require(
                connection.execute(
                    "SELECT * FROM meta.listings WHERE dataset_id=? AND listing_id=?",
                    [dataset.id, listing],
                ).fetchone()
                == (
                    dataset.id,
                    listing,
                    "complete" if enabled else "disabled",
                    count if enabled else None,
                    None if enabled else "duplicates_disabled",
                    1,
                ),
                "Listing metadata mismatch",
            )
            listed = getattr(dataset.records, listing.split(".")[1])
            scan_count = listed.count
            if listing != "records.duplicates" or scan_count.status == "complete":
                _require(
                    count
                    == (
                        scan_count.value
                        if listing == "records.duplicates"
                        else scan_count
                    ),
                    "Complete Scan listing count mismatch",
                )
                prefix = connection.execute(
                    actual + " ORDER BY record_index LIMIT ?",
                    [dataset.id, listing, len(listed.records)],
                ).fetchall()
                _require(
                    [r[0] for r in prefix] == listed.records,
                    "Complete Scan listing prefix mismatch",
                )
            elif scan_count.status == "limited":
                _require(
                    count >= scan_count.lower_bound, "Duplicate lower bound mismatch"
                )
                for index in listed.records:
                    _require(
                        connection.execute(
                            actual + " AND record_index=?", [dataset.id, listing, index]
                        ).fetchone()
                        is not None,
                        "Limited Scan listing is not a subset",
                    )
    _require(
        connection.execute("SELECT count(*) FROM meta.value_storage").fetchone()[0]
        == len(field_map),
        "Unexpected storage metadata",
    )
    _require(
        connection.execute("SELECT count(*) FROM meta.listings").fetchone()[0]
        == 3 * len(result.datasets),
        "Unexpected listings",
    )
