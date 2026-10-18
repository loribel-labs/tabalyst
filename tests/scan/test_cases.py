# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cases of the observed rules: the class sampler, the collector, their output in
the Scan, the memory budget, the exposure and the validation (design 18.15, lot K1)."""

import json
import random
from collections import Counter, defaultdict

import pytest
from scan_helpers import dataset, field, run_scan, write_text

from tabalyst.scanner import bottomk
from tabalyst.scanner.cases import CaseCollector, ClassSampler
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.memory import (
    CASE_CLASS_BYTES,
    CASE_SHARE,
    SampleBudget,
)
from tabalyst.scanner.memory import (
    SAMPLE_ENTRY_BYTES as SAMPLE_ENTRY,
)
from tabalyst.scanner.validation import check_scan

SECRET = {"id": "secret", "regex": r"S-\d{2}", "sensitive": True}
# A field of a few thousand values is a bottom-k with these limits.
RELEASED = {"max_distinct_per_field": 1_000, "max_samples": 200}


def _csv(tmp_path, rows, name="v.csv"):
    return write_text(tmp_path, name, "v\n" + "\n".join(rows) + "\n")


def _samples(result, name="v"):
    return field(dataset(result, "rows"), name)["values"]["samples"]


def _check(result):
    from tabalyst.scanner.models import ScanResult

    return check_scan(ScanResult.model_validate(result))


def _ids(count, special=None):
    """``count`` distinct identifiers of one length; ``special`` maps a position
    to the text found there."""
    special = special or {}
    return [special.get(n, f"CLI-{n:06d}") for n in range(count)]


def _case(block, kind):
    return next(item for item in block["whitespace"] if item["kind"] == kind)


def _oracle(texts, counts, k, seed=42):
    """The k smallest priorities of a class with their exact counts."""
    table = Counter()
    for text, count in zip(texts, counts, strict=True):
        table[("string", text)] += count
    ranked = sorted(table, key=lambda key: (bottomk.priority(key, seed=seed), key))
    return [(key[1], table[key]) for key in ranked[:k]]


# The class sampler ---------------------------------------------------------------


def test_a_class_keeps_the_smallest_priorities_of_its_cells_with_exact_counts():
    rng = random.Random(3)
    texts = [f"t{n}" for n in range(400)]
    counts = [rng.randint(1, 5) for _ in texts]
    classes = [n % 3 for n in range(400)]
    sampler = ClassSampler(4, 10, seed=7)

    for start in range(0, 400, 90):
        end = start + 90
        sampler.update(classes[start:end], texts[start:end], counts[start:end])

    assert sorted(sampler.tracked) == [0, 1, 2]
    for name in range(3):
        members = [n for n in range(400) if classes[n] == name]
        tracked = sampler.tracked[name]
        assert tracked.occurrences == sum(counts[n] for n in members)
        entries = [
            (entry.key[1], entry.count) for entry in tracked.sampler.entries()
        ]
        assert entries == _oracle(
            [texts[n] for n in members], [counts[n] for n in members], 4, seed=7
        )


def test_the_batches_do_not_change_the_classes():
    texts = [f"t{n}" for n in range(300)]
    counts = [1 + n % 4 for n in range(300)]
    classes = [n % 5 for n in range(300)]

    def run(size):
        sampler = ClassSampler(3, 10, seed=1)
        for start in range(0, 300, size):
            end = start + size
            sampler.update(classes[start:end], texts[start:end], counts[start:end])
        return {
            name: (
                tracked.occurrences,
                [(entry.key, entry.count) for entry in tracked.sampler.entries()],
            )
            for name, tracked in sampler.tracked.items()
        }

    assert run(7) == run(300) == run(64)


def test_classes_beyond_the_cap_are_summed_in_other():
    sampler = ClassSampler(2, 2, seed=0)

    sampler.update([1, 2, 3, 3, 1], list("abcde"), [4, 1, 7, 2, 3])

    assert sorted(sampler.tracked) == [1, 2]
    assert sampler.tracked[1].occurrences == 7
    assert sampler.other_classes == {3}
    assert sampler.other_occurrences == 9


def test_a_muted_class_counts_its_cells_and_keeps_no_text():
    sampler = ClassSampler(2, 5, seed=0)
    sampler.muted = 1

    sampler.update([1, 2, 1], ["a", "b", "c"], [3, 1, 2])

    assert sampler.tracked[1].occurrences == 5 and sampler.tracked[1].sampler is None
    assert [e.key[1] for e in sampler.tracked[2].sampler.entries()] == ["b"]


def test_a_size_of_zero_counts_the_cells_without_hashing_any_text():
    sampler = ClassSampler(0, 5, seed=0)

    sampler.update([1, 1], ["a", "b"], [3, 2])

    assert sampler.tracked[1].occurrences == 5 and sampler.tracked[1].sampler is None


# In the Scan ---------------------------------------------------------------------


def test_two_cells_with_a_trailing_space_in_a_big_field_are_both_listed(tmp_path):
    rows = _ids(6_000, {17: "CLI-000017 ", 4_000: "CLI-004000  "})
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    samples = _samples(result)
    block = samples["cases"]

    assert samples["selection"] == "bottom_k"
    trailing = _case(block, "trailing")
    assert trailing["occurrences"] == 2 and trailing["selection"] == "all"
    assert {entry["value"]: entry["count"] for entry in trailing["listed"]} == {
        "CLI-000017 ": 1,
        "CLI-004000  ": 1,
    }
    assert [item["kind"] for item in block["whitespace"]] == ["trailing"]
    assert _check(result) == []


def test_a_repeated_text_keeps_its_exact_count(tmp_path):
    rows = _ids(6_000) + [" CLI-000001"] * 5 + ["CLI-000002 "] * 3
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    block = _samples(result)["cases"]

    assert _case(block, "leading")["listed"] == [{"value": " CLI-000001", "count": 5}]
    assert _case(block, "trailing")["listed"] == [{"value": "CLI-000002 ", "count": 3}]
    assert _check(result) == []


def test_the_cases_equal_the_counts_of_the_stages(tmp_path):
    rows = _ids(
        3_000,
        {
            1: " CLI-000001",
            2: "CLI-000002 ",
            3: " CLI-000003 ",
            4: "CLI-00  0004",
            5: "CLI\t000005",
        },
    )
    rows += [" CLI-000001"] * 2
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    field_result = field(dataset(result, "rows"), "v")
    stages = {item["stage"]: item for item in field_result["normalization"]["stages"]}
    block = field_result["values"]["samples"]["cases"]
    kinds = {item["kind"]: item["occurrences"] for item in block["whitespace"]}

    assert kinds == {"leading": 4, "trailing": 2, "repeated": 2}
    assert kinds["repeated"] == stages["collapse_whitespace"]["changed"]
    assert max(kinds["leading"], kinds["trailing"]) <= stages["trim"]["changed"] <= (
        kinds["leading"] + kinds["trailing"]
    )
    assert stages["trim"]["changed"] == 5
    assert _check(result) == []


def test_a_field_without_a_case_has_no_cases_member(tmp_path):
    result = run_scan(_csv(tmp_path, _ids(3_000)), limits=RELEASED)

    assert "cases" not in _samples(result)


def test_the_cases_do_not_depend_on_the_table_the_workers_or_the_order(tmp_path):
    from tabalyst import ScanConfig, scan

    rng = random.Random(11)
    rows = _ids(
        4_000, {n: f"CLI-{n:06d}  " for n in rng.sample(range(4_000), 9)}
    )
    rows += [" CLI-000003", "CLI-12", "CLI-123456789", "CLI-12"]
    shuffled = list(rows)
    random.Random(2).shuffle(shuffled)

    def cases(source, limits, workers):
        config = ScanConfig.model_validate({"limits": limits})
        document = scan(source, config=config, workers=workers).model_dump(mode="json")
        return _samples(document)["cases"]

    complete = cases(_csv(tmp_path, rows), {}, 1)
    assert cases(_csv(tmp_path, rows), RELEASED, 1) == complete
    assert cases(_csv(tmp_path, rows), RELEASED, 2) == complete
    assert cases(_csv(tmp_path, rows), {"max_distinct_per_field": 50}, 1) == complete
    ordered = {
        item["kind"]: item["listed"] for item in cases(_csv(tmp_path, shuffled), {}, 1)["whitespace"]
    }
    assert ordered == {item["kind"]: item["listed"] for item in complete["whitespace"]}
    assert complete["lengths"]["classes"]


def test_a_class_larger_than_its_size_is_a_sample_with_a_threshold(tmp_path):
    rows = _ids(2_000, {n: f"CLI-{n:06d} " for n in range(0, 2_000, 4)})
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    trailing = _case(_samples(result)["cases"], "trailing")

    assert trailing["occurrences"] == 500
    assert trailing["selection"] == "bottom_k" and trailing["of"] == trailing["kept"] == 5
    assert len(trailing["threshold"]) == 32
    assert [entry["value"] for entry in trailing["listed"]] == [
        text for text, _ in _oracle([f"CLI-{n:06d} " for n in range(0, 2_000, 4)], [1] * 500, 5)
    ]
    assert _check(result) == []


def test_the_lengths_other_than_the_dominant_one_have_their_cases(tmp_path):
    rows = _ids(6_000, {10: "CLI-12", 20: "CLI-12", 30: "CLI-1", 40: "CLI-1234567"})
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    lengths = _samples(result)["cases"]["lengths"]
    classes = {item["length"]: item for item in lengths["classes"]}

    assert sorted(classes) == [5, 6, 11]
    assert classes[6]["occurrences"] == 2
    assert classes[6]["listed"] == [{"value": "CLI-12", "count": 2}]
    assert classes[11]["listed"] == [{"value": "CLI-1234567", "count": 1}]
    assert 10 not in classes and "other" not in lengths
    assert _check(result) == []


def test_the_analytical_length_decides_the_class_of_a_text_with_spaces(tmp_path):
    rows = _ids(3_000, {5: " CLI-12 ", 6: "CLI-12"})
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    classes = {
        item["length"]: item for item in _samples(result)["cases"]["lengths"]["classes"]
    }

    assert classes[6]["occurrences"] == 2
    assert {entry["value"] for entry in classes[6]["listed"]} == {" CLI-12 ", "CLI-12"}
    assert _check(result) == []


def test_a_field_without_a_minority_length_has_no_cases_by_length(tmp_path):
    rows = [f"{'x' * (1 + n % 30)}{n}" for n in range(3_000)]
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    assert "cases" not in _samples(result)


def test_lengths_beyond_the_cap_are_summed_in_other_and_the_cap_is_a_setting(tmp_path):
    rows = _ids(6_000) + [f"CLI-{'9' * n}" for n in range(1, 9)] * 2
    result = run_scan(_csv(tmp_path, rows), limits={**RELEASED, "max_case_lengths": 3})

    lengths = _samples(result)["cases"]["lengths"]

    assert lengths["max_lengths"] == 3
    assert len(lengths["classes"]) <= 3
    assert lengths["other"]["occurrences"] > 0
    assert _check(result) == []


def test_the_cases_by_length_can_be_turned_off(tmp_path):
    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-12", 3: "CLI-13"})
    result = run_scan(_csv(tmp_path, rows), limits={**RELEASED, "max_case_lengths": 0})

    block = _samples(result)["cases"]

    assert "lengths" not in block and block["whitespace"]
    assert _check(result) == []


def test_the_cases_can_be_turned_off(tmp_path):
    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-12", 3: "CLI-13"})

    for limits in (RELEASED, {}):
        result = run_scan(_csv(tmp_path, rows), limits={**limits, "max_cases_per_class": 0})

        assert "cases" not in _samples(result)
        assert _check(result) == []


def test_a_disabled_stage_creates_no_class(tmp_path):
    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-000002 ", 3: "CLI-00  0003"})
    result = run_scan(
        _csv(tmp_path, rows),
        limits=RELEASED,
        normalization={"trim": False, "collapse_whitespace": False},
    )

    block = _samples(result).get("cases", {})

    assert "whitespace" not in block
    assert _check(result) == []


def test_a_long_text_is_counted_and_never_listed(tmp_path):
    long = "w" * 1_200 + "  " + "z" * 10
    rows = _ids(3_000, {1: " CLI-000001"}) + [long, long, long + " "]
    result = run_scan(
        _csv(tmp_path, rows), limits={**RELEASED, "max_stored_value_length": 1_000}
    )

    block = _samples(result)["cases"]

    repeated = _case(block, "repeated")
    assert repeated["occurrences"] == 3 and repeated["listed"] == []
    assert _case(block, "leading")["listed"][0]["value"] == " CLI-000001"
    assert _check(result) == []


def test_a_json_source_has_cases_too(tmp_path):
    from tabalyst import ScanConfig, scan

    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-12"})
    path = write_text(tmp_path, "v.json", json.dumps([{"v": row} for row in rows]))

    document = scan(
        path, config=ScanConfig.model_validate({"limits": RELEASED})
    ).model_dump(mode="json")

    block = field(dataset(document, "$[]"), "v")["values"]["samples"]["cases"]
    assert _case(block, "leading")["listed"] == [{"value": " CLI-000001", "count": 1}]
    assert block["lengths"]["classes"][0]["listed"] == [{"value": "CLI-12", "count": 1}]
    assert _check(document) == []


# Exposure ------------------------------------------------------------------------


def _secrets():
    rows = [f"S-{n:02d}" for n in range(60)] + [" S-11", "S-12 ", "S-12 ", " S-99"]
    return rows


def test_a_masked_field_merges_equal_masks_and_adds_their_counts(tmp_path):
    from tabalyst import ScanConfig, scan

    config = ScanConfig.model_validate(
        {
            "limits": {"max_distinct_per_field": 10, "max_samples": 5},
            "patterns": [SECRET],
            "exposure": {"sensitive_values": "mask"},
        }
    )
    document = scan(_csv(tmp_path, _secrets()), config=config).model_dump(mode="json")

    block = _samples(document)["cases"]
    leading = _case(block, "leading")

    assert field(dataset(document, "rows"), "v")["sensitive"]
    assert leading["occurrences"] == 2 and leading["of"] == 2
    assert leading["listed"] == [{"value": " A-99", "count": 2}]
    assert leading["kept"] == 1 and "threshold" not in leading
    assert _check(document) == []


def test_a_hidden_field_lists_no_text_and_keeps_the_counts(tmp_path):
    from tabalyst import ScanConfig, scan

    config = ScanConfig.model_validate(
        {
            "limits": {"max_distinct_per_field": 10, "max_samples": 5},
            "patterns": [SECRET],
            "exposure": {"sensitive_values": "hide"},
        }
    )
    document = scan(_csv(tmp_path, _secrets()), config=config).model_dump(mode="json")

    block = _samples(document)["cases"]

    assert all(
        item["listed"] == [] and item["kept"] == 0 and item["of"] > 0
        for item in block["whitespace"]
    )
    assert {item["kind"]: item["occurrences"] for item in block["whitespace"]} == {
        "leading": 2,
        "trailing": 2,
    }
    assert "threshold" not in json.dumps(block)
    assert _check(document) == []


def test_the_gate_masks_the_texts_of_a_collector():
    collector = CaseCollector(3, 3, 4, 0, 100)
    collector.observe(["ab 12", " cd 34"], [2, 1], [5, 5], [(1, 2)])

    block = collector.block(ExposureGate("mask"))

    leading = block.whitespace[0]
    assert (leading.kind, leading.occurrences) == ("leading", 1)
    assert [(entry.value, entry.count) for entry in leading.listed] == [(" aa 99", 1)]


# Memory --------------------------------------------------------------------------


def test_the_cases_have_an_eighth_of_the_sample_memory():
    budget = SampleBudget(1 << 30)

    assert budget.case_limit == (1 << 30) // CASE_SHARE
    assert (
        budget.limit + budget.long_limit + budget.length_limit + budget.case_limit
        == 1 << 30
    )


def test_a_field_gets_the_largest_size_that_fits_its_share_of_the_cases():
    budget = SampleBudget(1 << 30)

    assert budget.grant_cases(5, 32, None, 10, 1) == 5
    classes, entry = 35, SAMPLE_ENTRY + 20
    tight = SampleBudget(CASE_SHARE * classes * (CASE_CLASS_BYTES + 3 * entry) + CASE_SHARE)

    assert tight.grant_cases(5, 32, None, 10, 1) == 3


def test_a_share_that_cannot_hold_a_class_grants_nothing_and_reserves_nothing():
    budget = SampleBudget(CASE_SHARE * 35 * CASE_CLASS_BYTES)

    assert budget.grant_cases(5, 32, None, 10, 1) == 0
    assert budget.case_reserved == 0


def test_a_field_never_takes_more_than_its_share_of_the_case_budget():
    grants = [SampleBudget(1 << 26).grant_cases(5, 32, None, 10, 4) for _ in range(2)]
    budget = SampleBudget(1 << 26)
    shared = [budget.grant_cases(5, 32, None, 10, fields) for fields in (4, 4, 4, 4)]

    assert shared == [grants[0]] * 4 and grants[0] > 0
    assert budget.case_reserved <= budget.case_limit
    assert grants[0] == grants[1]


def test_a_complete_table_reserves_only_the_values_it_holds():
    budget = SampleBudget(1 << 30)

    budget.grant_cases(5, 32, 12, 10, 1)

    assert budget.case_reserved == 12 * (CASE_CLASS_BYTES + SAMPLE_ENTRY + 20)


def test_a_small_budget_gives_fewer_texts_per_class_and_says_so(tmp_path):
    from tabalyst import ScanConfig, scan

    columns = 3
    rows = ["a,b,c"]
    for n in range(2_000):
        rows.append(",".join(f"CLI-{n:06d}" for _ in range(columns)))
    rows[5] = ",".join(" CLI-000004" for _ in range(columns))
    source = write_text(tmp_path, "wide.csv", "\n".join(rows) + "\n")
    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 100,
                "max_samples": 50,
                "max_sample_memory": 4_000_000,
            }
        }
    )

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 2)
    ]

    blocks = [
        field(dataset(documents[0], "rows"), name)["values"]["samples"]["cases"]
        for name in "abc"
    ]
    assert len({block["per_class_k"] for block in blocks}) == 1
    for block in blocks:
        assert 0 <= block["per_class_k"] < 5
        assert block["requested_per_class_k"] == 5 and block["reason"] == "memory_budget"
    assert [
        field(dataset(documents[1], "rows"), name)["values"]["samples"]["cases"]
        for name in "abc"
    ] == blocks
    assert _check(documents[0]) == []


def test_a_grant_of_zero_keeps_the_counts_and_lists_no_text(tmp_path):
    from tabalyst import ScanConfig, scan

    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-000002 "})
    config = ScanConfig.model_validate(
        {"limits": {**RELEASED, "max_sample_memory": 300_000}}
    )

    document = scan(_csv(tmp_path, rows), config=config).model_dump(mode="json")

    block = _samples(document)["cases"]
    assert block["per_class_k"] == 0 and block["reason"] == "memory_budget"
    assert {item["kind"]: item["occurrences"] for item in block["whitespace"]} == {
        "leading": 1,
        "trailing": 1,
    }
    assert all(item["listed"] == [] for item in block["whitespace"])
    assert _check(document) == []


# Document, Report base, validation -----------------------------------------------


def test_the_report_base_keeps_the_counts_of_the_cases_and_drops_their_texts(tmp_path):
    from tabalyst import ScanConfig, scan
    from tabalyst.report_profile import report_base
    from tabalyst.scanner.identity import facts_sha256

    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-12", 3: "CLI-13"})
    result = scan(_csv(tmp_path, rows), config=ScanConfig.model_validate({"limits": RELEASED}))

    base = report_base(result, 20)

    cases = base.datasets[0].fields[0].values.samples.cases
    assert cases.whitespace[0].occurrences == 1 and cases.whitespace[0].listed == []
    assert cases.lengths.classes and all(item.listed == [] for item in cases.lengths.classes)
    original = result.datasets[0].fields[0].values.samples.cases
    assert original.whitespace[0].kept == 1
    assert check_scan(base) == []
    assert facts_sha256(base) == facts_sha256(result)


def test_a_document_with_cases_passes_the_json_schema(tmp_path):
    from jsonschema import Draft202012Validator

    from tabalyst.scanner.schema import scan_schema

    rows = _ids(3_000, {1: " CLI-000001", 2: "CLI-12", 3: "CLI-00  3"})
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    Draft202012Validator(scan_schema()).validate(result)


def _mutated(tmp_path, change):
    from tabalyst.scanner.models import ScanResult

    rows = _ids(
        3_000, {1: " CLI-000001", 2: "CLI-000002 ", 3: "CLI-12", 4: "CLI-00  4"}
    )
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)
    change(_samples(result)["cases"])
    return check_scan(ScanResult.model_validate(result))


def _leading(block):
    return _case(block, "leading")


@pytest.mark.parametrize(
    "change",
    [
        lambda block: _leading(block).update(listed=[{"value": "CLI-000001", "count": 1}]),
        lambda block: _leading(block).update(occurrences=0),
        lambda block: _leading(block).update(occurrences=9),
        lambda block: _case(block, "repeated").update(occurrences=7),
        lambda block: _case(block, "trailing").update(occurrences=7),
        lambda block: block.update(per_class_k=10**6),
        lambda block: block.update(requested_per_class_k=100),
        lambda block: block["whitespace"].reverse(),
        lambda block: _leading(block).update(kept=2),
        lambda block: _leading(block).update(threshold="0" * 32),
        lambda block: block["lengths"]["classes"][0].update(length=99),
        lambda block: block["lengths"]["classes"][0].update(occurrences=10**6),
        lambda block: block["lengths"].update(max_lengths=1),
        lambda block: block["lengths"]["classes"].append(
            {**block["lengths"]["classes"][0], "length": 10}
        ),
        lambda block: _leading(block)["listed"].append(
            {"value": " CLI-000002", "count": 1}
        ),
    ],
)
def test_check_scan_refuses_inconsistent_cases(tmp_path, change):
    assert _mutated(tmp_path, change)


def test_check_scan_refuses_texts_out_of_hash_order(tmp_path):
    texts = [f"CLI-{n:06d} " for n in range(40)]
    rows = _ids(3_000) + texts
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)
    from tabalyst.scanner.models import ScanResult

    _case(_samples(result)["cases"], "trailing")["listed"].reverse()

    assert check_scan(ScanResult.model_validate(result))


def test_a_clean_oracle_over_many_classes_agrees_with_the_scan(tmp_path):
    rng = random.Random(5)
    texts = []
    for n in range(5_000):
        text = f"CLI-{n:06d}"
        if rng.random() < 0.01:
            text = " " * rng.randint(1, 3) + text
        texts.append(text)
    counts = Counter(texts)
    rows = texts + texts[:50]
    counts = Counter(rows)
    result = run_scan(_csv(tmp_path, rows), limits=RELEASED)

    leading = _case(_samples(result)["cases"], "leading")
    cells = defaultdict(int)
    for text, count in counts.items():
        if text != text.lstrip():
            cells[text] = count

    assert leading["occurrences"] == sum(cells.values())
    assert [(e["value"], e["count"]) for e in leading["listed"]] == _oracle(
        list(cells), list(cells.values()), 5
    )


def test_the_memory_of_the_cases_stays_within_the_model():
    import tracemalloc

    from tabalyst.scanner.memory import sample_entry_bytes

    rng = random.Random(9)
    k, max_lengths = 5, 32
    collector = CaseCollector(k, k, max_lengths, 0, 1_000)
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    for _ in range(20):
        raws = ["".join(rng.choices("abcdef ", k=rng.randint(1, 40))) for _ in range(5_000)]
        lengths = [len(raw.strip()) for raw in raws]
        flagged = [(n, 2) for n, raw in enumerate(raws) if raw != raw.strip()]
        collector.observe(raws, [1] * len(raws), lengths, flagged)
        del raws, lengths, flagged
    used = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()

    classes = 3 + max_lengths
    assert used <= classes * (CASE_CLASS_BYTES + k * sample_entry_bytes(40))
