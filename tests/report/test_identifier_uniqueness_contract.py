# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests T01 to T34 of the identifier uniqueness (cahier 15.1).

Each test names its lot (``uid_lot``) and its requirement (``uid_t``); a lot that is not in
``conftest.ENABLED_LOTS`` is skipped. Lot 0 tests describe behavior that exists in 0.7.1 and
must not change (UID-001, UID-010). The expectations follow
``docs/dev/report/identifier-uniqueness.md``; changing one requires changing that document
in the same lot. Lots 2 to 4 may adapt the calls to the final signatures of their API
(contract 9.1) but not the expectations.
"""

import json
import random
import uuid

import pytest
from identifier_uniqueness_helpers import (
    assess,
    oracle,
    population,
    random_population,
    report_document,
    uniqueness_of,
    write_csv,
)

from tabalyst import scan
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.quality import analytical_distinct

# ------------------------------------------------------------------ lot 1: the pure rule


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T01")
def test_t01_all_ids_distinct_is_raw_unique():
    result = assess(n=100_000, d=100_000, e=0)

    assert result["status"] == "complete"
    assert result["interpretation"] == "raw_unique"
    assert result["raw"] == {"unique": True, "id_distinct": 100_000, "id_redundant": 0}
    assert result["explanation"]["id_repetitions_residual"] == 0


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T01")
def test_a_raw_unique_id_needs_no_duplicate_count():
    result = assess(n=100, d=100, e=None)

    assert result["interpretation"] == "raw_unique"
    assert result["explanation"]["duplicate_row_extra_copies"] == 0
    assert result["after_row_deduplication"]["unique"] is True


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T02")
def test_t02_copies_that_explain_every_repetition():
    result = assess(n=100_000, d=99_500, e=500)

    assert result["status"] == "complete"
    assert result["interpretation"] == "unique_after_row_deduplication"
    assert result["raw"] == {"unique": False, "id_distinct": 99_500, "id_redundant": 500}
    assert result["after_row_deduplication"] == {
        "unique": True,
        "id_distinct": 99_500,
        "id_redundant": 0,
    }
    assert result["explanation"] == {
        "duplicate_row_extra_copies": 500,
        "id_repetitions_explained": 500,
        "id_repetitions_residual": 0,
    }
    assert result["scope"]["distinct_records"] == 99_500


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T03")
def test_t03_copies_that_explain_only_part_of_the_repetitions():
    result = assess(n=100_000, d=99_480, e=500)

    assert result["interpretation"] == "repeated_between_distinct_records"
    assert result["raw"]["id_redundant"] == 520
    assert result["explanation"]["id_repetitions_explained"] == 500
    assert result["explanation"]["id_repetitions_residual"] == 20
    assert result["after_row_deduplication"]["unique"] is False
    assert result["after_row_deduplication"]["id_redundant"] == 20


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T04")
def test_t04_same_id_with_other_columns_different_is_residual():
    result = assess(n=2, d=1, e=0)

    assert result["explanation"]["duplicate_row_extra_copies"] == 0
    assert result["explanation"]["id_repetitions_residual"] == 1
    assert result["interpretation"] == "repeated_between_distinct_records"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T05")
@pytest.mark.parametrize("sizes", [(3,), (10,), (3, 10, 1, 2)])
def test_t05_extra_copies_are_counted_not_groups(sizes):
    n = sum(sizes)
    result = assess(n=n, d=len(sizes), e=n - len(sizes))

    assert result["explanation"]["duplicate_row_extra_copies"] == n - len(sizes)
    assert result["explanation"]["id_repetitions_residual"] == 0
    if len(sizes) >= 2:
        assert result["interpretation"] == "unique_after_row_deduplication"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T06")
def test_t06_ids_equal_only_after_trim_stay_a_residual_repetition():
    """Case D: the rows differ, the analytical ID is the same (D counts one value)."""
    result = assess(n=2, d=1, e=0)

    assert result["explanation"]["id_repetitions_residual"] == 1
    assert result["scope"]["id_value_domain"] == "analytical"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T08")
def test_t08_duplicates_on_other_columns_only_leave_the_id_unique():
    result = assess(n=1000, d=1000, e=0)

    assert result["interpretation"] == "raw_unique"
    assert result["raw"]["id_redundant"] == 0


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T09")
def test_t09_a_copied_row_without_id_never_subtracts_all_copies():
    """Case E: 3 records, two copies without ID, one ID present."""
    result = assess(n=3, present=1, d=1, e=1)

    assert result["status"] == "limited"
    assert result["reason"] == "missing_ids"
    assert result["interpretation"] == "not_assessed"
    assert result["after_row_deduplication"]["unique"] is None
    assert result["explanation"]["id_repetitions_residual"] is None
    assert result["scope"]["missing_id_positions"] == 2


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T10")
def test_t10_a_missing_id_in_a_row_that_is_not_copied_refuses_the_strict_result():
    result = assess(n=3, present=2, d=2, e=0)

    assert result["reason"] == "missing_ids"
    assert result["raw"]["unique"] is None
    assert result["after_row_deduplication"]["unique"] is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T11")
def test_t11_one_distinct_row_repeated_is_not_a_significant_key():
    """Case F: R_residual is 0 but U is 1."""
    result = assess(n=3, d=1, e=2)

    assert result["status"] == "limited"
    assert result["reason"] == "too_few_distinct_records"
    assert result["interpretation"] == "not_assessed"
    assert result["after_row_deduplication"]["unique"] is None
    assert result["raw"]["unique"] is False
    assert result["scope"]["distinct_records"] == 1


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T11")
def test_a_single_record_is_not_a_raw_unique_key():
    result = assess(n=1, d=1, e=0)

    assert result["reason"] == "too_few_records"
    assert result["raw"]["unique"] is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T12")
def test_t12_exact_scan_cardinality_and_duplicates_conclude_alone():
    result = assess(n=500, d=495, e=5)

    assert result["status"] == "complete"
    assert result["evidence"]["id_cardinality"]["source"] == "scan.values.cardinality"
    assert result["evidence"]["duplicate_rows"]["source"] == "scan.records.duplicates"
    assert result["evidence"]["duplicate_rows"]["accuracy"] == "exact"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T14")
def test_t14_a_limited_scan_count_without_dedup_invents_no_residual():
    result = assess(n=5000, d=4990, e=3, duplicate_accuracy="lower_bound")

    assert result["status"] == "limited"
    assert result["reason"] == "duplicates_limited"
    assert result["interpretation"] == "not_assessed"
    assert result["explanation"]["id_repetitions_residual"] is None
    assert result["explanation"]["id_repetitions_explained"] is None
    assert result["raw"]["id_redundant"] == 10


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T14")
def test_a_disabled_duplicate_count_is_not_assessed():
    result = assess(n=100, d=90, e=None, duplicate_accuracy="disabled")

    assert result["status"] == "not_assessed"
    assert result["reason"] == "duplicates_disabled"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T13")
def test_a_dedup_count_replaces_a_limited_scan_count():
    result = assess(
        n=5000,
        d=4500,
        e=3,
        duplicate_accuracy="lower_bound",
        extra_duplicates=[("dedup.report", 500, "exact")],
    )

    assert result["status"] == "complete"
    assert result["evidence"]["duplicate_rows"]["source"] == "dedup.report"
    assert result["explanation"]["id_repetitions_residual"] == 0


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T18")
def test_t18_an_estimated_cardinality_never_concludes():
    result = assess(n=100_000, d=99_500, e=500, distinct_accuracy="estimated")

    assert result["status"] == "limited"
    assert result["reason"] == "distinct_estimated"
    assert result["interpretation"] == "not_assessed"
    assert result["raw"]["id_distinct"] is None
    assert result["raw"]["unique"] is None
    assert result["after_row_deduplication"]["unique"] is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T19")
def test_t19_original_deep_count_is_not_an_analytical_count_when_trim_changed_values():
    result = assess(
        n=100,
        d=100,
        e=0,
        distinct_source="deep.exact_distinct",
        domain="original",
        stages_changed_values=True,
    )

    assert result["status"] == "limited"
    assert result["reason"] == "distinct_not_exact"
    assert result["raw"]["unique"] is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T20")
def test_t20_original_deep_count_is_usable_when_no_stage_changed_a_value():
    result = assess(
        n=100,
        d=100,
        e=0,
        distinct_source="deep.exact_distinct",
        domain="original",
        stages_changed_values=False,
    )

    assert result["status"] == "complete"
    assert result["evidence"]["id_cardinality"]["source"] == "deep.exact_distinct"
    assert result["interpretation"] == "raw_unique"


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T21", "T22", "T23", "T24")
def test_an_ineligible_column_has_no_assessment():
    assert assess(n=100, d=100, e=0, eligible=False) is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T25")
def test_t25_a_partial_scope_guarantees_nothing_about_the_whole_file():
    result = assess(n=1000, d=1000, e=0, scope_complete=False)

    assert result["status"] == "limited"
    assert result["reason"] == "scope_partial"
    assert result["raw"]["unique"] is None
    assert result["after_row_deduplication"]["unique"] is None
    assert result["scope"]["complete"] is False


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T28")
@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"n": 10, "d": 9, "e": 3}, "inconsistent_measures"),  # R_raw 1 < E 3
        ({"n": 10, "d": 10, "e": 2}, "inconsistent_measures"),  # raw unique with copies
        ({"n": 10, "d": 11, "e": 0}, "inconsistent_measures"),  # D above P
        ({"n": 10, "d": 5, "e": 12}, "inconsistent_measures"),  # E above N
        (
            {
                "n": 10,
                "d": 8,
                "e": 2,
                "extra_duplicates": [("dedup.report", 3, "exact")],
            },
            "evidence_conflict",
        ),
    ],
)
def test_t28_contradictory_exact_measures_fail_without_correction(options, reason):
    result = assess(**options)

    assert result["status"] == "failed"
    assert result["reason"] == reason
    assert result["interpretation"] == "not_assessed"
    assert result["raw"]["unique"] is None
    assert result["after_row_deduplication"]["unique"] is None
    assert result["explanation"]["id_repetitions_residual"] is None


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T30")
def test_the_assessment_is_deterministic():
    options = {"n": 1000, "d": 990, "e": 4}

    assert assess(**options) == assess(**options)


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T02", "T03", "T09", "T11")
@pytest.mark.parametrize("seed", range(150))
def test_the_rule_agrees_with_the_in_memory_oracle(seed):
    rows = random_population(random.Random(seed))
    if len(rows) < 1:
        return
    expected = oracle(rows)
    result = assess(n=expected.n, present=expected.p, d=expected.d, e=expected.e)

    if expected.m:
        assert result["reason"] == "missing_ids"
        assert result["after_row_deduplication"]["unique"] is None
        return
    if expected.n < 2:
        assert result["reason"] == "too_few_records"
        return
    assert result["raw"]["unique"] is expected.raw_unique
    if expected.u < 2:
        assert result["reason"] == "too_few_distinct_records"
        return
    assert result["after_row_deduplication"]["unique"] is expected.unique_after_dedup
    assert result["explanation"]["id_repetitions_residual"] == expected.r_residual
    assert result["explanation"]["id_repetitions_explained"] == expected.r_explained


@pytest.mark.uid_lot("1")
@pytest.mark.uid_t("T18", "T14")
@pytest.mark.parametrize("accuracy", ["estimated", "limited"])
def test_no_false_is_ever_emitted_without_a_demonstrated_repetition(accuracy):
    for options in (
        {"n": 100, "d": 50, "e": 5, "distinct_accuracy": accuracy},
        {"n": 100, "d": 50, "e": 5, "duplicate_accuracy": "lower_bound"},
        {"n": 100, "d": 50, "e": None, "duplicate_accuracy": "disabled"},
    ):
        result = assess(**options)
        assert result["after_row_deduplication"]["unique"] is None, options


# ---------------------------------------------- lot 0: behavior of 0.7.1 that must not move


def _classes(path):
    result = scan(path)
    return {
        f.display: (f.classification.family, f.classification.type, f.classification.traits)
        for ds in result.datasets
        for f in ds.fields
    }


def _csv(tmp_path, name, header, rows):
    return write_csv(tmp_path, name, rows, header=header)


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T21")
def test_t21_a_uuid_column_keeps_its_specific_type(tmp_path):
    rows = [(str(uuid.UUID(int=i)), str(i)) for i in range(1, 8)]
    classes = _classes(_csv(tmp_path, "u.csv", ["customer_id", "x"], rows))

    assert classes["customer_id"][:2] == ("web_network", "uuid")


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T21")
def test_t21_an_email_column_keeps_its_specific_type(tmp_path):
    rows = [(f"a{i}@example.com", str(i)) for i in range(8)]
    classes = _classes(_csv(tmp_path, "e.csv", ["email", "x"], rows))

    assert classes["email"][:2] == ("contact", "email")


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T22")
def test_t22_a_name_that_weakens_the_role_gives_no_identifier(tmp_path):
    rows = [(str(i), f"a{i}") for i in range(1, 8)]
    classes = _classes(_csv(tmp_path, "l.csv", ["customer_id_length", "x"], rows))

    assert classes["customer_id_length"][0] != "identifier"


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T23")
def test_t23_first_column_and_observed_unique_without_an_id_name_are_no_identifier(tmp_path):
    rows = [(str(i), f"a{i}") for i in range(1, 8)]
    classes = _classes(_csv(tmp_path, "n.csv", ["value", "x"], rows))

    family, _, traits = classes["value"]
    assert family != "identifier"
    assert "observed_unique" in traits and "first_column" in traits


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T24")
def test_t24_an_id_under_a_json_array_is_never_a_unique_id(tmp_path):
    source = tmp_path / "nested.json"
    source.write_text(
        json.dumps(
            {
                "orders": [
                    {"id": 1, "lines": [{"id": 10}, {"id": 11}]},
                    {"id": 2, "lines": [{"id": 12}, {"id": 13}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    classes = _classes(source)

    assert classes["lines[].id"][:2] == ("identifier", "id")
    assert classes["id"][:2] == ("identifier", "unique_id")  # a collection root, no array above


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T25")
def test_t25_a_tolerant_scan_with_excluded_records_is_partial(tmp_path):
    source = tmp_path / "ragged.csv"
    source.write_bytes(b"customer_id,x\r\nA,1\r\nB\r\nC,3\r\n")

    result = scan(source, config=ScanConfig.model_validate({"errors": {"policy": "tolerant"}}))

    assert result.status == "partial"
    assert result.scope.records_excluded == 1
    assert result.datasets[0].record_count == 2


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T26")
def test_t26_the_scan_keeps_the_duplicate_counts_of_two_datasets_apart(tmp_path):
    source = tmp_path / "two.json"
    source.write_text(
        json.dumps(
            {
                "a": [{"id": 1, "v": "x"}, {"id": 2, "v": "y"}],
                "b": [{"id": 1, "v": "x"}, {"id": 1, "v": "x"}, {"id": 3, "v": "z"}],
            }
        ),
        encoding="utf-8",
    )

    result = scan(source, config=ScanConfig.model_validate({"json": {"collections": ["$.a[]", "$.b[]"]}}))
    counts = {ds.id: (ds.record_count, ds.records.duplicates.count.value) for ds in result.datasets}

    assert counts["$.a[]"] == (2, 0)
    assert counts["$.b[]"] == (3, 1)


@pytest.mark.uid_lot("0")
@pytest.mark.uid_t("T34")
def test_t34_the_scan_domain_merges_unicode_forms_that_the_rows_keep_apart(tmp_path):
    """NFC merges the IDs (D = 1) while the rows stay distinct (E = 1): the pair the rule uses."""
    source = tmp_path / "unicode.csv"
    source.write_bytes("id,x\r\né,x\r\né,x\r\né,x\r\n".encode())

    dataset = scan(source).datasets[0]
    field = dataset.fields[0]

    assert dataset.records.duplicates.count.value == 1
    assert analytical_distinct(field) == 1


# ------------------------------------------------------------ lot 2: the Dedup proof


def _dedup(tmp_path, rows, name="d.csv", **options):
    """A CSV, its scan and a Dedup report beside it."""
    from tabalyst.dedup_service import dedup_csv

    source = write_csv(tmp_path, name, rows)
    outcome = dedup_csv(source, output_dir=tmp_path, **options)
    return source, outcome.report_path


def _proof(report_path, scan_result, origin="explicit"):
    from tabalyst.identifier_uniqueness.proof import load_dedup_proof

    return load_dedup_proof(report_path, scan=scan_result, dataset="rows", origin=origin)


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T07")
def test_t07_equal_cells_quoted_differently_are_the_same_row(tmp_path):
    source = tmp_path / "q.csv"
    source.write_bytes(b'customer_id,status\r\nA,"x"\r\nA,x\r\n"A",x\r\nB,y\r\n')
    from tabalyst.dedup_service import dedup_csv

    outcome = dedup_csv(source, output_dir=tmp_path)
    proof = _proof(outcome.report_path, scan(source))

    assert proof.value == 2
    assert proof.accuracy == "exact"
    assert scan(source).datasets[0].records.duplicates.count.value == 2


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T13")
def test_t13_a_compatible_dedup_report_supplies_e_when_the_scan_is_limited(tmp_path):
    rows = population(distinct_ids=2000, copies=600)
    source, report = _dedup(tmp_path, rows)
    config = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})
    result = scan(source, config=config)
    assert result.datasets[0].records.duplicates.count.status == "limited"

    proof = _proof(report, result)

    assert proof.value == 600 and proof.accuracy == "exact"
    assert proof.source == "dedup.report"
    assert proof.report.origin == "explicit"


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T15")
def test_t15_a_failed_dedup_report_is_refused(tmp_path):
    from tabalyst.dedup.failures import DedupInputError
    from tabalyst.dedup_service import dedup_csv

    source = tmp_path / "bad.csv"
    source.write_bytes(b"customer_id,x\r\nA,1\r\nA\r\n")
    with pytest.raises(DedupInputError):
        dedup_csv(source, output_dir=tmp_path)
    good = write_csv(tmp_path, "good.csv", [("A", "1"), ("A", "1")], header=["customer_id", "x"])

    proof = _proof(tmp_path / "bad.dedup.json", scan(good))

    assert proof.reason == "dedup_not_complete"


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T16")
def test_t16_a_dedup_report_of_another_content_is_refused(tmp_path):
    source, report = _dedup(tmp_path, population(distinct_ids=20, copies=3))
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("Z-1,new\r\n")

    proof = _proof(report, scan(source))

    assert proof.reason == "dedup_source_mismatch"


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T17")
def test_t17_a_dedup_report_read_with_another_delimiter_is_refused(tmp_path):
    from tabalyst.dedup_service import dedup_csv

    source = tmp_path / "semi.csv"
    source.write_bytes(b"id;name\r\n1;a\r\n1;a\r\n2;b\r\n")
    outcome = dedup_csv(source, output_dir=tmp_path, delimiter=";")

    proof = _proof(outcome.report_path, scan(source))  # the Scan read it with a comma

    assert proof.reason == "dedup_dialect_mismatch"


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T32")
def test_t32_the_proof_is_read_from_the_json_without_opening_the_csv(tmp_path, monkeypatch):
    source, report = _dedup(tmp_path, population(distinct_ids=200, copies=20))
    result = scan(source)
    opened = []
    real = type(source).open

    def guard(self, *args, **kwargs):
        opened.append(self.name)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(source), "open", guard)

    proof = _proof(report, result)

    assert proof.value == 20
    assert source.name not in opened
    assert not [n for n in opened if n.endswith(".csv")]


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T34")
def test_t34_dedup_and_the_scan_give_one_row_identity_for_unicode_and_multiline_cells(tmp_path):
    source = tmp_path / "n.csv"
    source.write_bytes(
        "id,x\r\né,\"l1\r\nl2\"\r\né,x\r\né,\"l1\r\nl2\"\r\n".encode()
    )
    from tabalyst.dedup_service import dedup_csv

    outcome = dedup_csv(source, output_dir=tmp_path)
    result = scan(source)
    proof = _proof(outcome.report_path, result)

    assert proof.value == result.datasets[0].records.duplicates.count.value == 1
    assert proof.identity == "full_decoded_csv_row_v1"


@pytest.mark.uid_lot("2")
@pytest.mark.uid_t("T15", "T16", "T17")
def test_a_refusal_never_writes_the_dedup_report(tmp_path):
    source, report = _dedup(tmp_path, population(distinct_ids=20, copies=3))
    before = (report.read_bytes(), report.stat().st_mtime_ns)
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("Z-1,new\r\n")

    _proof(report, scan(source))

    assert (report.read_bytes(), report.stat().st_mtime_ns) == before


# ---------------------------------------------------------- lot 3: the Report document


def _unique_csv(tmp_path, name="r.csv", **kwargs):
    return write_csv(tmp_path, name, population(**kwargs))


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T12")
def test_t12_the_report_does_not_read_the_source_again(tmp_path, monkeypatch):
    source = _unique_csv(tmp_path, distinct_ids=995, copies=5)
    from tabalyst.scanner.readers import csv_reader

    reads = []
    real = csv_reader.CsvReader.__iter__

    def counting(self):
        reads.append(self.path)
        return real(self)

    monkeypatch.setattr(csv_reader.CsvReader, "__iter__", counting)

    document = report_document(source)

    assert len(reads) == 1
    assert uniqueness_of(document, "customer_id")["status"] == "complete"


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T25", "T29")
def test_the_porte_3_deliverable_100000_rows_500_copies(tmp_path):
    source = _unique_csv(tmp_path, "big.csv", distinct_ids=99_500, copies=500)

    document = report_document(source)
    item = uniqueness_of(document, "customer_id")

    assert item["interpretation"] == "unique_after_row_deduplication"
    assert item["explanation"]["id_repetitions_residual"] == 0
    assert item["explanation"]["duplicate_row_extra_copies"] == 500
    assert document["report"]["base_scan"] is not None
    assert document["format_revision"] == 5


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T26")
def test_t26_each_dataset_gets_its_own_counts(tmp_path):
    from tabalyst.identifier_uniqueness.facts import facts_from_scan

    source = tmp_path / "two.json"
    source.write_text(
        json.dumps(
            {
                "a": [{"id": 1, "v": "x"}, {"id": 2, "v": "y"}],
                "b": [{"id": 1, "v": "x"}, {"id": 1, "v": "x"}, {"id": 3, "v": "z"}],
            }
        ),
        encoding="utf-8",
    )
    result = scan(source, config=ScanConfig.model_validate({"json": {"collections": ["$.a[]", "$.b[]"]}}))
    ids = {ds.id: next(f.id for f in ds.fields if f.display == "id") for ds in result.datasets}

    a = facts_from_scan(result, "$.a[]", ids["$.a[]"])
    b = facts_from_scan(result, "$.b[]", ids["$.b[]"])

    assert (a.records, b.records) == (2, 3)
    assert (a.duplicates[0].value, b.duplicates[0].value) == (0, 1)


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T27")
def test_t27_a_report_from_a_scan_document_without_the_source_uses_stored_proofs(tmp_path):
    from tabalyst import generate_reports

    source = _unique_csv(tmp_path, distinct_ids=95, copies=5)
    from tabalyst import generate_scans as scans

    scans([source], output_dir=tmp_path / "scans")
    source.unlink()
    document_path = next((tmp_path / "scans").glob("*.scan.json"))

    generate_reports([document_path], output_dir=tmp_path / "out", from_scan=True)
    report = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))

    assert uniqueness_of(report, "customer_id")["interpretation"] == "unique_after_row_deduplication"


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T29", "T30")
def test_t30_a_second_report_of_an_unchanged_file_gives_the_same_object(tmp_path):
    source = _unique_csv(tmp_path, distinct_ids=495, shared_id_rows=5, copies=5)

    first = uniqueness_of(report_document(source), "customer_id")
    second = uniqueness_of(report_document(source), "customer_id")

    assert first == second
    assert first["rule_version"] == 1


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T31")
@pytest.mark.parametrize("exposure", ["show", "mask", "hide"])
def test_t31_the_object_holds_no_id_value_whatever_the_exposure(tmp_path, exposure):
    from tabalyst.report_config import ReportConfig

    rows = population(distinct_ids=40, copies=3)
    source = write_csv(tmp_path, "s.csv", rows)
    config = ReportConfig(scan=ScanConfig.model_validate({"exposure": {"sensitive_values": exposure}}))
    from tabalyst import analyze_csv

    profile = analyze_csv(source, config)
    item = uniqueness_of(json.loads(profile.model_dump_json()), "customer_id")
    text = json.dumps(item)

    assert not any(row[0] in text for row in rows)
    assert item["explanation"]["duplicate_row_extra_copies"] == 3


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T13", "T15", "T16", "T17")
def test_dedup_report_option_is_used_when_given_and_refused_proofs_are_listed(tmp_path):
    rows = population(distinct_ids=2000, copies=600)
    source = write_csv(tmp_path, "o.csv", rows)
    from tabalyst.dedup_service import dedup_csv

    outcome = dedup_csv(source, output_dir=tmp_path / "dd")
    config = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})

    document = report_document(
        source, scan=config, dedup_report=str(outcome.report_path.parent)
    )
    item = uniqueness_of(document, "customer_id")

    assert item["evidence"]["duplicate_rows"]["source"] == "dedup.report"
    assert item["explanation"]["duplicate_row_extra_copies"] == 600


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T13")
def test_the_colocated_dedup_report_is_found_without_an_option(tmp_path):
    rows = population(distinct_ids=2000, copies=600)
    source = write_csv(tmp_path, "c.csv", rows)
    from tabalyst.dedup_service import dedup_csv

    dedup_csv(source, output_dir=tmp_path)
    config = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})

    item = uniqueness_of(report_document(source, scan=config), "customer_id")

    assert item["evidence"]["duplicate_rows"]["report"]["origin"] == "colocated"


@pytest.mark.uid_lot("3")
@pytest.mark.uid_t("T21", "T22", "T23", "T24")
def test_the_scan_classification_and_the_raw_finding_do_not_change(tmp_path):
    source = _unique_csv(tmp_path, distinct_ids=95, copies=5)

    document = report_document(source)
    field = document["datasets"][0]["fields"][0]

    assert (field["classification"]["family"], field["classification"]["type"]) == ("identifier", "id")


# ------------------------------------------------------------------ lot 4: the HTML


@pytest.mark.uid_lot("4")
@pytest.mark.uid_t("T29")
def test_t29_the_html_and_the_json_say_the_same(tmp_path):
    from tabalyst import generate_reports

    source = _unique_csv(tmp_path, distinct_ids=495, shared_id_rows=5, copies=5)
    generate_reports([source], output_dir=tmp_path / "out")
    html = next((tmp_path / "out").glob("*.html")).read_text(encoding="utf-8")
    document = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    item = uniqueness_of(document, "customer_id")

    assert item["explanation"]["id_repetitions_residual"] == 5
    assert "remain between distinct records" in html
    assert "Unique ID" not in html.split("customer_id", 1)[1][:2000]


@pytest.mark.uid_lot("4")
@pytest.mark.uid_t("T29")
def test_a_repetition_is_never_an_automatic_error(tmp_path):
    document = report_document(_unique_csv(tmp_path, distinct_ids=495, shared_id_rows=5))
    column = next(c for c in document["report"]["datasets"][0]["columns"] if c["name"] == "customer_id")

    errors = column["summary"]["findings"]["errors"]["items"]
    assert not [item for item in errors if item["code"].startswith("identifier")]


# ------------------------------------------------------------------------ P1 (not planned)


@pytest.mark.uid_lot("P1")
@pytest.mark.uid_t("T33")
def test_t33_a_count_only_deep_analysis_writes_no_dedup_csv():
    """Lot 6: counts the copies with the Dedup engine, exact or limited, no output file."""
    pytest.fail("P1: written when lot 6 is detailed")
