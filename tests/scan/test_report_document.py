# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report as a superset of the Scan and the common loader (plan tests A02,
A10, A11, A14; design 19)."""

import copy
import json
import shutil
from pathlib import Path

import jsonschema
import pytest
from scan_helpers import dataset, field, write_json, write_text

from tabalyst import generate_reports, generate_scans, render_report
from tabalyst.errors import InputError
from tabalyst.report_schema import SCHEMA_FILE, report_schema, report_schema_text
from tabalyst.reporting import load_profile
from tabalyst.scan_document import facts_sha256, load_base, load_document
from tabalyst.scanner.schema import scan_schema
from tabalyst.scanner.validation import check_scan

pytestmark = pytest.mark.scan_json_lot("1b")

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "examples" / "datasets"
SOURCES = ["insurance-customers.csv", "orders.json", "web-events.jsonl"]
CSV = "id,city,amount\n1,Paris,10\n2,,x\n3,Lyon,30\n1,Paris,10\n"


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage")
    )


def _written(tmp_path: Path, content: str = CSV, name: str = "data.csv", **options):
    """Write the scan and the report of a source; return both documents."""
    source = write_text(tmp_path, name, content)
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    batch = generate_reports(
        [tmp_path / "scans" / f"{source.stem}.scan.json"],
        output_dir=tmp_path / "reports",
        from_scan=True,
        force=True,
        **options,
    )
    assert batch.succeeded
    return (
        tmp_path / "scans" / f"{source.stem}.scan.json",
        tmp_path / "reports" / f"{source.stem}.json",
    )


def _profile_file(directory: Path) -> Path:
    return next(p for p in directory.glob("*.json") if p.name != "executions.json")


def _ids(count: int) -> str:
    return "id\n" + "\n".join(f"C{n:04d}" for n in range(count)) + "\n"


@pytest.mark.scan_json_lot("1b")
def test_A10_a_report_sent_alone_is_read_and_rendered_without_scan_or_source(tmp_path):
    scan_file, report_file = _written(tmp_path)
    alone = tmp_path / "elsewhere"
    alone.mkdir()
    copied = alone / "report.json"
    shutil.copy(report_file, copied)

    document = load_document(copied)
    html = render_report(load_profile(copied))

    assert document.kind == "report"
    assert document.base.source.name == "data.csv"
    assert "data" in html and "Paris" in html
    assert load_base(copied).source.sha256 == load_base(scan_file).source.sha256


@pytest.mark.scan_json_lot("1b")
def test_A11_a_consumer_of_the_base_receives_a_report(tmp_path):
    scan_file, report_file = _written(tmp_path)

    from_scan = load_document(scan_file)
    from_report = load_document(report_file)

    assert (from_scan.kind, from_report.kind) == ("scan", "report")
    base, expected = from_report.base, from_scan.base
    assert base.config == expected.config
    assert base.config_sha256 == expected.config_sha256
    assert base.scope == expected.scope
    assert base.diagnostics == expected.diagnostics
    assert [(d.id, [f.id for f in d.fields]) for d in base.datasets] == [
        (d.id, [f.id for f in d.fields]) for d in expected.datasets
    ]
    # A file of a few rows keeps every row of its row sample.
    assert [d.records.sample.kept for d in base.datasets] == [4]
    assert base.datasets == expected.datasets  # envelopes included
    assert check_scan(base) == []
    assert from_report.report is not None and from_scan.report is None


@pytest.mark.parametrize("name", SOURCES)
def test_the_base_of_a_report_is_the_scan_of_the_same_source(tmp_path, name):
    source = INPUT / name
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    scan_file = next((tmp_path / "scans").glob("*.scan.json"))
    generate_reports(
        [scan_file], output_dir=tmp_path / "reports", from_scan=True, force=True
    )
    report_file = _profile_file(tmp_path / "reports")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    scan_document = load_base(scan_file)
    base = load_base(report_file)

    assert report["report"]["base_scan"]["facts_sha256"] == facts_sha256(scan_document)
    assert facts_sha256(base) == facts_sha256(scan_document)
    # The sample is the only difference the Report may make (design 19.4).
    for kept, whole in zip(base.datasets, scan_document.datasets, strict=True):
        for left, right in zip(kept.fields, whole.fields, strict=True):
            assert left.model_copy(
                update={"values": right.values}
            ) == right, left.display
            assert left.values.samples.of == right.values.samples.of
    assert check_scan(base) == []


def test_a_report_keeps_a_declared_subset_of_a_larger_sample(tmp_path):
    scan_file, report_file = _written(tmp_path, _ids(150), "ids.csv")

    whole = load_base(scan_file).datasets[0].fields[0].values.samples
    kept = load_base(report_file).datasets[0].fields[0].values.samples
    document = load_document(report_file)

    assert (whole.kept, whole.of) == (150, 150)
    assert (kept.kept, kept.of) == (100, 150)
    assert len(kept.listed) == 100
    # Exact counters of an exact subset.
    assert all(item in whole.listed for item in kept.listed)
    assert document.capabilities.complete_samples is False
    assert load_document(scan_file).capabilities.complete_samples is True
    with pytest.raises(InputError, match="fewer sample values"):
        document.require_complete_samples("plan a second pass")
    load_document(scan_file).require_complete_samples("plan a second pass")


def test_a_report_with_all_its_values_is_complete(tmp_path):
    source = write_text(tmp_path, "data.csv", CSV)
    config = write_json(
        tmp_path, "rows.json", {"scan": {"records": {"sample": {"rows": 0}}}}
    )
    generate_scans(
        [source], output_dir=tmp_path / "scans", config_path=config, force=True
    )
    generate_reports(
        [tmp_path / "scans" / "data.scan.json"],
        output_dir=tmp_path / "reports",
        config_path=config,
        from_scan=True,
        force=True,
    )

    document = load_document(tmp_path / "reports" / "data.json")

    assert document.capabilities.complete_samples is True


def test_a_report_without_the_rows_of_its_row_sample_is_not_complete(tmp_path):
    config = write_json(
        tmp_path,
        "rows.json",
        {"report": {"row_sample": {"start": 0, "middle": 0, "end": 0}}},
    )
    _, report_file = _written(tmp_path, config_path=config)

    assert load_document(report_file).capabilities.complete_samples is False


def test_a_report_with_every_row_of_a_small_sample_is_complete(tmp_path):
    _, report_file = _written(tmp_path)

    assert load_document(report_file).capabilities.complete_samples is True
    assert check_scan(load_base(report_file)) == []


@pytest.mark.scan_json_lot("1b")
def test_A14_a_presentation_change_does_not_scan_again(tmp_path, monkeypatch):
    source = write_text(tmp_path, "data.csv", CSV)
    plain = write_json(tmp_path, "plain.json", {})
    presented = write_json(
        tmp_path, "presented.json", {"report": {"value_examples": {"inline_display_size": 1}}}
    )
    first = generate_reports(
        [source], output=tmp_path / "a" / "data.html", config_path=plain, force=True
    )
    assert first.succeeded

    def refuse(*args, **kwargs):
        raise AssertionError("the source was scanned again")

    monkeypatch.setattr("tabalyst.shared_scan_service.scan", refuse)
    second = generate_reports(
        [source],
        output=tmp_path / "b" / "data.html",
        config_path=presented,
        force=True,
    )

    assert second.succeeded
    one = json.loads((tmp_path / "a" / "data.json").read_text(encoding="utf-8"))
    two = json.loads((tmp_path / "b" / "data.json").read_text(encoding="utf-8"))
    assert one["report"]["base_scan"] == two["report"]["base_scan"]
    assert one["report"]["config"] != two["report"]["config"]
    assert one["report"]["config"]["value_examples"]["inline_display_size"] != 1
    assert two["report"]["config"]["value_examples"]["inline_display_size"] == 1
    assert one["config"] == two["config"]


@pytest.mark.scan_json_lot("1b")
def test_A14_a_presentation_change_leaves_the_scan_file_untouched(tmp_path):
    source = write_text(tmp_path, "data.csv", CSV)
    generate_scans([source], output_dir=tmp_path / "scans", force=True)
    scan_file = tmp_path / "scans" / "data.scan.json"
    before = scan_file.read_bytes()
    presented = write_json(
        tmp_path, "presented.json", {"report": {"value_examples": {"inline_display_size": 1}}}
    )

    batch = generate_reports(
        [scan_file],
        output_dir=tmp_path / "reports",
        config_path=presented,
        from_scan=True,
        force=True,
    )

    assert batch.succeeded
    assert scan_file.read_bytes() == before


def test_a_report_cannot_be_reported_again(tmp_path):
    _, report_file = _written(tmp_path)

    batch = generate_reports(
        [report_file], output_dir=tmp_path / "again", from_scan=True, force=True
    )

    assert batch.succeeded is False
    (failure,) = batch.failures
    assert isinstance(failure.error, InputError)
    assert "is a Report" in str(failure.error)


def test_a_report_of_another_revision_is_refused_not_converted(tmp_path):
    _, report_file = _written(tmp_path)
    original = json.loads(report_file.read_text(encoding="utf-8"))

    older = copy.deepcopy(original)
    older["format_revision"] = 1
    other_base = copy.deepcopy(original)
    other_base["report"]["base_scan"]["format_revision"] = 1

    for document, text in ((older, "format 0.2.0 revision 1"), (other_base, "Scan base of format")):
        report_file.write_text(json.dumps(document), encoding="utf-8")
        for load in (load_document, load_profile):
            with pytest.raises(InputError, match=text):
                load(report_file)


def test_a_report_whose_base_was_modified_is_refused(tmp_path):
    _, report_file = _written(tmp_path)
    document = json.loads(report_file.read_text(encoding="utf-8"))
    document["datasets"][0]["fields"][0]["occurrences"] += 1
    report_file.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(InputError, match="does not match the identity"):
        load_base(report_file)


def test_a_document_that_is_neither_scan_nor_report_is_refused(tmp_path):
    other = write_json(tmp_path, "other.json", {"format": "tabalyst.inspect"})

    with pytest.raises(InputError, match="Not a Tabalyst document"):
        load_document(other)


@pytest.mark.shipped_exposure_default
def test_the_committed_report_schema_is_the_generated_one():
    committed = ROOT / "src" / "tabalyst" / "schemas" / SCHEMA_FILE
    assert committed.read_text(encoding="utf-8") == report_schema_text()


@pytest.mark.parametrize("name", SOURCES)
def test_a_report_satisfies_its_schema_and_its_base_the_scan_schema(tmp_path, name):
    source = INPUT / name
    generate_reports([source], output_dir=tmp_path, force=True)
    report_file = _profile_file(tmp_path)
    report = json.loads(report_file.read_text(encoding="utf-8"))

    jsonschema.validate(report, report_schema())
    base = {k: v for k, v in report.items() if k != "report"}
    base["format"] = report["report"]["base_scan"]["format"]
    base["format_revision"] = report["report"]["base_scan"]["format_revision"]
    jsonschema.validate(base, scan_schema())


def test_the_report_schema_rejects_a_document_without_its_block(tmp_path):
    _, report_file = _written(tmp_path)
    report = json.loads(report_file.read_text(encoding="utf-8"))
    del report["report"]["base_scan"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, report_schema())


def test_the_report_holds_no_second_copy_of_the_scan_facts(tmp_path):
    _, report_file = _written(tmp_path)
    report = json.loads(report_file.read_text(encoding="utf-8"))

    column = dataset(report["report"], "rows")["columns"][0]
    assert not {"scan_details", "numeric", "string_profile", "date_profile"} & set(
        column
    )
    assert "source" not in report["report"]
    assert field(dataset(report, "rows"), "amount")["numeric"]


def test_the_validator_checks_the_declared_size_of_a_sample(tmp_path):
    scan_file, _ = _written(tmp_path)
    base = load_base(scan_file)
    samples = base.datasets[0].fields[0].values.samples
    broken_samples = samples.model_copy(update={"kept": samples.kept + 1})
    values = base.datasets[0].fields[0].values.model_copy(
        update={"samples": broken_samples}
    )
    fields = [base.datasets[0].fields[0].model_copy(update={"values": values})]
    dataset_result = base.datasets[0].model_copy(update={"fields": fields})

    problems = check_scan(base.model_copy(update={"datasets": [dataset_result]}))

    assert any("kept does not match the listing" in problem for problem in problems)


def test_a_report_whose_projection_names_an_unknown_field_is_refused(tmp_path):
    _, report_file = _written(tmp_path)
    document = json.loads(report_file.read_text(encoding="utf-8"))
    document["report"]["datasets"][0]["columns"][0]["id"] = "column_99"
    report_file.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(InputError, match="has no field in its Scan base"):
        load_profile(report_file)
