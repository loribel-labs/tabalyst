# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Counts, outputs and report of the small scenarios T01 to T06 (design 6, 8, 12).

Each scenario is checked at three levels, one per lot: the counts and marks of the
first pass (lot 4), the published CSV (lot 5) and the JSON report (lot 6).
"""

import json

import pytest
from dedup_helpers import (
    analyze,
    assert_published,
    check_invariants,
    count_stats,
    load_report,
    no_temporary_files,
    output_names,
    reference_outputs,
    reference_stats,
    run,
    validate_report,
    write_csv,
)


def _same(*names: str) -> list[tuple[str, str]]:
    """Rows whose id repeats with the name, so equal names mean equal rows."""
    ids = {name: str(index) for index, name in enumerate(dict.fromkeys(names))}
    return [(ids[name], name) for name in names]


CASES = {
    "T01": [(str(n), f"name {n}") for n in range(100)],
    "T02": [],
    "T03": _same("A", "A"),
    "T04": _same("A", "A", "B", "B"),
    "T05": _same("A", "A", "A"),
    "T06": _same("A", "B", "C", "A", "B", "A"),
}
IDS = sorted(CASES)
EXPECTED_FILES = {
    "T01": [],
    "T02": [],
    "T03": ["unique", "duplicates"],
    "T04": ["unique", "duplicates"],
    "T05": ["unique", "duplicates", "duplicates_all"],
    "T06": ["unique", "duplicates", "duplicates_all"],
}
EXPECTED_ROWS = {  # unique / duplicates / duplicates_all, where written (S16.1)
    "T03": (1, 1),
    "T04": (2, 2),
    "T05": (1, 1, 3),
    "T06": (3, 2, 5),
}


@pytest.fixture
def make(tmp_path):
    def build(case: str):
        rows = CASES[case]
        return write_csv(tmp_path, f"{case.lower()}.csv", rows), rows

    return build


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T01", "T02", "T03", "T04", "T05", "T06")
@pytest.mark.parametrize("case", IDS)
def test_first_pass_counts_and_marks_match_the_reference(make, case):
    source, rows = make(case)
    analysis = analyze(source)
    letters = count_stats(analysis)
    assert letters == reference_stats(rows)
    check_invariants(letters)
    seen = set()
    for index, row in enumerate(rows):
        assert analysis.marks.is_extra(index) == (row in seen)
        seen.add(row)
    firsts = {row: index for index, row in reversed(list(enumerate(rows)))}
    repeated = {row for row in rows if rows.count(row) >= 2}
    for index, row in enumerate(rows):
        assert analysis.marks.is_group_first(index) == (
            row in repeated and firsts[row] == index
        )


@pytest.mark.dedup_lot("5")
@pytest.mark.dedup_t("T01", "T02", "T03", "T04", "T05", "T06")
@pytest.mark.parametrize("case", IDS)
def test_published_csv_have_the_exact_definitions_order_and_header(make, case, tmp_path):
    source, rows = make(case)
    run(source)
    assert_published(tmp_path, source.stem, rows)
    names = output_names(source.stem)
    written = sorted(kind for kind, name in names.items() if (tmp_path / name).exists())
    assert written == sorted(EXPECTED_FILES[case])
    if case in EXPECTED_ROWS:
        outputs = reference_outputs(rows)
        counts = tuple(len(outputs[kind]) for kind in EXPECTED_FILES[case])
        assert counts == EXPECTED_ROWS[case]
    assert no_temporary_files(tmp_path)


@pytest.mark.dedup_lot("5")
@pytest.mark.dedup_t("T02")
def test_a_file_with_only_a_header_is_valid_and_produces_no_csv(tmp_path):
    source = write_csv(tmp_path, "empty.csv", [])
    run(source)
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".csv") and p != source]


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T01", "T02", "T03", "T04", "T05", "T06")
@pytest.mark.parametrize("case", IDS)
def test_the_report_is_valid_complete_and_consistent_with_the_files(make, case, tmp_path):
    source, rows = make(case)
    run(source)
    document = load_report(tmp_path, source.stem)
    validate_report(document)
    assert document["status"] == "complete"
    assert document["format"] == "tabalyst.dedup"
    assert document["format_version"] == "0.2.0"
    assert document["format_revision"] == 1
    letters = reference_stats(rows)
    records = document["records"]
    assert records["total"] == letters["N"]
    assert records["distinct"] == letters["D"]
    assert records["duplicate_groups"] == letters["G"]
    assert records["extra_copies"] == letters["E"]
    assert records["max_occurrences"] == letters["M"]
    outputs = document["outputs"]
    assert outputs["csv_files_created"] == len(EXPECTED_FILES[case])
    for kind in ("unique", "duplicates", "duplicates_all"):
        assert (outputs[kind] is not None) == (kind in EXPECTED_FILES[case])
    assert document["run"]["passes"] == (1 if letters["G"] == 0 else 2)
    assert document["source"]["name"] == source.name
    assert document["settings"]["identity"] == "full_decoded_csv_row_v1"


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T01", "T02")
def test_a_source_without_duplicate_still_gets_a_report_and_no_csv(make, tmp_path):
    source, _ = make("T01")
    run(source)
    assert (tmp_path / "t01.dedup.json").exists()
    assert not (tmp_path / "t01.unique.csv").exists()
    assert load_report(tmp_path, "t01")["outputs"]["csv_files_created"] == 0


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T01")
def test_the_report_holds_no_cell_content_and_no_absolute_path(tmp_path):
    rows = [("secret-4711", "person@example.org"), ("secret-4711", "person@example.org")]
    source = write_csv(tmp_path, "private.csv", rows, header=["token", "mail"])
    run(source)
    text = (tmp_path / "private.dedup.json").read_text(encoding="utf-8")
    for cell in ("secret-4711", "person@example.org"):
        assert cell not in text
    assert str(tmp_path) not in text
    assert json.loads(text)["outputs"]["unique"]["file"] == "private.unique.csv"
