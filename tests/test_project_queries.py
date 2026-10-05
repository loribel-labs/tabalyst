# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exhaustive, exposure-aware private listings and generation cursor contracts."""

import itertools
import json
from dataclasses import replace

import duckdb
import pytest
from test_project_database import CSV_CASES, JSON_CASES

from tabalyst.errors import InputError
from tabalyst.projects import StorageLocation, _queries
from tabalyst.projects._generation import open_generation
from tabalyst.projects._publication import publish_scan
from tabalyst.projects._queries import (
    Cursor,
    QueryError,
    StaleCursorError,
    materialize_values,
    records_page,
)
from tabalyst.projects._query_budget import QueryBudget, apply_spill_limit
from tabalyst.projects._staging import _file_hash
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.config import resolve_config_defaults
from tabalyst.scanner.normalization import STAGES


def publish(tmp_path, text, *, suffix=".csv", settings=None, value_limit=10000):
    source = tmp_path / ("source" + suffix)
    source.write_text(text, encoding="utf-8", newline="")
    config = ScanConfig.model_validate(settings or {})
    location = StorageLocation(tmp_path / "storage")
    outcome = publish_scan(source, location, config, workers=1, value_limit=value_limit)
    return location, source, config, outcome


def walk(method, *, size=2, status="complete"):
    items, cursor, seen = [], None, set()
    while True:
        page = method(size=size, cursor=cursor)
        assert page.status == status
        assert len(page.items) <= size
        items.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            return page, items
        assert cursor not in seen
        seen.add(cursor)


def assert_value_parity(pinned, reference):
    tiny = QueryBudget(batch_rows=2, batch_bytes=50)
    for dataset in reference.datasets:
        for field in dataset.fields:
            with materialize_values(pinned, dataset.id, field.id, budget=tiny) as query:
                page, frequencies = walk(query.frequencies_page, size=1)
                assert page.scope.generation_id == pinned.generation_id
                assert page.scope.structure == dataset.structure
                assert page.scope.scan_scope == reference.scope
                assert query.value_count == field.values.count
                measure = field.values.frequencies
                if measure.status == "complete":
                    assert frequencies == measure.value.listed
                    assert page.total == measure.value.distinct
                else:
                    assert measure.status == "not_applicable"
                    assert frequencies == [] and page.total == 0
                page, groups = walk(query.groups_page, size=1)
                measure = field.normalization.variant_groups
                if measure.status == "not_applicable":
                    assert groups == [] and page.total == 0
                    continue
                assert page.total == measure.value.groups
                assert [(g.key, g.count, g.distinct) for g in groups] == [
                    (g.key, g.count, g.distinct) for g in measure.value.listed
                ]
                for actual, expected in zip(groups, measure.value.listed, strict=True):
                    _, variants = walk(
                        lambda key=actual.key, **kw: query.variants_page(key, **kw),
                        size=1,
                    )
                    assert variants == expected.variants


@pytest.mark.parametrize(("text", "settings"), CSV_CASES)
def test_csv_exhaustive_queries_match_scan(tmp_path, text, settings):
    location, _, _, outcome = publish(tmp_path, text, settings=settings)
    with open_generation(location, outcome.project.project_id) as pinned:
        assert_value_parity(pinned, outcome.result)


@pytest.mark.parametrize(("text", "settings"), JSON_CASES)
@pytest.mark.parametrize("backend", ["python", "yajl2_c"])
def test_json_exhaustive_queries_match_scan(
    tmp_path, text, settings, backend, monkeypatch
):
    import ijson

    from tabalyst.scanner.readers import json_reader

    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend(backend))
    location, _, _, outcome = publish(tmp_path, text, suffix=".json", settings=settings)
    with open_generation(location, outcome.project.project_id) as pinned:
        assert_value_parity(pinned, outcome.result)


@pytest.mark.parametrize("enabled", list(itertools.product([False, True], repeat=5)))
def test_every_normalization_stage_combination(tmp_path, enabled):
    text = json.dumps(
        [
            {"v": v}
            for v in [
                " É  CAT ",
                "E\u0301  CAT",
                "é cat",
                "e cat",
                "Straße",
                "STRASSE",
                " A\n B ",
                "A\nB",
                "a",
                "a\x00z",
                "\ue000",
                "\U00010000",
                "😀",
            ]
        ]
    )
    settings = {"normalization": dict(zip(STAGES, enabled, strict=True))}
    location, _, _, outcome = publish(tmp_path, text, suffix=".json", settings=settings)
    with open_generation(location, outcome.project.project_id) as pinned:
        # Equal counts test Python/UTF-8 binary order, including NUL and the
        # BMP/non-BMP boundary (UTF-16 ordering would be wrong here).
        assert_value_parity(pinned, outcome.result)


@pytest.mark.parametrize("mode", ["mask", "hide", "show"])
def test_exposure_before_frequency_and_variant_ranking(tmp_path, mode):
    location, source, config, outcome = publish(
        tmp_path,
        "secret\nSECRET-1111\n SECRET-1111 \nSECRET-2222\n SECRET-2222 \nSECRET-3333\nplain\nplain\n",
        settings={
            "patterns": [{"id": "secret", "regex": r"SECRET-\d{4}", "sensitive": True}],
            "exposure": {"sensitive_values": mode},
        },
    )
    source.unlink()  # Queries require neither the source nor rerunning detectors.
    with open_generation(location, outcome.project.project_id) as pinned:
        assert pinned.result.config == resolve_config_defaults(config, "csv")
        assert_value_parity(pinned, outcome.result)
        with materialize_values(pinned, "rows", "column_1") as query:
            page = query.frequencies_page(size=1)
            if mode == "mask":
                assert page.items[0].value == "AAAAAA-9999"
                assert page.items[0].count == 5
                group = query.groups_page().items[0]
                # Only raw groups with >=2 variants qualify; SECRET-3333
                # must not join the masked group just because its mask agrees.
                assert group.count == 4 and group.distinct == 2
                assert "SECRET" not in repr(page)
                assert "SECRET" not in repr(query.groups_page())
            elif mode == "hide":
                assert page.items == () and page.next_cursor is None
                assert page.total == 4 and page.reason == "sensitive_values_hidden"
                assert query.groups_page().total == 2
                with pytest.raises(QueryError, match="Hidden"):
                    query.variants_page("secret-1111")


def test_typed_ties_and_binary_order(tmp_path):
    location, _, _, outcome = publish(
        tmp_path, '["1",1,1.0,"1.0",true,"true",false,"false"]', suffix=".json"
    )
    with open_generation(location, outcome.project.project_id) as pinned:
        assert_value_parity(pinned, outcome.result)


@pytest.mark.parametrize("limit", ["distinct", "global", "long", "listing"])
def test_complete_queries_recover_released_tables_without_mutating_scan(
    tmp_path, limit
):
    limits = {
        "max_listed_frequencies": 0,
        "max_variant_groups": 0,
        "max_variants_per_group": 0,
    }
    if limit == "distinct":
        limits.update(max_distinct_per_field=1)
    elif limit == "global":
        limits.update(max_distinct_per_field=2, max_tracked_values=2)
    elif limit == "long":
        limits.update(max_stored_value_length=2)
    location, source, config, outcome = publish(
        tmp_path,
        "a,b\n É ,10\nÉ,11\né,12\ne,13\n" + "x" * 5000 + ",14\n",
        settings={"limits": limits},
    )
    full_limits = config.limits.model_dump()
    full_limits.update(
        max_distinct_per_field=1000,
        max_tracked_values=10000,
        max_stored_value_length=10000,
        max_listed_frequencies=1000,
        max_variant_groups=1000,
        max_variants_per_group=1000,
    )
    reference = scan(
        source,
        config=config.model_copy(update={"limits": type(config.limits)(**full_limits)}),
        workers=1,
    )
    before = outcome.scan_path.read_bytes(), _file_hash(outcome.database_path)
    with open_generation(location, outcome.project.project_id) as pinned:
        # Source, presence and scope are identical; only Scan's value limits
        # differ from the exhaustive reference.
        assert_value_parity(pinned, reference)
    assert before == (outcome.scan_path.read_bytes(), _file_hash(outcome.database_path))


def test_many_records_exhausted_budget_and_gaps(tmp_path):
    text = (
        "a,b\n"
        + "\n".join(
            "x" if i % 17 == 0 else (" ," if i % 3 == 0 else "a,b")
            for i in range(13050)
        )
        + "\n"
    )
    location, source, config, outcome = publish(
        tmp_path,
        text,
        settings={
            "errors": {"policy": "tolerant"},
            "limits": {"max_listed_records": 0, "max_tracked_records": 1},
        },
    )
    full = config.limits.model_copy(
        update={"max_listed_records": 10000, "max_tracked_records": 20000}
    )
    reference = scan(
        source, config=config.model_copy(update={"limits": full}), workers=1
    ).datasets[0]
    with open_generation(location, outcome.project.project_id) as pinned:
        for listing in ("with_missing", "empty", "duplicates"):
            page, items = walk(
                lambda listing=listing, **kw: records_page(
                    pinned, "rows", "records." + listing, **kw
                ),
                size=317,
            )
            expected = getattr(reference.records, listing)
            assert page.total == (
                expected.count.value if listing == "duplicates" else expected.count
            )
            indices = [item.record_index for item in items]
            assert indices[:10000] == expected.records
            assert len(set(indices)) == len(indices) == page.total
            assert indices == sorted(indices)
            assert all(item.location["record"] == item.record_index for item in items)
            assert not any((i - 1) % 17 == 0 for i in indices)


def test_cursors_pin_old_generation_and_reject_new_or_other_queries(tmp_path):
    location, source, config, first = publish(
        tmp_path, 'v\n É \né\ne\na\nb\n""\n""\n""\n'
    )
    with open_generation(location, first.project.project_id) as old:
        records = records_page(old, "rows", "records.duplicates", size=1)
        with materialize_values(old, "rows", "column_1") as values:
            frequencies = values.frequencies_page(size=1)
            groups = values.groups_page(size=1)
            variant = values.variants_page(groups.items[0].key, size=1)
            with pytest.raises(StaleCursorError):
                values.groups_page(cursor=frequencies.next_cursor)
            with pytest.raises(StaleCursorError):
                values.frequencies_page(cursor=variant.next_cursor)
        with materialize_values(old, "rows", "column_1") as rebuilt:
            assert rebuilt.frequencies_page(
                size=2, cursor=frequencies.next_cursor
            ).items
        source.write_text('v\n É \né\ne\na\nb\n""\n""\n""\nx\n', encoding="utf-8")
        second = publish_scan(source, location, config, workers=1)
        assert records_page(
            old, "rows", "records.duplicates", cursor=records.next_cursor
        ).items
        with open_generation(location, second.project.project_id) as new:
            with pytest.raises(StaleCursorError):
                records_page(
                    new, "rows", "records.duplicates", cursor=records.next_cursor
                )
            with (
                materialize_values(new, "rows", "column_1") as values,
                pytest.raises(StaleCursorError),
            ):
                values.frequencies_page(cursor=frequencies.next_cursor)
        with pytest.raises(StaleCursorError):
            records_page(old, "rows", "records.empty", cursor=records.next_cursor)
        bad_project = replace(
            records.next_cursor, binding=("other", *records.next_cursor.binding[1:])
        )
        with pytest.raises(StaleCursorError):
            records_page(old, "rows", "records.duplicates", cursor=bad_project)


@pytest.mark.parametrize("size", [0, -1, 1001, True, 1.5, "2"])
def test_page_limits_are_strict(tmp_path, size):
    location, _, _, outcome = publish(tmp_path, "v\na\nb\n")
    with open_generation(location, outcome.project.project_id) as pinned:
        with pytest.raises(QueryError):
            records_page(pinned, "rows", "records.empty", size=size)
        with materialize_values(pinned, "rows", "column_1") as query:
            with pytest.raises(QueryError):
                query.frequencies_page(size=size)
            with pytest.raises(QueryError):
                query.groups_page(size=size)


def test_disabled_duplicates_unknown_fields_and_malformed_cursors(tmp_path):
    location, _, _, outcome = publish(
        tmp_path,
        "v,unprofiled\na,secret\na,secret\n",
        settings={"records": {"duplicates": False}, "limits": {"max_fields": 1}},
    )
    with open_generation(location, outcome.project.project_id) as pinned:
        page = records_page(pinned, "rows", "records.duplicates")
        assert page.status == "disabled" and page.total is None and not page.items
        with pytest.raises(QueryError):
            records_page(pinned, "rows", "records.detector.number")
        with pytest.raises(QueryError):
            records_page(pinned, "unknown", "records.empty")
        with pytest.raises(QueryError), materialize_values(pinned, "rows", "column_2"):
            pytest.fail("Unprofiled payload exposed")
        with (
            materialize_values(pinned, "rows", "column_1") as query,
            pytest.raises(QueryError),
        ):
            query.frequencies_page(
                cursor=Cursor(
                    _queries._binding(query.frequencies_page().scope), (True,)
                )
            )
        with pytest.raises(QueryError, match="closed"):
            query.frequencies_page()


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory_bytes", 0),
        ("spill_bytes", -1),
        ("batch_rows", True),
        ("batch_bytes", 0),
    ],
)
def test_invalid_resource_budgets(field, value):
    with pytest.raises(ValueError):
        QueryBudget(**{field: value})


@pytest.mark.parametrize("spill_bytes", [0, 1024 * 1024])
def test_real_sort_rejects_disabled_or_exhausted_spill(tmp_path, spill_bytes):
    spill = tmp_path / "spill"
    budget = QueryBudget(memory_bytes=32 * 1024 * 1024, spill_bytes=spill_bytes)
    with duckdb.connect(
        str(tmp_path / "query.duckdb"), config=budget.config(spill)
    ) as connection:
        apply_spill_limit(connection, f"{spill_bytes}B")
        if not spill_bytes:
            assert connection.execute(
                "SELECT current_setting('temp_directory')"
            ).fetchone() == ("",)
        with pytest.raises(duckdb.OutOfMemoryException) as error:
            connection.execute(
                "CREATE TEMP TABLE probe AS SELECT i,md5(i::VARCHAR) s FROM range(500000) t(i)"
            )
            connection.execute("SELECT * FROM probe ORDER BY s")
            while connection.fetchmany(1024):
                pass
        if spill_bytes:
            assert "max_temp_directory_size" in str(error.value)
        else:
            assert "no temporary directory" in str(error.value)
            assert not list(spill.glob("*"))


@pytest.mark.parametrize("limit", ["0B", "0GiB"])
def test_loader_zero_spill_disables_its_directory(tmp_path, monkeypatch, limit):
    from tabalyst.projects import _staging

    source = tmp_path / "source.csv"
    source.write_text("v\na\nb\n", encoding="utf-8")
    original = _staging.scan

    def check(*args, **kwargs):
        connection = kwargs["on_record"].records.connection
        assert connection.execute(
            "SELECT current_setting('temp_directory')"
        ).fetchone() == ("",)
        return original(*args, **kwargs)

    monkeypatch.setattr(_staging, "scan", check)
    publish_scan(
        source,
        StorageLocation(tmp_path / "storage"),
        ScanConfig(),
        workers=1,
        spill_limit=limit,
    )


def test_failed_materialization_cleans_only_its_cache_and_never_yields(
    tmp_path, monkeypatch
):
    location, _, _, outcome = publish(tmp_path, "v\na\nb\n")
    cache = location.project_dir(outcome.project.project_id) / "cache"
    cache.mkdir(exist_ok=True)
    sentinel = cache / "unrelated"
    sentinel.write_bytes(b"keep")
    before = outcome.scan_path.read_bytes(), _file_hash(outcome.database_path)
    original = _queries._build_values

    def fail(*args):
        original(*args)
        raise OSError("Disk exhausted")

    monkeypatch.setattr(_queries, "_build_values", fail)
    with open_generation(location, outcome.project.project_id) as pinned:
        with (
            pytest.raises(OSError, match="Disk exhausted"),
            materialize_values(pinned, "rows", "column_1"),
        ):
            pytest.fail("Failure yielded a complete listing")
        assert list(cache.rglob("values.duckdb")) == []
    assert list(cache.rglob("query-*")) == []
    assert sentinel.read_bytes() == b"keep"
    assert before == (outcome.scan_path.read_bytes(), _file_hash(outcome.database_path))


def test_real_memory_failure_is_explicit_and_does_not_publish_partial_values(tmp_path):
    location, _, _, outcome = publish(
        tmp_path, "v\n" + "\n".join(str(i) for i in range(4000)) + "\n"
    )
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        pytest.raises(duckdb.Error, match="allocate|Memory"),
        materialize_values(
            pinned, "rows", "column_1", budget=QueryBudget(memory_bytes=1024 * 1024)
        ),
    ):
        pytest.fail("Memory failure yielded values")
    assert not list(
        location.project_dir(outcome.project.project_id).rglob("values.duckdb")
    )
    with (
        pytest.raises(InputError, match="Cannot open committed project"),
        open_generation(
            location,
            outcome.project.project_id,
            budget=QueryBudget(memory_bytes=1024 * 1024),
        ),
    ):
        pytest.fail("Unbounded validation bypassed reader budget")


def test_maintenance_verification_has_the_default_reader_budget(tmp_path, monkeypatch):
    from tabalyst.projects import _generation

    location, _, _, outcome = publish(
        tmp_path, "v\n" + "\n".join(map(str, range(4000))) + "\n"
    )
    monkeypatch.setattr(
        _generation, "QueryBudget", lambda: QueryBudget(memory_bytes=1024 * 1024)
    )
    with pytest.raises(InputError, match="Cannot open committed project"):
        _generation.verify_generation(location, outcome.project)
    assert not (location.project_dir(outcome.project.project_id) / "cache").exists()


def test_legacy_large_value_and_group_pages_are_exhaustive_after_zero_scan_lists(
    tmp_path, monkeypatch
):
    from tabalyst.projects import _publication

    original = _publication.build_staging

    def legacy(*args, **kwargs):
        kwargs.pop("value_limit")
        return original(*args, **kwargs)

    monkeypatch.setattr(_publication, "build_staging", legacy)
    count = 12500
    text = (
        "v\n" + "\n".join(v for i in range(count) for v in (f"V{i}", f" v{i} ")) + "\n"
    )
    location, _, _, outcome = publish(
        tmp_path,
        text,
        settings={
            "limits": {
                "max_distinct_per_field": 1,
                "max_listed_frequencies": 0,
                "max_variant_groups": 0,
                "max_variants_per_group": 0,
            }
        },
    )
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        assert query.storage[0] == 1
        page, values = walk(query.frequencies_page, size=1000)
        assert page.total == count * 2
        assert [v.value for v in values] == sorted(
            v.strip() for i in range(count) for v in (f"V{i}", f" v{i} ")
        )
        assert all(v.count == 1 and v.type == "string" for v in values)
        page, groups = walk(query.groups_page, size=991)
        assert page.total == count
        assert [g.key for g in groups] == sorted(f"v{i}" for i in range(count))
        assert all(g.count == 2 and g.distinct == 2 for g in groups)
        for group in (groups[0], groups[-1]):
            page, variants = walk(
                lambda key=group.key, **kw: query.variants_page(key, **kw), size=1
            )
            assert page.total == 2
            assert [v.value for v in variants] == [f" {group.key} ", group.key.upper()]


def test_cursor_references_include_dataset_field_and_variant_key(tmp_path):
    location, _, _, outcome = publish(
        tmp_path,
        '{"left":[{"x":" A ","y":" B "},{"x":"a","y":"b"}],'
        '"right":[{"x":" A "},{"x":"a"}]}',
        suffix=".json",
    )
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "$.left[]", "f1") as left,
    ):
        cursor = left.frequencies_page(size=1).next_cursor
        assert cursor is not None
        with (
            materialize_values(pinned, "$.right[]", "f1") as right,
            pytest.raises(StaleCursorError),
        ):
            right.frequencies_page(cursor=cursor)
        with (
            materialize_values(pinned, "$.left[]", "f2") as other,
            pytest.raises(StaleCursorError),
        ):
            other.frequencies_page(cursor=cursor)
    location, _, _, outcome = publish(tmp_path, "v\n A \na\n B \nb\n")
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        cursor = query.variants_page("a", size=1).next_cursor
        with pytest.raises(StaleCursorError):
            query.variants_page("b", cursor=cursor)


@pytest.mark.parametrize(
    "key", [(), (0,), (-1,), (True,), (2**63,), (1, 2), ("1",), None]
)
def test_malformed_keys_are_rejected(tmp_path, key):
    location, _, _, outcome = publish(tmp_path, "v\na\nb\n")
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        binding = _queries._binding(query.frequencies_page().scope)
        with pytest.raises(QueryError):
            query.frequencies_page(cursor=Cursor(binding, key))


@pytest.mark.parametrize("mode", ["show", "mask", "hide"])
def test_bounded_storage_counts_retained_keys_after_saturation(tmp_path, mode):
    location, _, _, outcome = publish(
        tmp_path,
        "v\nSECRET-1111\n SECRET-1111 \nSECRET-2222\nSECRET-3333\nSECRET-4444\nSECRET-1111\n SECRET-1111 \n",
        value_limit=3,
        settings={
            "patterns": [{"id": "secret", "regex": r"SECRET-\d{4}", "sensitive": True}],
            "exposure": {"sensitive_values": mode},
        },
    )
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        assert (
            pinned.connection.execute("SELECT count(*) FROM data.values").fetchone()[0]
            == 3
        )
        stored = pinned.connection.execute(
            "SELECT raw_text,count FROM data.values ORDER BY value_index"
        ).fetchall()
        assert stored == [("SECRET-1111", 2), (" SECRET-1111 ", 2), ("SECRET-2222", 1)]
        page = query.frequencies_page(size=1)
        assert page.status == "limited" and page.reason == "stored_value_budget"
        assert page.scope.stored_distinct_limit == 3
        assert page.scope.value_population == 7
        assert page.scope.retained_occurrences == 5
        assert page.scope.omitted_occurrences == 2
        if mode == "show":
            assert page.items[0].value == "SECRET-1111" and page.items[0].count == 4
        elif mode == "mask":
            assert page.total == 1 and page.items[0].count == 5
            assert query.groups_page().items[0].count == 4
        else:
            assert not page.items and page.next_cursor is None
        assert outcome.result.datasets[0].fields[0].values.count == 7


def test_default_cap_is_10000_and_records_still_cover_every_value(tmp_path):
    n = 12500
    text = "v\n" + "\n".join(map(str, range(n))) + "\n12499\n0\n"
    location, _, _, outcome = publish(tmp_path, text)
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        page, items = walk(query.frequencies_page, size=777, status="limited")
        assert page.total == 10000 and len(items) == 10000
        assert items[0].value == "0" and items[0].count == 2
        assert page.scope.omitted_occurrences == 2501
        assert "12499" not in {i.value for i in items}
        assert [
            i.record_index
            for i in records_page(pinned, "rows", "records.duplicates").items
        ] == [12501, 12502]
        assert (
            pinned.connection.execute("SELECT count(*) FROM data.records").fetchone()[0]
            == 12502
        )


@pytest.mark.parametrize("limit", [0, 10001, True, None])
def test_project_storage_limit_cannot_be_bypassed(tmp_path, limit):
    with pytest.raises(ValueError, match="Stored distinct"):
        publish(tmp_path, "v\na\n", value_limit=limit)


@pytest.mark.parametrize(
    ("rows", "bytes_limit"), [(1, 1), (2, 30), (2048, 4 * 1024 * 1024)]
)
def test_catalog_first_seen_order_is_independent_of_batching(
    tmp_path, monkeypatch, rows, bytes_limit
):
    from tabalyst.projects import _staging

    monkeypatch.setattr(_staging, "BATCH_ROWS", rows)
    monkeypatch.setattr(_staging, "BATCH_BYTES", bytes_limit)
    location, _, _, outcome = publish(
        tmp_path, "v,w\nz,q\na,p\na,q\nb,r\nz,s\nx,q\na,p\n", value_limit=2
    )
    with open_generation(location, outcome.project.project_id) as pinned:
        assert pinned.connection.execute(
            "SELECT field_id,raw_text,count FROM data.values ORDER BY field_id,value_index"
        ).fetchall() == [
            ("column_1", "z", 2),
            ("column_1", "a", 3),
            ("column_2", "q", 3),
            ("column_2", "p", 2),
        ]
        assert pinned.connection.execute(
            "SELECT omitted_occurrences FROM meta.value_storage ORDER BY field_id"
        ).fetchall() == [(2,), (2,)]


def test_omitted_values_can_share_a_retained_analytical_key(tmp_path):
    location, _, _, outcome = publish(tmp_path, "v\na\n a \na\n", value_limit=1)
    with (
        open_generation(location, outcome.project.project_id) as pinned,
        materialize_values(pinned, "rows", "column_1") as query,
    ):
        page = query.frequencies_page()
        assert page.status == "limited" and page.scope.omitted_occurrences == 1
        assert [(v.value, v.count) for v in page.items] == [("a", 2)]
        assert query.groups_page().status == "limited"
        assert query.groups_page().items == ()
        # Scan sees all three occurrences and the otherwise omitted variant.
        field = outcome.result.datasets[0].fields[0]
        assert field.values.frequencies.value.listed[0].count == 3
        assert field.normalization.variant_groups.value.groups == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE meta.value_storage SET retained_occurrences=retained_occurrences+1",
        "UPDATE data.values SET raw_text='' WHERE value_index=1",
        "UPDATE data.records SET location_json='{\"record\":true}' WHERE record_index=1",
        "UPDATE data.records SET duplicate_key=NULL WHERE record_index=1",
        "UPDATE data.records SET is_empty=true,with_missing=false WHERE record_index=1",
    ],
)
def test_bounded_validation_rejects_corrupt_facts(tmp_path, mutation):
    import shutil

    from tabalyst.projects._codec import DatabaseValidationError
    from tabalyst.projects._validation import validate_database

    _, _, _, outcome = publish(tmp_path, "v\na\nb\n", value_limit=1)
    copy = tmp_path / "corrupt.duckdb"
    shutil.copyfile(outcome.database_path, copy)
    with duckdb.connect(str(copy)) as connection:
        connection.execute(mutation)
        with pytest.raises(DatabaseValidationError):
            validate_database(
                connection,
                outcome.result,
                project_id=outcome.project.project_id,
                workspace_id=outcome.project.workspace_id,
                generation_id=outcome.project.generation.id,
                scan_sha256=outcome.project.generation.scan_sha256,
            )
