# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 15: the values that patterns and detectors leave out, and the
repeated values of identifiers and keys (G33 onward).

``residual_values`` keeps the values no pattern reads and the values a detector
finds invalid or does not match, with exact counts and the first record of each
(design 20.20); ``duplicates_report`` lists the repeated values of an identifier
and of a combination of columns (design 20.21). The oracles are built from what
the generator wrote, never from the detectors.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import jsonschema
import pytest
from planner_helpers import by_analyzer
from planner_helpers import scan_csv as _scan_csv
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan

from tabalyst.config import DeepSettings
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.schema import deep_schema
from tabalyst.source_guard import StaleSource

HEADER = "code,born,email"


def scan_csv(directory: Path, header: str, rows, **settings):
    """Scan a CSV written under ``directory``, which is created."""
    directory.mkdir(parents=True, exist_ok=True)
    return _scan_csv(directory, header, rows, **settings)


# Few samples: the Scan does not hold every distinct value, so the second pass
# reads the source and gives the records.
# Three families: the three structures of the codes; the structures of the junk
# values are not published, so no pattern reads them (design 18.12).
PATTERNS = {"pattern_inference": {"max_families": 3}}
READ = {"limits": {"max_samples": 50}, **PATTERNS}
JUNK = ("n/a", "??", "x")


def _code(rng: random.Random, junk: Counter, first: dict) -> str:
    kind = rng.random()
    if kind < 0.55:
        return f"{rng.choice('ABCDE')}{rng.choice('FGHIJ')}{rng.randint(1000, 9999)}"
    if kind < 0.85:
        return f"{rng.randint(100, 999)}-{rng.randint(100, 999)}"
    if kind < 0.97:
        return f"{rng.randint(1000, 9999)}-{rng.choice('KLMNO')}{rng.choice('PQRST')}"
    return rng.choice(JUNK)


def _born(rng: random.Random, junk: Counter, first: dict) -> str:
    kind = rng.random()
    year = rng.randint(1940, 2005)
    if kind < 0.9:
        return f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    if kind < 0.95:
        return f"{year}-02-3{rng.randint(0, 1)}"
    return "unknown"


def _email(rng: random.Random, junk: Counter, first: dict) -> str:
    if rng.random() < 0.05:
        return "not-an-email"
    return f"user{rng.randint(1, 500)}@example.com"


def _rows(count: int = 3_000, seed: int = 15) -> tuple[list[str], dict]:
    """The rows, and what the generator left out: per column, the counts and
    first record of each value it wrote that a pattern or a detector rejects."""
    rng = random.Random(seed)
    left_out: dict[str, dict[str, list[int]]] = {"code": {}, "born_invalid": {}, "born_other": {}}
    rows = []
    for record in range(1, count + 1):
        code = _code(rng, Counter(), {})
        born = _born(rng, Counter(), {})
        rows.append(f"{code},{born},{_email(rng, Counter(), {})}")
        if code in JUNK:
            slot = left_out["code"].setdefault(code, [0, record])
            slot[0] += 1
        if born == "unknown":
            slot = left_out["born_other"].setdefault(born, [0, record])
            slot[0] += 1
        elif born[5:7] == "02" and born[8:] in ("30", "31"):
            slot = left_out["born_invalid"].setdefault(born, [0, record])
            slot[0] += 1
    return rows, left_out


def _deep(tmp_path: Path, rows: list[str], deep: DeepSettings | None = None, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, HEADER, rows, **settings)
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
    return result, plan, outcome


def _residuals(outcome, display: str):
    found = entry(outcome, "residual_values", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _table(result, source: str, state: str, detector: str | None = None):
    found = [
        t for t in result.tables
        if t.source == source and t.state == state and t.detector == detector
    ]
    assert len(found) == 1, [(t.source, t.state, t.detector) for t in result.tables]
    return found[0]




def _ranked(oracle: dict, limit: int = 20) -> list[tuple[str, int, int]]:
    ordered = sorted(oracle.items(), key=lambda item: (-item[1][0], item[0]))
    return [(value, slot[0], slot[1]) for value, slot in ordered[:limit]]


def _listed(table) -> list[tuple[str, int, int | None]]:
    return [(v.value, v.count, v.first_record) for v in table.listed]


def _counts(result) -> dict:
    """The result without what the source alone holds: the records and the
    examples."""
    data = result.model_dump(mode="json", exclude={"computed_from", "records"})
    for table in data["tables"]:
        for value in table["listed"]:
            value.pop("first_record", None)
    # The patterns follow the sample the inference read, so their ids differ.
    for pattern in data.get("patterns") or ():
        for name in ("id", "example", "first_record"):
            pattern.pop(name, None)
    if data.get("patterns"):
        data["patterns"].sort(key=lambda pattern: pattern["render"])
    return data


# G33 to G37: the oracle ----------------------------------------------------------


def test_G33_the_values_no_pattern_reads_have_exact_counts_and_first_records(tmp_path):
    rows, left_out = _rows()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _residuals(outcome, "code")
    table = _table(result, "pattern", "other")

    assert result.computed_from == "source" and result.records is True
    assert table.occurrences == sum(slot[0] for slot in left_out["code"].values())
    assert (table.distinct, table.complete, table.truncated) == (3, True, False)
    assert _listed(table) == _ranked(left_out["code"])
    assert result.accuracy == "exact" and result.values == len(rows)
    # No value is both read by a pattern and left out.
    assert sum(p.occurrences for p in result.patterns) + table.occurrences == len(rows)


def test_G34_a_detector_gives_its_invalid_and_unmatched_values_and_the_reasons(tmp_path):
    rows, left_out = _rows()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _residuals(outcome, "born")

    invalid = _table(result, "detector", "invalid", "date")
    assert invalid.occurrences == sum(slot[0] for slot in left_out["born_invalid"].values())
    assert invalid.distinct == len(left_out["born_invalid"]) and invalid.truncated
    assert _listed(invalid) == _ranked(left_out["born_invalid"])
    assert [(r.reason, r.count) for r in invalid.reasons] == [
        ("invalid_calendar_date", invalid.occurrences)
    ]
    unmatched = _table(result, "detector", "not_matched", "date")
    assert _listed(unmatched) == _ranked(left_out["born_other"])

    tally = next(d for d in result.detectors if d.detector == "date")
    assert (tally.invalid, tally.not_matched) == (invalid.occurrences, unmatched.occurrences)
    assert tally.eligible == len(rows) and tally.scan_not_tested == 0


def test_G35_the_scan_alone_gives_the_counts_when_it_holds_every_value(tmp_path):
    rows, _ = _rows()
    _, plan, from_samples = _deep(tmp_path / "samples", rows, **PATTERNS)
    _, _, from_source = _deep(tmp_path / "source", rows, **READ)

    for display in ("code", "born"):
        samples = _residuals(from_samples, display)
        assert samples.computed_from == "samples" and samples.records is False
        assert all(v.first_record is None for t in samples.tables for v in t.listed)
        if display == "code":
            assert all(p.first_record is None and p.example is not None for p in samples.patterns)
        counts, expected = _counts(samples), _counts(_residuals(from_source, display))
        if display == "born":
            # Whether a pattern read `unknown` depends on the sample the discovery
            # saw (it is a family of its own in the complete scan): the detector
            # tables are what both ways must agree on.
            for item in (counts, expected):
                item.pop("patterns", None)
                item.pop("pattern_excluded", None)
        assert counts == expected
    candidate = by_analyzer(plan, "residual_values")["code"]
    assert candidate.execution.requires_source is False
    assert "derivable_from_samples" in candidate.utility.reasons


def test_G36_asking_for_the_records_reads_the_source_even_when_the_scan_holds_the_values(tmp_path):
    rows, left_out = _rows()
    deep = DeepSettings.model_validate({"residuals": {"records": True}})
    _, plan, outcome = _deep(tmp_path, rows, deep, **PATTERNS)

    assert by_analyzer(plan, "residual_values")["code"].execution.requires_source is True
    result = _residuals(outcome, "code")
    assert result.computed_from == "source" and result.records is True
    assert _listed(_table(result, "pattern", "other")) == _ranked(left_out["code"])


def test_G37_each_pattern_has_an_example_a_first_record_and_its_distinct_values(tmp_path):
    import re

    rows, _ = _rows()
    _, _, outcome = _deep(tmp_path, rows, **READ)
    result = _residuals(outcome, "code")
    shapes = {
        "AA9999": re.compile(r"[A-Z]{2}\d{4}"),
        "999-999": re.compile(r"\d{3}-\d{3}"),
        "9999-AA": re.compile(r"\d{4}-[A-Z]{2}"),
    }
    codes = [row.split(",")[0] for row in rows]
    assert {p.render for p in result.patterns} == set(shapes)
    for profile in result.patterns:
        mine = [(n, c) for n, c in enumerate(codes, 1) if shapes[profile.render].fullmatch(c)]
        assert profile.occurrences == len(mine)
        assert profile.distinct == len({c for _, c in mine}) and profile.distinct_accuracy == "exact"
        assert (profile.first_record, profile.example) == mine[0]
    assert result.pattern_excluded.model_dump() == {"non_string": 0, "too_long": 0, "too_complex": 0}


# G38 and G39: the bounds ------------------------------------------------------------


def test_G38_beyond_the_tracked_values_only_the_occurrences_are_counted(tmp_path):
    rows, left_out = _rows()
    deep = DeepSettings.model_validate({"residuals": {"max_tracked": 2}})
    _, _, outcome = _deep(tmp_path, rows, deep, **READ)
    table = _table(_residuals(outcome, "code"), "pattern", "other")

    # ``n/a`` (record 13) and ``x`` (23) came first; ``??`` (169) found the table full.
    assert table.complete is False and table.distinct == 2
    assert table.untracked == left_out["code"]["??"][0]
    assert _listed(table) == _ranked({k: v for k, v in left_out["code"].items() if k != "??"})
    assert table.occurrences == sum(slot[0] for slot in left_out["code"].values())
    assert sum(v.count for v in table.listed) + table.untracked == table.occurrences
    result = _residuals(outcome, "code")
    assert result.accuracy == "exact_counts"


def test_G39_a_long_value_is_counted_and_never_listed(tmp_path):
    rows, left_out = _rows()
    deep = DeepSettings.model_validate({"residuals": {"max_value_length": 2}})
    _, _, outcome = _deep(tmp_path, rows, deep, **READ)
    table = _table(_residuals(outcome, "code"), "pattern", "other")

    assert table.too_long == left_out["code"]["n/a"][0] and table.complete is False
    assert {v.value for v in table.listed} == {"x", "??"}
    assert table.occurrences == sum(slot[0] for slot in left_out["code"].values())
    assert [e for e in (v for v in table.listed) if len(e.value) > 2] == []


# G40 to G48: workers, JSON, the Scan, reuse ---------------------------------------


def test_G40_the_workers_give_the_result_of_one_process_and_the_same_records(tmp_path):
    rng = random.Random(40)

    def day() -> str:
        year, kind = rng.randint(1940, 2005), rng.random()
        if kind < 0.97:
            return f"{year}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        return f"{year}-02-30"

    rows = [f"{day()},{day()},{n}" for n in range(4_000)]
    # Without patterns (dates are eligible for them, AC-002), no exact set.
    result = scan_csv(
        tmp_path, "first,second,n", rows, pattern_inference={"enabled": False}, limits=READ["limits"]
    )
    plan = forced_plan(result)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    # No pattern, so no exact set: the two routes of dates go to workers.
    assert result.derived is None
    assert shared.document.run.workers == 3
    found = _residuals(shared, "first")
    assert found.records and found.tables[0].listed[0].first_record is not None
    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]


def test_G41_an_accumulator_without_exact_sets_travels_to_a_worker_and_back():
    import pickle

    from tabalyst.scanner.secondpass.parallel import part_name
    from tabalyst.scanner.secondpass.residuals import ResidualAccumulator

    accumulator = ResidualAccumulator(
        entry=None,
        pattern_max_length=64,
        detectors=["date"],
        pool=None,  # type: ignore[arg-type]
        max_listed=5,
        max_tracked=10,
        max_value_length=20,
    )
    again = pickle.loads(pickle.dumps(accumulator))
    assert part_name(again) == "residuals" and again.uses_pool is False and again.needs_text


def test_G42_a_json_source_numbers_its_records_from_one(tmp_path):
    from tabalyst.scanner import ScanConfig, scan

    lines = [json.dumps({"id": n, "day": f"2024-01-{n % 28 + 1:02d}"}) for n in range(1, 41)]
    lines[6] = json.dumps({"id": 7, "day": "2024-02-31"})
    lines[19] = json.dumps({"id": 20, "day": "soon"})
    lines[29] = json.dumps({"id": 30, "day": "2024-02-31"})
    source = write_text(tmp_path, "data.jsonl", "\n".join(lines) + "\n")
    result = scan(source, config=ScanConfig.model_validate({"limits": {"max_samples": 10}}))
    outcome = run_second_pass(result, source, forced_plan(result))
    found = _residuals(outcome, "day")

    invalid = _table(found, "detector", "invalid", "date")
    assert _listed(invalid) == [("2024-02-31", 2, 7)]
    assert _listed(_table(found, "detector", "not_matched", "date")) == [("soon", 1, 20)]


def test_G43_a_sensitive_field_is_left_out_and_no_value_reaches_the_document(tmp_path):
    rows, _ = _rows()
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    plan = plan_analyses(result, forced=True)
    email = by_analyzer(plan, "residual_values").get("email")
    assert email is not None and email.applicability.reasons == ["sensitive_exposure"]
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))

    assert "not-an-email" not in deep_document(outcome.document)
    assert all(
        a.display != "email" for a in outcome.document.analyses if a.analyzer == "residual_values"
    )


def test_G44_a_result_is_reused_by_key_and_only_a_changed_setting_computes_it_again(tmp_path):
    rows, _ = _rows(800)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    first = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    same = run_second_pass(
        result, tmp_path / "data.csv", forced_plan(result), previous=first.document
    )
    assert not same.executed and not same.read_source

    deep = DeepSettings.model_validate({"residuals": {"max_listed": 2}})
    again = run_second_pass(
        result,
        tmp_path / "data.csv",
        forced_plan(result, deep),
        settings=deep,
        previous=first.document,
    )
    assert {i.split(":")[0] for i in again.executed} == {"residual_values"}
    assert len(_table(_residuals(again, "code"), "pattern", "other").listed) == 2


def test_G45_a_source_changed_after_the_scan_publishes_nothing(tmp_path):
    rows, _ = _rows(500)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    plan = forced_plan(result)
    source = tmp_path / "data.csv"
    text = source.read_text(encoding="utf-8")
    # Same size, other content: only the digest of the reading can tell.
    source.write_text(text.replace("n/a", "n/b"), encoding="utf-8", newline="")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_G46_counts_that_disagree_with_the_detector_of_the_scan_fail_the_analysis(tmp_path):
    from planner_helpers import with_field

    from tabalyst.scanner.models import Coverage

    rows, _ = _rows(600)
    result = scan_csv(tmp_path, HEADER, rows, **READ)
    column = next(f for f in result.datasets[0].fields if f.display == "born")
    date = next(d for d in column.detectors if d.id == "date")
    coverage = date.coverage

    def edited(**changes):
        changed = date.model_copy(
            update={"coverage": Coverage(**{**coverage.model_dump(), **changes})}
        )
        detectors = [changed if d.id == "date" else d for d in column.detectors]
        return with_field(result, "born", detectors=detectors)

    wrong_scan = edited(invalid=coverage.invalid - 1)
    wrong = run_second_pass(wrong_scan, tmp_path / "data.csv", forced_plan(wrong_scan))
    failed = entry(wrong, "residual_values", "born")
    assert (failed.status, failed.reason) == ("failed", "scan_mismatch")

    # Values the Scan did not test may add what it did not count, and no more.
    untested = edited(invalid=coverage.invalid - 2, matched=coverage.matched - 1, not_tested=3)
    bounded = run_second_pass(untested, tmp_path / "data.csv", forced_plan(untested))
    assert entry(bounded, "residual_values", "born").status == "complete"
    assert _residuals(bounded, "born").detectors[0].scan_not_tested == 3


def test_G47_the_document_follows_its_schema_and_the_report_summarises_it(tmp_path):
    from tabalyst.report_deep import result_summary

    rows, _ = _rows(500)
    _, _, outcome = _deep(tmp_path, rows, **READ)

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(_residuals(outcome, "code"))
    assert "values left out" in summary and "3 patterns profiled" in summary


def test_G48_the_replay_of_every_detector_agrees_with_the_coverage_of_the_scan(tmp_path):
    """Each replayable detector, replayed on strings of every kind, finds in each
    state the occurrences the first pass counted: ``result`` raises otherwise."""
    from tabalyst.scanner.detectors.registry import replayable
    from tabalyst.scanner.secondpass.exactset import ExactPool
    from tabalyst.scanner.secondpass.replay import CellReader
    from tabalyst.scanner.secondpass.residuals import (
        ResidualAccumulator,
        derive_from_samples,
    )

    rng = random.Random(48)
    pool = [
        "2024-03-09", "09/03/2024", "2024-13-45", "12", "-4.5", "1,234.50", "3.14", "abc",
        "a@b.com", "bad@", "https://x.org/p", "http://", "192.168.0.1", "999.1.1.1",
        "123e4567-e89b-12d3-a456-426614174000", "not-a-uuid", "+1 514 555 0100",
        "(514) 555-0100", "H2X 1Y4", "10001", "true", "no", "$12.50", "12 %", "5 kg",
        "x" * 300, "N/A",
    ]
    rows = [f'"{rng.choice(pool)}"' for _ in range(1_500)]
    result = scan_csv(tmp_path, "mixed", rows, exposure={"sensitive_values": "show"})
    field = result.datasets[0].fields[0]
    reader = CellReader(result.config)
    checked = 0
    for detector in field.detectors:
        if detector.id not in replayable() or detector.status != "complete":
            continue
        accumulator = ResidualAccumulator(
            entry=None,
            pattern_max_length=64,
            detectors=[detector.id],
            pool=ExactPool(1 << 40),
            max_listed=5,
            max_tracked=100,
            max_value_length=50,
        )
        derive_from_samples(accumulator, field, reader)
        accumulator.result(field, "samples", False)
        checked += 1
    assert checked >= 5


# G49 to G60: the repeated values of identifiers and keys --------------------------

KEY_HEADER = "uid,client,year,note"


def _ids(count: int = 2_000, seed: int = 49):
    """Rows with an identifier that repeats for some values, two columns that make
    a key but for a few rows, and a note. Returns the rows and, per value of the
    identifier and per combination, its count and first record."""
    rng = random.Random(seed)
    uids = [f"u-{n:06x}" for n in range(count)]
    for value in rng.sample(uids, 40):
        for _ in range(rng.randint(1, 3)):
            uids[rng.randrange(count)] = value
    rows, keys = [], Counter()
    first_key: dict[tuple[str, str], int] = {}
    incomplete = 0
    for record, uid in enumerate(uids, 1):
        client = f"c{rng.randint(1, 60)}"
        year = str(rng.randint(2000, 2040))
        if rng.random() < 0.02:
            client = ""
        if client and year:
            keys[(client, year)] += 1
            first_key.setdefault((client, year), record)
        else:
            incomplete += 1
        rows.append(f"{uid},{client},{year},{rng.choice(['a', 'b'])}")
    counts = Counter(uids)
    first: dict[str, int] = {}
    for record, uid in enumerate(uids, 1):
        first.setdefault(uid, record)
    return rows, counts, first, keys, first_key, incomplete


def _repeated(counts: Counter, first: dict) -> dict[str, list[int]]:
    return {v: [c, first[v]] for v, c in counts.items() if c > 1}


def _dups(outcome, display: str):
    found = entry(outcome, "duplicates_report", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _dupes(result):
    return [(v.value, v.count, v.first_record) for v in result.repeated.listed]


def test_G49_the_planner_proposes_the_report_for_identifiers_and_skips_proven_unique_ones(tmp_path):
    rows, *_ = _ids()
    unique = [f"u-{n},{n % 7}" for n in range(300)]
    plan = plan_analyses(scan_csv(tmp_path / "plain", "uid,tag", unique))
    candidates = by_analyzer(plan, "duplicates_report")
    assert set(candidates) == {"uid"}
    assert candidates["uid"].selection.state == "already_satisfied"
    assert candidates["uid"].selection.reason == "all_distinct"

    result = scan_csv(tmp_path / "repeated", KEY_HEADER, rows)
    proposed = by_analyzer(plan_analyses(result), "duplicates_report")
    candidate = proposed["uid"]
    assert set(proposed) == {"uid"}
    assert candidate.method == "digest_table"
    assert candidate.parameters == {"max_listed": 20, "max_tracked": 10_000, "records": 0}
    assert candidate.execution.requires_source is False
    assert candidate.selection.state == "selected" and candidate.selection.reason == "automatic"
    read = scan_csv(tmp_path / "read", KEY_HEADER, rows, **READ)
    reading = by_analyzer(plan_analyses(read), "duplicates_report")
    assert reading["uid"].execution.requires_source is True


def test_G50_the_repeated_values_have_exact_counts_and_first_records(tmp_path):
    rows, counts, first, *_ = _ids()
    result = scan_csv(tmp_path, KEY_HEADER, rows, **READ)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))
    found = _dups(outcome, "uid")
    repeated = _repeated(counts, first)

    assert found.computed_from == "source" and found.records is True and found.accuracy == "exact"
    assert (found.values, found.distinct) == (len(rows), len(counts))
    assert found.redundant == len(rows) - len(counts) and found.unique is False
    assert found.repeated.distinct == len(repeated)
    assert found.repeated.occurrences == sum(c for c, _ in repeated.values())
    expected = sorted(repeated.items(), key=lambda item: (-item[1][0], item[0]))[:20]
    assert _dupes(found) == [(v, c, r) for v, (c, r) in expected]
    assert found.repeated.complete and found.repeated.truncated


def test_G51_the_scan_alone_gives_the_counts_when_it_holds_every_value(tmp_path):
    rows, *_ = _ids()
    result = scan_csv(tmp_path / "samples", KEY_HEADER, rows)
    from_samples = run_second_pass(result, tmp_path / "samples" / "data.csv", forced_plan(result))
    read = scan_csv(tmp_path / "source", KEY_HEADER, rows, **READ)
    from_source = run_second_pass(read, tmp_path / "source" / "data.csv", forced_plan(read))

    found = _dups(from_samples, "uid")
    assert found.computed_from == "samples" and found.records is False
    assert all(v.first_record is None for v in found.repeated.listed)
    left = found.model_dump(mode="json", exclude={"computed_from", "records"})
    right = _dups(from_source, "uid").model_dump(
        mode="json", exclude={"computed_from", "records"}
    )
    for side in (left, right):
        for value in side["repeated"]["listed"]:
            value.pop("first_record", None)
    assert left == right


def test_G52_asking_for_the_records_reads_the_source_even_when_the_scan_holds_the_values(tmp_path):
    rows, _, first, *_ = _ids()
    deep = DeepSettings.model_validate({"duplicates": {"records": True}})
    result = scan_csv(tmp_path, KEY_HEADER, rows)
    plan = forced_plan(result, deep)
    assert by_analyzer(plan, "duplicates_report")["uid"].execution.requires_source is True
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
    found = _dups(outcome, "uid")
    assert found.computed_from == "source"
    assert _dupes(found)[0][2] == first[_dupes(found)[0][0]]


def test_G53_beyond_the_tracked_values_only_the_occurrences_are_counted(tmp_path):
    rows, counts, first, *_ = _ids()
    deep = DeepSettings.model_validate({"duplicates": {"max_tracked": 5}})
    result = scan_csv(tmp_path, KEY_HEADER, rows, **READ)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, deep), settings=deep)
    found = _dups(outcome, "uid")
    repeated = _repeated(counts, first)

    assert found.accuracy == "exact_counts" and found.repeated.complete is False
    assert found.repeated.tracked == 5 and found.repeated.distinct == len(repeated)
    assert found.repeated.occurrences == sum(c for c, _ in repeated.values())
    assert (
        sum(v.count for v in found.repeated.listed) + found.repeated.untracked
        == found.repeated.occurrences
    )
    # What is tracked is exact: the first five to repeat, in the order of the file.
    for value, count, record in _dupes(found):
        assert (count, record) == tuple(repeated[value])
    assert found.distinct == len(counts)


def test_G54_a_search_the_budget_stops_proves_a_lower_bound_and_nothing_more():
    from tabalyst.scanner.secondpass.duplicates import DuplicateAccumulator
    from tabalyst.scanner.secondpass.exactset import ExactPool
    from tabalyst.scanner.secondpass.models import DuplicatesLimited

    pool = ExactPool(20_000)
    accumulator = DuplicateAccumulator(pool, max_listed=5, max_tracked=100)
    values = [f"value-{n % 5_000}" for n in range(20_000)]
    for start in range(0, len(values), 100):
        batch = values[start : start + 100]
        accumulator.add_strings(batch, [1] * len(batch), lambda raw: 1)
    result = accumulator.result(len(values), None, "source", True)

    assert isinstance(result, DuplicatesLimited) and result.accuracy == "lower_bound"
    assert 0 < result.distinct < 5_000 and result.values_read < len(values)
    assert pool.used == 0
    # A stopped search takes no more values.
    accumulator.add_strings(["more"], [1], lambda raw: 1)
    assert accumulator.values == result.values_read


def test_G55_json_values_keep_their_type_and_their_record(tmp_path):
    from tabalyst.scanner import ScanConfig, scan

    values = ["a", 7, "7", 7, "b", "a", True, True, 2.5, 2.5]
    lines = [json.dumps({"id": value}) for value in values]
    source = write_text(tmp_path, "data.jsonl", "\n".join(lines) + "\n")
    result = scan(source, config=ScanConfig.model_validate({"limits": {"max_samples": 3}}))
    deep = DeepSettings.model_validate({"duplicates": {"max_listed": 10}})
    plan = forced_plan(result, deep)
    candidate = by_analyzer(plan, "duplicates_report")
    assert "id" in candidate
    found = _dups(run_second_pass(result, source, plan, settings=deep), "id")

    # 7 and "7" are two values, and so are True and the string "True".
    assert (found.values, found.distinct) == (10, 6)
    assert sorted(_dupes(found), key=lambda item: item[2]) == [
        ("a", 2, 1),
        ("7", 2, 2),
        ("True", 2, 7),
        ("2.5", 2, 9),
    ]


def test_G56_a_combination_of_two_columns_has_its_repeated_rows_and_the_incomplete_ones(tmp_path):
    from tabalyst.scanner.planner import AnalysisRequest, default_registry

    rows, _, _, keys, first_key, incomplete = _ids()
    result = scan_csv(tmp_path, KEY_HEADER, rows)
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("duplicates_report", field="client", partner="year")],
        forced=True,
        registry=default_registry().runnable(),
    )
    pair = [c for c in plan.candidates if c.analyzer == "duplicates_report" and c.partner]
    assert [c.display for c in pair] == ["client and year"] and pair[0].execution.requires_source
    outcome = run_second_pass(result, tmp_path / "data.csv", plan)
    found = _dups(outcome, "client and year")

    repeated = {k: v for k, v in keys.items() if v > 1}
    assert found.columns == ["client", "year"] and found.incomplete == incomplete
    assert found.values == len(rows) - incomplete
    assert found.distinct == len(keys) and found.redundant == sum(keys.values()) - len(keys)
    assert found.repeated.distinct == len(repeated)
    expected = sorted(repeated.items(), key=lambda item: (-item[1], item[0]))[:20]
    assert [(tuple(v.value), v.count, v.first_record) for v in found.repeated.listed] == [
        (key, count, first_key[key]) for key, count in expected
    ]


def test_G57_two_combinations_never_share_a_text(tmp_path):
    from tabalyst.scanner.planner import AnalysisRequest, default_registry

    rows = ["ab,c", "a,bc", "ab,c", "a|b,c", "a,b|c", "x,y", "x,y"]
    result = scan_csv(tmp_path, "left,right", rows)
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("duplicates_report", field="left", partner="right")],
        forced=True,
        registry=default_registry().runnable(),
    )
    found = _dups(run_second_pass(result, tmp_path / "data.csv", plan), "left and right")
    assert sorted((tuple(v.value), v.count, v.first_record) for v in found.repeated.listed) == [
        (("ab", "c"), 2, 1),
        (("x", "y"), 2, 6),
    ]
    assert found.distinct == 5


def test_G58_a_request_for_a_combination_is_checked_and_never_proposed_by_itself(tmp_path):
    from tabalyst.errors import ConfigurationError
    from tabalyst.scanner.planner import AnalysisRequest

    rows, *_ = _ids(300)
    result = scan_csv(tmp_path, KEY_HEADER, rows)
    plain = plan_analyses(result)
    assert all(c.partner is None for c in plain.candidates if c.analyzer == "duplicates_report")
    requested = plan_analyses(
        result, requests=[AnalysisRequest("duplicates_report", field="client", partner="year")]
    )
    pair = [c for c in requested.candidates if c.analyzer == "duplicates_report" and c.partner]
    assert len(pair) == 1 and pair[0].selection.state == "selected"
    assert pair[0].selection.reason == "requested"
    assert requested.objective.requested[0].candidates == 1
    with pytest.raises(ConfigurationError):
        plan_analyses(
            result, requests=[AnalysisRequest("duplicates_report", field="client", partner="nope")]
        )
    hidden = plan_analyses(
        scan_csv(tmp_path / "hidden", ["id,mail", ""][0], ["1,a@b.com"]),
        requests=[AnalysisRequest("duplicates_report", field="id", partner="mail")],
    )
    assert [c.applicability.reasons for c in hidden.candidates if c.partner] == [
        ["sensitive_exposure"]
    ]


def test_G59_the_workers_and_one_reading_serve_the_whole_run(tmp_path, monkeypatch):
    rows, *_ = _ids(3_000)
    result = scan_csv(tmp_path, KEY_HEADER, rows, **READ)
    plan = forced_plan(result)
    opened = []
    from tabalyst.scanner.readers import factory
    from tabalyst.scanner.secondpass import executor

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    assert len(opened) == 2
    assert {"duplicates_report", "residual_values"} <= {a.analyzer for a in alone.document.analyses}
    assert [a.model_dump(mode="json") for a in shared.document.analyses] == [
        a.model_dump(mode="json") for a in alone.document.analyses
    ]


def test_G60_the_document_follows_its_schema_and_the_report_summarises_it(tmp_path):
    from tabalyst.report_deep import result_summary

    rows, *_ = _ids()
    result = scan_csv(tmp_path, KEY_HEADER, rows, **READ)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result))

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(entry(outcome, "duplicates_report", "uid").result)
    assert "found more than once" in summary and "extra occurrences" in summary


def test_G61_the_cost_follows_the_distinct_values_and_a_wide_replay_is_never_automatic(tmp_path):
    from datetime import date, timedelta

    from tabalyst.scanner.planner.costmodel import NS_PER_CELL

    few = [f"{'AB'[n % 2]}{n % 20:02d}" if n % 50 else "n/a" for n in range(600)]
    # One family: the structure of `n/a` is not published, so a pattern leaves it out.
    plan = plan_analyses(
        scan_csv(tmp_path / "few", "code", few, limits=READ["limits"], pattern_inference={"max_families": 1})
    )
    candidate = by_analyzer(plan, "residual_values")["code"]
    assert candidate.costs.cell_ns == NS_PER_CELL["residual_pattern_few"]
    assert candidate.costs.cpu == "low" and candidate.selection.state == "selected"

    start = date(1900, 1, 1)
    days = [
        (start + timedelta(days=n)).isoformat() if n % 30 else "2000-02-30" for n in range(20_000)
    ]
    wide = scan_csv(tmp_path / "wide", "day", days, **READ)
    auto = by_analyzer(plan_analyses(wide), "residual_values")["day"]
    # Dates are eligible for patterns (AC-002): the replay of the detector and
    # the pattern share the reading of a cell.
    assert auto.costs.cell_ns == NS_PER_CELL["residual_wide"] + round(
        0.3 * NS_PER_CELL["residual_pattern_wide"]
    )
    assert auto.costs.cpu == "high"
    assert (auto.selection.state, auto.selection.reason) == ("rejected", "cpu_class")
    forced = by_analyzer(plan_analyses(wide, forced=True), "residual_values")["day"]
    assert forced.selection.state == "selected" and forced.selection.reason == "forced"
