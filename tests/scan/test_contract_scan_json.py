# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the shared Scan and Report document (plan tests A01 to A06).

Tests of lot ``0`` describe behavior that exists today and must keep passing
through the whole work: they are the non-regression guard. The others name the
lot that delivers them and are expected to fail until then (see
``conftest.py``). The expectations follow ``docs/dev/scan/design.md``
sections 9.11 and 18 to 20.
"""

import hashlib
import json
from pathlib import Path

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

from tabalyst import ScanConfig, analyze_csv, generate_reports, generate_scans, scan
from tabalyst.errors import InputError
from tabalyst.scanner.config import config_sha256

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "input"
INSURANCE = EXAMPLES / "insurance-customers.csv"
ORDERS = EXAMPLES / "orders.json"

ROOT_KEYS = {
    "format",
    "format_version",
    "format_revision",
    "engine",
    "status",
    "run",
    "source",
    "config",
    "config_sha256",
    "scope",
    "datasets",
    "diagnostics",
}
DATASET_KEYS = {
    "id",
    "kind",
    "collection_path",
    "record_count",
    "record_types",
    "structure",
    "records",
    "fields",
}
FIELD_KEYS = {
    "id",
    "path",
    "display",
    "name",
    "parent",
    "collection",
    "first_record",
    "occurrences",
    "presence",
    "native_types",
    "strings",
    "missing",
    "arrays",
    "values",
    "string_characteristics",
    "string_lengths",
    "numeric",
    "booleans",
    "temporal",
    "normalization",
    "technical_type",
    "detectors",
    "interpretations",
    "sensitive",
    "exposure",
}
VALUES_KEYS = {"count", "cardinality", "frequencies", "samples", "first", "last"}


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage")
    )


def _dump(path: Path, **settings) -> dict:
    config = ScanConfig.model_validate(settings)
    return scan(path, config=config, workers=1).model_dump(mode="json", by_alias=True)


@pytest.mark.scan_json_lot("0")
@pytest.mark.parametrize("fixture", [INSURANCE, ORDERS], ids=lambda path: path.name)
def test_A01_current_structure_is_the_base_the_new_model_keeps(fixture):
    document = _dump(fixture)

    # The new model only adds to these keys (JSON-02): nothing is renamed.
    assert ROOT_KEYS <= set(document)
    assert document["format"] == "tabalyst.scan"
    assert document["format_version"] == "0.2.0"
    assert document["source"]["name"] == fixture.name
    assert document["source"]["size_bytes"] == fixture.stat().st_size
    assert (
        document["source"]["sha256"] == hashlib.sha256(fixture.read_bytes()).hexdigest()
    )
    assert document["config_sha256"] == config_sha256(
        ScanConfig.model_validate(document["config"])
    )
    for item in document["datasets"]:
        assert DATASET_KEYS <= set(item)
        for each in item["fields"]:
            assert FIELD_KEYS <= set(each)
            assert VALUES_KEYS <= set(each["values"])


@pytest.mark.scan_json_lot("0")
def test_A01_insurance_dimensions_and_identifiers_are_stable():
    document = _dump(INSURANCE)
    (rows,) = document["datasets"]

    assert rows["id"] == "rows"
    assert rows["record_count"] == 3000
    assert [item["id"] for item in rows["fields"]] == [
        f"column_{n}" for n in range(1, 35)
    ]
    assert document["scope"]["records_analyzed"] == 3000


@pytest.mark.scan_json_lot("1a")
def test_A01_new_model_extends_the_current_envelopes():
    document = _dump(INSURANCE)

    limits = document["config"]["limits"]
    assert limits["max_distinct_per_field"] == 100_000  # T keeps its default
    assert limits["max_samples"] == 10_000  # K, the bottom-k sample size
    for item in dataset(document, "rows")["fields"]:
        cardinality = item["values"]["cardinality"]
        assert cardinality["domain"] == "original"
        if cardinality["status"] == "complete":
            assert cardinality["accuracy"] == "exact"
            assert cardinality["identity_accuracy"] == "exact"


@pytest.mark.scan_json_lot("1b")
def test_A02_report_base_equals_the_scan_base(tmp_path):
    from tabalyst.scan_document import load_base

    source = write_text(
        tmp_path,
        "data.csv",
        "id,city,amount\n1,Paris,10\n2,,x\n3,Lyon,30\n1,Paris,10\n",
    )
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    scan_file = tmp_path / "scans" / "data.scan.json"
    generate_reports(
        [scan_file], output_dir=tmp_path / "reports", from_scan=True, force=True
    )
    report_file = tmp_path / "reports" / "data.json"

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["format"] == "tabalyst.report"
    base = load_base(report_file).model_dump(mode="json", by_alias=True)
    expected = load_base(scan_file).model_dump(mode="json", by_alias=True)
    # The Report declares the rows of the row sample it does not keep (P6,
    # design 18.11); every other fact is the Scan's.
    for dataset_ in base["datasets"]:
        sample = dataset_["records"]["sample"]
        assert (sample["kept"], sample["rows"]) == (0, [])
        sample.update(kept=sample["of"], rows=None)
    for dataset_ in expected["datasets"]:
        sample = dataset_["records"]["sample"]
        assert sample["kept"] == sample["of"] == len(sample["rows"])
        sample["rows"] = None
    assert base == expected  # no lost detector, status or rounding
    assert load_base(scan_file).format == "tabalyst.scan"


@pytest.mark.scan_json_lot("1c")
def test_A02_report_keeps_a_declared_subset_of_the_scan_sample(tmp_path):
    from tabalyst.scan_document import load_base

    values = [f"id{n:04d}" for n in range(60)]
    source = write_text(tmp_path, "ids.csv", "id\n" + "\n".join(values) + "\n")
    config = write_json(
        tmp_path,
        "tabalyst.json",
        {
            "report": {"value_examples": {"kept_per_column": 5}},
            "scan": {"limits": {"max_distinct_per_field": 30, "max_samples": 20}},
        },
    )
    generate_scans(
        [source], output_dir=tmp_path / "scans", config_path=config, force=True
    )
    generate_reports(
        [tmp_path / "scans" / "ids.scan.json"],
        output_dir=tmp_path / "reports",
        config_path=config,
        from_scan=True,
        force=True,
    )

    scan_samples = _id_samples(load_base(tmp_path / "scans" / "ids.scan.json"))
    report_samples = _id_samples(load_base(tmp_path / "reports" / "ids.json"))
    assert (scan_samples["kept"], scan_samples["of"]) == (20, 20)
    # Smallest priorities first: the Report keeps the head of the Scan's sample.
    assert (report_samples["kept"], report_samples["of"]) == (5, 20)
    assert report_samples["listed"] == scan_samples["listed"][:5]


def _id_samples(base) -> dict:
    document = base.model_dump(mode="json", by_alias=True)
    return field(dataset(document, "rows"), "id")["values"]["samples"]


@pytest.mark.scan_json_lot("0")
def test_A03_missing_rate_counts_empty_values_over_the_value_slots(tmp_path):
    profile = analyze_csv(_rates_csv(tmp_path))
    rows = profile.report.datasets[0]
    amount = _column(rows, "amount")

    assert (amount.missing_count, amount.missing_percent) == (2, 9.09)  # 2 / 22
    assert (rows.summary.missing_count, rows.summary.missing_percent) == (
        5,
        7.58,
    )  # 5 / 66
    assert rows.summary.cell_count == 66


@pytest.mark.scan_json_lot("0")
def test_A03_type_error_rate_counts_outside_values_over_the_typed_population(tmp_path):
    amount = _column(analyze_csv(_rates_csv(tmp_path)).report.datasets[0], "amount")

    # 1 value outside the integer family among 20 values: the 2 empty values
    # are not in the population, so it is 5.0, not 1 / 22.
    assert amount.inferred_type == "integer"
    assert (amount.type_error_count, amount.type_error_percent) == (1, 5.0)


@pytest.mark.scan_json_lot("0")
def test_A03_normalization_rates_count_changed_content_over_all_value_slots(tmp_path):
    name = _column(analyze_csv(_rates_csv(tmp_path)).report.datasets[0], "name")

    # 3 trimmed and 2 collapsed content values, over the 22 slots of the
    # column (the 3 empty cells included): 13.64 and 9.09.
    assert (name.normalization.trim_count, name.normalization.trim_percent) == (
        3,
        13.64,
    )
    assert name.normalization.collapse_internal_whitespace_count == 2
    assert name.normalization.collapse_internal_whitespace_percent == 9.09


@pytest.mark.scan_json_lot("0")
def test_A03_json_slots_add_the_objects_where_the_field_is_absent(tmp_path):
    source = write_json(
        tmp_path,
        "records.json",
        [{"a": 1, "b": 2}, {"a": 3}, {"a": 4, "b": None}, {"a": 5, "b": 6}],
    )
    dataset_profile = analyze_csv(source).report.datasets[0]
    b = _column(dataset_profile, "b")

    # 3 occurrences + 1 absent = 4 slots; null and absent are missing: 2 / 4.
    assert (b.missing_count, b.missing_percent) == (2, 50.0)


@pytest.mark.scan_json_lot("0")
def test_A03_scan_shares_are_fractions_and_report_percents_are_0_to_100(tmp_path):
    source = write_text(tmp_path, "mail.csv", "email\n" + "a@example.com\nbad\n" * 5)
    document = run_scan(source)
    email = field(dataset(document, "rows"), "email")
    coverage = next(item for item in email["detectors"] if item["id"] == "email")[
        "coverage"
    ]
    assert coverage["share_eligible"] == 0.5  # a part, 0 to 1

    detector = next(
        item
        for item in _column(analyze_csv(source).report.datasets[0], "email").detectors
        if item.id == "email"
    )
    assert detector.matched_percent == 50.0  # a percentage, 0 to 100


@pytest.mark.scan_json_lot("0")
def test_A03_rates_are_documented_with_their_denominators():
    design = (
        Path(__file__).resolve().parents[2] / "docs/dev/scan/design.md"
    ).read_text(encoding="utf-8")
    start = design.index("### 9.11 Rates of the report")
    section = design[start : design.index("\n## ", start)]
    for name in (
        "missing_percent",
        "type_error_percent",
        "trim_percent",
        "collapse_internal_whitespace_percent",
    ):
        assert name in section
    assert "value_slots" in section
    assert "values.count" in section


@pytest.mark.scan_json_lot("1b")
def test_A04_report_columns_hold_no_copy_of_scan_facts(tmp_path):
    profile = analyze_csv(_rates_csv(tmp_path))
    column = _column(profile.report.datasets[0], "amount")

    # The Report reads the statistics where the Scan keeps them.
    for copy in ("scan_details", "numeric", "string_profile", "date_profile"):
        assert not hasattr(column, copy), copy


def _limited_cardinality(tmp_path) -> dict:
    """The cardinality of an identifier column of 25 values, tracked up to 10."""
    source = write_text(
        tmp_path,
        "ids.csv",
        "id_client\n" + "\n".join(f"C{n:05d}" for n in range(25)) + "\n",
    )
    result = run_scan(source, limits={"max_distinct_per_field": 10, "max_samples": 10})
    return field(dataset(result, "rows"), "id_client")["values"]["cardinality"]


@pytest.mark.scan_json_lot("0")
def test_A05_limited_cardinality_keeps_limit_bound_and_reason(tmp_path):
    cardinality = _limited_cardinality(tmp_path)

    assert cardinality["status"] == "limited"
    assert cardinality["reason"] == "distinct_limit"
    assert cardinality["limit"] == 10
    assert cardinality["lower_bound"] == 11


@pytest.mark.scan_json_lot("1a")
def test_A05_limited_cardinality_names_its_domain_and_where_tracking_stopped(tmp_path):
    cardinality = _limited_cardinality(tmp_path)

    assert cardinality["domain"] == "original"
    assert cardinality["identity_accuracy"] == "exact"
    assert cardinality["threshold_reached_at_record"] == 10
    assert cardinality["overflow_detected_at_record"] == 11
    assert cardinality["upper_bound"] == 25


@pytest.mark.scan_json_lot("0")
def test_A06_a_scan_document_of_another_revision_is_refused(tmp_path):
    source = write_text(tmp_path, "data.csv", "id\n1\n2\n")
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    document = tmp_path / "scans" / "data.scan.json"
    data = json.loads(document.read_text(encoding="utf-8"))
    data["format_revision"] = 1
    document.write_text(json.dumps(data), encoding="utf-8")

    outcome = generate_reports(
        [document], output_dir=tmp_path / "reports", from_scan=True, force=True
    )

    # The document fails its own job, with a request to scan again.
    assert outcome.succeeded is False
    (failure,) = outcome.failures
    assert isinstance(failure.error, InputError)
    assert "Run tabalyst scan again" in str(failure.error)
    assert not (tmp_path / "reports").exists()


@pytest.mark.scan_json_lot("0")
def test_A06_a_stored_scan_of_another_revision_is_scanned_again_not_converted(tmp_path):
    from tabalyst.projects.location import StorageLocation
    from tabalyst.shared_scan_service import current_scan

    source = write_text(tmp_path, "data.csv", "id\n1\n2\n")
    location = StorageLocation.local()
    first = current_scan(source, ScanConfig(), location=location, workers=1)
    assert first.reused is False
    data = json.loads(first.path.read_text(encoding="utf-8"))
    data["format_revision"] = 1
    first.path.write_text(json.dumps(data), encoding="utf-8")

    second = current_scan(source, ScanConfig(), location=location, workers=1)

    assert second.reused is False
    assert json.loads(second.path.read_text(encoding="utf-8"))["format_revision"] != 1


def _rates_csv(tmp_path) -> Path:
    """22 rows: `amount` has 19 integers, 1 text and 2 empty values; `name` has
    3 values with surrounding whitespace, 2 with a repeated inner space, 14
    plain and 3 empty."""
    amounts = [str(10 + n) for n in range(19)] + ["x", "", ""]
    names = (
        [f"Name{n}" for n in range(14)]
        + [" Bob ", "Cy ", " Di"]
        + ["a  b", "c   d"]
        + ["", "", ""]
    )
    lines = ["id,amount,name"]
    lines += [
        f"{n},{amount},{name}"
        for n, (amount, name) in enumerate(zip(amounts, names, strict=True))
    ]
    return write_text(tmp_path, "rates.csv", "\n".join(lines) + "\n")


def _column(dataset_profile, name):
    return next(column for column in dataset_profile.columns if column.name == name)


@pytest.mark.scan_json_lot("1a")
def test_a_stored_scan_that_no_longer_satisfies_the_model_is_scanned_again(tmp_path):
    from tabalyst.projects.location import StorageLocation
    from tabalyst.shared_scan_service import current_scan

    source = write_text(tmp_path, "data.csv", "id\n1\n2\n")
    location = StorageLocation.local()
    first = current_scan(source, ScanConfig(), location=location, workers=1)
    data = json.loads(first.path.read_text(encoding="utf-8"))
    # A document of the current revision written before a member became
    # required (the revision in progress is not published yet).
    del data["datasets"][0]["fields"][0]["values"]["cardinality"]["accuracy"]
    first.path.write_text(json.dumps(data), encoding="utf-8")

    second = current_scan(source, ScanConfig(), location=location, workers=1)

    assert second.reused is False
    stored = json.loads(second.path.read_text(encoding="utf-8"))
    assert stored["datasets"][0]["fields"][0]["values"]["cardinality"]["accuracy"] == (
        "exact"
    )


@pytest.mark.scan_json_lot("1a")
def test_a_scan_file_that_no_longer_satisfies_the_model_asks_for_a_new_scan(tmp_path):
    source = write_text(tmp_path, "data.csv", "id\n1\n2\n")
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    document = tmp_path / "scans" / "data.scan.json"
    data = json.loads(document.read_text(encoding="utf-8"))
    del data["datasets"][0]["fields"][0]["values"]["cardinality"]["domain"]
    document.write_text(json.dumps(data), encoding="utf-8")

    outcome = generate_reports(
        [document], output_dir=tmp_path / "reports", from_scan=True, force=True
    )

    assert outcome.succeeded is False
    (failure,) = outcome.failures
    assert "run tabalyst scan again" in str(failure.error)
