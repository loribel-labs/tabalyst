"""Private staging contract; no project publication is enabled by these tests."""

import hashlib
import json
import struct
from decimal import Decimal

import duckdb
import pytest

from tabalyst.projects import _staging
from tabalyst.projects._codec import (
    DatabaseCompatibilityError,
    DatabaseOpenError,
    DatabaseValidationError,
    bigint,
    decode_path,
    decode_value,
    encode_value,
    json_text,
    path_text,
)
from tabalyst.projects._schema import DUCKDB_VERSION, STORAGE_COMPATIBILITY
from tabalyst.projects._staging import build_staging
from tabalyst.projects._validation import validate_staging
from tabalyst.projects.identity import new_project_id
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.observations import Observation
from tabalyst.scanner.paths import ITEMS, ROOT, Column, Key
from tabalyst.scanner.records import PathTokens, record_digest


def semantic(result):
    return result.model_dump(
        mode="json", by_alias=True, exclude={"started_at", "duration_seconds"}
    )


def build(tmp_path, source, **kwargs):
    project_id, generation_id = new_project_id(), new_project_id()
    staged = build_staging(
        source,
        tmp_path / generation_id,
        project_id=project_id,
        generation_id=generation_id,
        workers=kwargs.pop("workers", 1),
        **kwargs,
    )
    return staged, {
        "project_id": project_id,
        "workspace_id": "local",
        "generation_id": generation_id,
    }


CSV_CASES = [
    ('a,a,,A,select,"a.b",é\n1,2,3,4,5,6,7\n1,2,3,4,5,6,7\n', {}),
    (
        'a,b\n"line1\nline2","he said ""hello"""\n\n, \n',
        {"errors": {"policy": "tolerant"}},
    ),
    ("\ufeffa;b\r\n0;001\r\n", {"csv": {"delimiter": ";"}}),
    ("a,b\n1\n2,3\n4,5,6\n,\n", {"errors": {"policy": "tolerant"}}),
    ("a,b,c\n1,2,3\n1,2,4\n1,2,3\n", {"limits": {"max_fields": 1}}),
    ("a,b\n", {}),
    (
        'a\nN/A\n na \n \n""\ncontent\n',
        {
            "values": {
                "null_markers": ["N/A", "NA"],
                "null_markers_case_sensitive": False,
                "missing": ["marker"],
            }
        },
    ),
]

JSON_CASES = [
    ('{"left":[{"x":1},{"x":1}],"right":[{"x":1}]}', {}),
    ("null", {}),
    ("true", {}),
    ("123.00", {}),
    ('"é\\u0000東京"', {}),
    ("{}", {}),
    ("[]", {}),
    ('[{}, {"x":null}, {"x":""}, {"x":false}, {"x":123}, {"x":"123"}]', {}),
    (
        (
            '{"rows":[{"a":[{}, {"x":1}, {"x":null}], "parent":null},'
            '{"a":[{"x":" "}], "parent":{}}, {"late":true}], "empty":[]}'
        ),
        {},
    ),
    (
        '{"groups":[{"rows":[1,2]},{"rows":[2,3]}]}',
        {"json": {"collections": ["$.groups[].rows[]", "$.absent[]"]}},
    ),
    (
        '[{"":1,"a.b":2,"a[]":3,"A":4,"a":5,"\\"":6,"東京":7},{"later":8}]',
        {"limits": {"max_fields": 2}},
    ),
    ('[{"a":{"b":{"c":1}}}, {"a":{"b":{"c":2}}}]', {"limits": {"max_depth": 1}}),
    (
        '[{"a":1,"b":2}, {"a":3}, {"a":1,"b":2}]',
        {"limits": {"max_record_observations": 2}, "errors": {"policy": "tolerant"}},
    ),
    ('[{"a":1,"a":2}, {"a":3}]', {"errors": {"policy": "tolerant"}}),
    ("[1,1.0,1.00,1e3,1e3,1.00,0,-0,0.00,-0.00,1e-500," + "9" * 500 + "]", {}),
]


@pytest.mark.parametrize(("text", "settings"), CSV_CASES)
def test_csv_stream_and_scan_parity(tmp_path, text, settings, monkeypatch):
    source = tmp_path / "source.csv"
    source.write_bytes(text.encode("utf-8"))
    assert_parity(tmp_path, source, ScanConfig.model_validate(settings), monkeypatch)


@pytest.mark.parametrize(("text", "settings"), JSON_CASES)
@pytest.mark.parametrize("backend", ["python", "yajl2_c"])
def test_json_stream_and_scan_parity(tmp_path, text, settings, backend, monkeypatch):
    import ijson

    from tabalyst.scanner.readers import json_reader

    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend(backend))
    source = tmp_path / "source.json"
    source.write_text(text, encoding="utf-8")
    assert_parity(tmp_path, source, ScanConfig.model_validate(settings), monkeypatch)


def test_jsonl_stream_and_scan_parity(tmp_path, monkeypatch):
    source = tmp_path / "source.jsonl"
    source.write_text(
        '{"id": 1, "a": {"b": [1, 2.5, null]}}\nnot json\n{"id": 2, "tags": []}\n',
        encoding="utf-8",
    )
    assert_parity(tmp_path, source, ScanConfig(), monkeypatch)


def assert_parity(tmp_path, source, config, monkeypatch):
    observed = []
    reference = scan(source, config=config, workers=1, on_record=observed.append)
    assert semantic(reference) == semantic(scan(source, config=config, workers=1))
    monkeypatch.setattr(_staging, "BATCH_ROWS", 2)
    monkeypatch.setattr(_staging, "BATCH_BYTES", 50)
    staged, binding = build(tmp_path, source, config=config)
    assert semantic(staged.result) == semantic(reference)
    with duckdb.connect(str(staged.database_path), read_only=True) as connection:
        expected = sorted(
            [
                (r.dataset, r.index, i, path_text(o.path), o.type, *encode_value(o))
                for r in observed
                for i, o in enumerate(r.observations, 1)
            ]
        )
        actual = connection.execute(
            "SELECT dataset_id,record_index,observation_index,path_json,native_type,raw_text,array_length "
            "FROM data.observations ORDER BY dataset_id,record_index,observation_index"
        ).fetchall()
        assert actual == expected
        locations = connection.execute(
            "SELECT dataset_id,record_index,location_json,depth_truncated FROM data.records "
            "ORDER BY dataset_id,record_index"
        ).fetchall()
        assert locations == sorted(
            (r.dataset, r.index, json_text(r.location.to_dict()), r.depth_truncated)
            for r in observed
        )
        for dataset in reference.datasets:
            for field in dataset.fields:
                counts = dict(
                    connection.execute(
                        "SELECT native_type,count(*) FROM data.observations "
                        "WHERE dataset_id=? AND field_id=? GROUP BY native_type",
                        [dataset.id, field.id],
                    ).fetchall()
                )
                assert counts == {k: v for k, v in field.native_types.items() if v}
                assert sum(counts.values()) == field.occurrences
                canonical = json_text([p.model_dump() for p in field.path])
                segments = json.loads(canonical)
                if not segments:
                    parent_count = dataset.record_count
                else:
                    parent_native = "array" if "items" in segments[-1] else "object"
                    parent_count = connection.execute(
                        "SELECT count(*) FROM data.observations WHERE dataset_id=? "
                        "AND path_json=? AND native_type=?",
                        [dataset.id, json_text(segments[:-1]), parent_native],
                    ).fetchone()[0]
                assert field.presence.parent_count == parent_count
                assert field.presence.absent == (
                    None
                    if segments and "items" in segments[-1]
                    else parent_count - field.occurrences
                )
                if field.arrays is not None:
                    lengths = connection.execute(
                        "SELECT array_length FROM data.observations "
                        "WHERE dataset_id=? AND field_id=? AND native_type='array'",
                        [dataset.id, field.id],
                    ).fetchall()
                    assert (
                        lengths
                    )  # metadata and repeated container observations survive
        assert connection.execute(
            "SELECT storage_compatibility FROM meta.format"
        ).fetchone() == (STORAGE_COMPATIBILITY,)
    source.unlink()
    validate_staging(staged.database_path, staged.scan_path, staged.result, **binding)
    assert (
        hashlib.sha256(staged.scan_path.read_bytes()).hexdigest() == staged.scan_sha256
    )
    assert (
        hashlib.sha256(staged.database_path.read_bytes()).hexdigest()
        == staged.database_sha256
    )
    assert not staged.database_path.with_suffix(".duckdb.wal").exists()
    assert not (tmp_path / "project.json").exists()
    assert not (tmp_path / "index.json").exists()
    assert not (tmp_path / "generations").exists()


@pytest.mark.parametrize(
    ("native", "value"),
    [
        ("string", "é東京\x00\n\t" + "x" * 100_000),
        ("string", ""),
        ("integer", 10**500),
        ("number", Decimal("1.2300E+900")),
        ("number", Decimal("-0.00")),
        ("number", Decimal("1E-900")),
        ("boolean", True),
        ("boolean", False),
        ("null", None),
        ("object", None),
        ("array", 0),
        ("array", 2**63 - 1),
    ],
    ids=lambda value: type(value).__name__,
)
def test_codec_preserves_repr_and_digest(native, value):
    from tabalyst.scanner.observations import Location, Record

    observation = Observation((Key("x"),), native, value)
    restored = Observation(
        decode_path(path_text(observation.path)),
        native,
        decode_value(native, *encode_value(observation)),
    )
    assert repr(restored) == repr(observation)
    original_record = Record("$", 1, Location(1), [observation])
    restored_record = Record("$", 1, Location(1), [restored])
    assert record_digest(original_record, None, PathTokens()) == record_digest(
        restored_record, None, PathTokens()
    )


@pytest.mark.parametrize(
    ("native", "text", "length"),
    [
        ("string", None, None),
        ("integer", "01", None),
        ("number", "NaN", None),
        ("number", "1e3", None),
        ("boolean", "1", None),
        ("null", "", None),
        ("array", None, -1),
        ("array", None, 2**63),
        ("unknown", None, None),
        ("object", None, 0),
        ("string", "x", 1),
    ],
)
def test_codec_rejects_invalid_payload(native, text, length):
    with pytest.raises(DatabaseValidationError):
        decode_value(native, text, length)


def test_path_codec_and_bigint_guards():
    path = (Key(""), Key('a.b[]"'), ITEMS, Column(3))
    assert decode_path(path_text(path)) == path
    assert decode_path(path_text(ROOT)) == ROOT
    for value in ('[{"items":false}]', '[{"column":true}]', '[{"column":0}]', "{}"):
        with pytest.raises(DatabaseValidationError):
            decode_path(value)
    for value in (-1, 2**63, 1.2, True):
        with pytest.raises(DatabaseValidationError):
            bigint(value)


def test_large_memberships_and_late_duplicate_groups(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text(
        "x\nfirst\nlate\nlate\n" + "\n".join(['""'] * 13_000) + "\n", encoding="utf-8"
    )
    config = ScanConfig.model_validate(
        {"limits": {"max_tracked_records": 1, "max_listed_records": 0}}
    )
    staged, _ = build(tmp_path, source, config=config)
    assert staged.result.datasets[0].records.duplicates.count.status == "limited"
    with duckdb.connect(str(staged.database_path), read_only=True) as connection:
        counts = dict(
            connection.execute(
                "SELECT listing_id,record_count FROM meta.listings"
            ).fetchall()
        )
        assert counts == {
            "records.with_missing": 13_000,
            "records.empty": 13_000,
            "records.duplicates": 13_000,
        }
        assert connection.execute(
            "SELECT min(record_index) FROM data.listing_records WHERE listing_id='records.duplicates'"
        ).fetchone() == (3,)
    assert staged.result.datasets[0].records.with_missing.records == []


@pytest.mark.parametrize("exposure", ["mask", "hide", "show"])
def test_disabled_duplicates_and_raw_exposure(tmp_path, exposure):
    source = tmp_path / "source.csv"
    source.write_text("email\na@example.com\na@example.com\n", encoding="utf-8")
    config = ScanConfig.model_validate(
        {"records": {"duplicates": False}, "exposure": {"sensitive_values": exposure}}
    )
    staged, _ = build(tmp_path, source, config=config)
    assert staged.result.datasets[0].fields[0].exposure == exposure
    with duckdb.connect(str(staged.database_path), read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT raw_text FROM data.observations WHERE native_type='string'"
            ).fetchall()
            == [("a@example.com",)] * 2
        )
        assert (
            connection.execute("SELECT duplicate_key FROM data.records").fetchall()
            == [(None,)] * 2
        )
        assert connection.execute(
            "SELECT status,record_count FROM meta.listings WHERE listing_id='records.duplicates'"
        ).fetchone() == ("disabled", None)


def test_effective_config_layers_and_cp1252(tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes("a;b\ncafé;N/A\n".encode("cp1252"))
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text(
        json.dumps(
            {"scan": {"csv": {"delimiter": ","}, "values": {"null_markers": ["old"]}}}
        ),
        encoding="utf-8",
    )
    second.write_text(
        json.dumps(
            {
                "scan": {
                    "csv": {"encoding": "cp1252"},
                    "values": {"null_markers": ["N/A"]},
                }
            }
        ),
        encoding="utf-8",
    )
    staged, _ = build(tmp_path, source, config_paths=[first, second], delimiter=";")
    assert staged.result.config.values.null_markers == ["N/A"]
    assert staged.result.source.csv.delimiter == ";"
    assert staged.result.datasets[0].records.with_missing.count == 1


@pytest.mark.parametrize(
    "change", ["version", "binding", "mapping", "payload", "listing", "scan"]
)
def test_reopen_rejects_invalid_database(tmp_path, change):
    source = tmp_path / "source.csv"
    source.write_text("a\n1\n1\n", encoding="utf-8")
    staged, binding = build(tmp_path, source)
    if change == "scan":
        staged.scan_path.write_bytes(
            staged.scan_path.read_bytes().replace(
                b'"name": "source.csv"', b'"name": "other.csv"'
            )
        )
    else:
        with duckdb.connect(str(staged.database_path)) as connection:
            queries = {
                "version": "UPDATE meta.format SET format_revision=999",
                "binding": "UPDATE meta.format SET generation_id='other'",
                "mapping": "UPDATE data.observations SET field_id='bad' WHERE field_id IS NOT NULL",
                "payload": "UPDATE data.observations SET native_type='boolean',raw_text='bad' WHERE field_id IS NOT NULL",
                "listing": "DELETE FROM data.listing_records WHERE listing_id='records.duplicates'",
            }
            connection.execute(queries[change])
    expected_error = (
        DatabaseCompatibilityError if change == "version" else DatabaseValidationError
    )
    with pytest.raises(expected_error):
        validate_staging(
            staged.database_path, staged.scan_path, staged.result, **binding
        )


def test_physical_failure_is_distinct(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    staged, binding = build(tmp_path, source)
    staged.database_path.write_bytes(b"not a database")
    with pytest.raises(DatabaseOpenError):
        validate_staging(
            staged.database_path, staged.scan_path, staged.result, **binding
        )


def test_runtime_and_physical_target(tmp_path):
    assert duckdb.__version__ == DUCKDB_VERSION
    source = tmp_path / "source.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    staged, _ = build(tmp_path, source)
    magic, version = struct.unpack("<8x4sQ", staged.database_path.read_bytes()[:20])
    assert magic == b"DUCK" and version == 67  # v1.4.x, not 1.5.x's 68


def test_workers_and_long_released_values(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps([{"x": "a" * 20_000}, {"x": "a" * 20_000}]), encoding="utf-8"
    )
    staged, _ = build(tmp_path, source, workers=2)
    assert semantic(staged.result) == semantic(scan(source, workers=1))
    with duckdb.connect(str(staged.database_path), read_only=True) as connection:
        assert connection.execute(
            "SELECT max(length(raw_text)) FROM data.observations"
        ).fetchone() == (20_000,)


@pytest.mark.parametrize("failure", ["sink", "finalize", "serialize", "source"])
def test_failure_never_publishes(tmp_path, monkeypatch, failure):
    source = tmp_path / "source.csv"
    source.write_text("a\n1\n2\n", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("injected disk/spill failure")

    if failure == "sink":
        monkeypatch.setattr(_staging._Buffer, "flush", fail)
        monkeypatch.setattr(_staging, "BATCH_ROWS", 1)
    elif failure == "finalize":
        monkeypatch.setattr(_staging._Sink, "finalize", fail)
    elif failure == "serialize":
        monkeypatch.setattr(_staging, "scan_document", fail)
    else:
        original = _staging.scan

        def changing_scan(*args, **kwargs):
            result = original(*args, **kwargs)
            source.write_text("a\nchanged\n", encoding="utf-8")
            return result

        monkeypatch.setattr(_staging, "scan", changing_scan)
    with pytest.raises((OSError, DatabaseValidationError)):
        build(tmp_path, source)
    assert not list(tmp_path.rglob("project.json"))
    assert not list(tmp_path.rglob("index.json"))
    assert not list(tmp_path.rglob("scan.json"))


def test_existing_stage_and_strict_parse_failure(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1\n", encoding="utf-8")
    stage = tmp_path / "stage"
    stage.mkdir()
    marker = stage / "marker"
    marker.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        build_staging(
            source, stage, project_id=new_project_id(), generation_id=new_project_id()
        )
    assert marker.read_bytes() == b"preserve"
    from tabalyst.errors import InputError

    with pytest.raises(InputError):
        build(tmp_path, source)


@pytest.mark.parametrize(
    "payload", [b"", b"a\nx\x00y\n", b"a\n\xff\n", b'a\n"unterminated\n']
)
def test_reader_failures_match_scan(tmp_path, payload):
    from tabalyst.errors import InputError

    source = tmp_path / "bad.csv"
    source.write_bytes(payload)
    with pytest.raises(InputError):
        scan(source, workers=1)
    with pytest.raises(InputError):
        build(tmp_path, source)


def test_inherited_digest_collisions(tmp_path, monkeypatch):
    from tabalyst.scanner import records

    monkeypatch.setattr(records, "_table_digest", lambda values: b"x" * 16)
    source = tmp_path / "source.csv"
    source.write_text("a\nfirst\nsecond\nthird\n", encoding="utf-8")
    staged, _ = build(tmp_path, source)
    assert staged.result.datasets[0].records.duplicates.count.value == 2


def test_memory_exhaustion_fails_without_partial_claim(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a\n1\n", encoding="utf-8")
    with pytest.raises(duckdb.OutOfMemoryException):
        build(tmp_path, source, memory_limit="1MB")
    assert not list(tmp_path.rglob("project.json"))


def test_runtime_can_spill_with_external_access_disabled(tmp_path):
    spill = tmp_path / "spill"
    with duckdb.connect(
        config={"memory_limit": "32MB", "temp_directory": str(spill), "threads": 1}
    ) as connection:
        connection.execute("SET enable_external_access=false")
        connection.execute(
            "CREATE TEMP TABLE probe AS SELECT i,md5(i::VARCHAR) s "
            "FROM range(500000) t(i)"
        )
        connection.execute("SELECT * FROM probe ORDER BY s")
        assert any(p.stat().st_size for p in spill.glob("*"))
        count = 0
        while rows := connection.fetchmany(1024):
            count += len(rows)
        assert count == 500_000
