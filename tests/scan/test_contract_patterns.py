# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the pattern inference (Scan and JSON plan, tests C07 to C10).

The behavior is specified in ``docs/dev/scan/design.md`` section 18.12 and in
the specification, section 10 (PAT-01 to PAT-06, LONG-05). The inference reads
the samples of the finished scan, so the expectations are on the document.
"""

import pytest
from scan_helpers import dataset, field, run_scan, write_text

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _entry(result: dict, display: str) -> dict:
    """The inferred patterns of the column ``display``."""
    column = field(dataset(result, "rows"), display)["id"]
    entries = [
        item
        for item in result["derived"]["patterns"]["fields"]
        if item["field"] == column
    ]
    assert len(entries) == 1
    return entries[0]


def _patterns(entry: dict) -> dict[str, dict]:
    """The patterns of every family of an entry, by rendering."""
    return {
        pattern["render"]: pattern
        for family in entry["families"]
        for pattern in family["patterns"]
    }


def _csv(directory, name: str, header: str, rows) -> object:
    return write_text(directory, name, header + "\n" + "\n".join(rows) + "\n")


@pytest.mark.scan_json_lot("4a")
def test_C07_sorted_old_and_new_id_formats_are_both_discovered(tmp_path):
    # The ids are sorted: the first 1,500 rows are all the old format. A preview
    # of the start would never see the new one; the sample is taken by priority.
    old = [
        f"{LETTERS[(i // 26) % 26]}{LETTERS[i % 26]}{(i * 7) % 10_000:04d}"
        for i in range(1_500)
    ]
    new = [
        f"{LETTERS[(i // 26) % 26]}{LETTERS[i % 26]}{(i * 7) % 10_000:04d}"
        f"{LETTERS[(i * 5) % 26]}"
        for i in range(1_500)
    ]
    source = _csv(tmp_path, "ids.csv", "id", [*old, *new])

    result = run_scan(source, limits={"max_samples": 200})
    entry = _entry(result, "id")

    assert entry["status"] == "complete"
    assert set(_patterns(entry)) == {"AA9999", "AA9999A"}
    assert entry["population"]["selection"] == "bottom_k"
    assert not entry["population"]["complete"]
    assert entry["population"]["occurrences_basis"] == "sample"
    for family in entry["families"]:
        assert family["d"] / entry["population"]["distinct"] > 0.3
    assert entry["other"] == {"structures": 0, "d": 0, "o": 0}


@pytest.mark.scan_json_lot("4a")
def test_C08_a_literal_letter_is_not_a_generic_capital(tmp_path):
    fixed = [
        f"{LETTERS[(i // 26) % 26]}{LETTERS[i % 26]}{1000 + i * 3:04d}A"
        for i in range(60)
    ]
    varying = [
        f"{LETTERS[(i // 26) % 26]}{LETTERS[i % 26]}{1000 + i * 3:04d}"
        f"{LETTERS[(i * 5) % 26]}"
        for i in range(60)
    ]
    source = _csv(
        tmp_path,
        "codes.csv",
        "fixed,varying",
        [f"{a},{b}" for a, b in zip(fixed, varying, strict=True)],
    )

    result = run_scan(source)
    fixed_entry = _entry(result, "fixed")
    varying_entry = _entry(result, "varying")

    [literal] = _patterns(fixed_entry).values()
    # The digits all start with 1 (1000 to 1177): a constant of the pattern too.
    assert literal["render"] == "AA'1'999'A'"
    assert literal["signature"][-1] == {"kind": "literal", "text": "A", "min": 1, "max": 1}
    [generic] = _patterns(varying_entry).values()
    assert generic["render"] == "AA'1'999A"
    assert generic["signature"][-1] == {"kind": "upper_ascii", "min": 1, "max": 1}
    assert literal["render"] != generic["render"]
    assert fixed_entry["population"]["complete"]


@pytest.mark.scan_json_lot("4a")
def test_C09_structures_are_disjoint_families_and_the_budget_leaves_the_rest_in_other(tmp_path):
    # Six-character values of five structures: each value belongs to the one
    # family of its structure, so nothing overlaps; with three families the two
    # smallest structures are counted in `other`.
    rows = (
        [f"{LETTERS[i % 26]}{LETTERS[(i * 3) % 26]}{1000 + i:04d}" for i in range(40)]
        + [f"{LETTERS[i % 26].lower()}{LETTERS[(i * 3) % 26].lower()}{2000 + i:04d}" for i in range(30)]
        + [f"{1000 + i:04d}{LETTERS[i % 26]}{LETTERS[(i * 5) % 26]}" for i in range(10)]
        + [
            f"{LETTERS[i % 26]}{i % 10}{LETTERS[(i * 3) % 26]}{(i * 7) % 10}{LETTERS[(i * 5) % 26]}{(i * 3) % 10}"
            for i in range(10)
        ]
        + [f"{10 + i:02d}{LETTERS[i % 26]}{LETTERS[(i * 3) % 26]}{20 + i:02d}" for i in range(10)]
    )
    source = _csv(tmp_path, "mixed.csv", "code", rows)

    result = run_scan(source, pattern_inference={"max_families": 3})
    entry = _entry(result, "code")

    assert [family["d"] for family in entry["families"]] == [40, 30, 10]
    assert [family["key"] for family in entry["families"]][:2] == ["UD", "LD"]
    assert "overlaps" not in entry
    assert entry["limits"] == ["max_families"]
    assert entry["other"] == {"structures": 2, "d": 20, "o": 20}
    # Every distinct value counts once: the families and `other` add up.
    taken = sum(family["d"] for family in entry["families"])
    assert taken + entry["other"]["d"] == entry["population"]["distinct"] == 100


@pytest.mark.scan_json_lot("4a")
def test_C10_the_preview_of_a_long_text_never_certifies_a_pattern(tmp_path):
    texts = [f"{'abc ' * 20}{i:04d}" for i in range(70)]
    mixed = [f"ID{i:05d}" for i in range(40)] + texts[:30]
    source = _csv(
        tmp_path,
        "long.csv",
        "text,mixed",
        [f"{text},{value}" for text, value in zip(texts, mixed, strict=True)],
    )

    result = run_scan(
        source, limits={"max_stored_value_length": 50}, pattern_inference={"max_value_length": 50}
    )

    only_long = _entry(result, "text")
    assert only_long["status"] == "not_applicable"
    assert only_long["reason"] == "long_texts_only"
    partial = _entry(result, "mixed")
    assert partial["status"] == "complete"
    assert partial["population"]["excluded"]["long_text_occurrences"] == 30
    [pattern] = _patterns(partial).values()
    # ID00000 to ID00039: the first three digits are a constant of the pattern.
    assert pattern["render"] == "'ID000'99"
    assert pattern["lengths"] == [2, 5]
    assert partial["population"]["distinct"] == 40
