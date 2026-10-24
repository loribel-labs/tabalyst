# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Lot 2 tests of the Dedup proof beyond the contract tests: refusals and report lookup."""

import json

import pytest
from identifier_uniqueness_helpers import population, write_csv

from tabalyst import scan
from tabalyst.dedup_service import dedup_csv
from tabalyst.errors import InputError

pytestmark = pytest.mark.uid_lot("2")


def _load(report, result, origin="explicit"):
    from tabalyst.identifier_uniqueness.proof import load_dedup_proof

    return load_dedup_proof(report, scan=result, dataset="rows", origin=origin)


def _deduped(tmp_path, copies=3):
    source = write_csv(tmp_path, "d.csv", population(distinct_ids=20, copies=copies))
    return source, dedup_csv(source, output_dir=tmp_path).report_path


def _edit(report, change):
    document = json.loads(report.read_text(encoding="utf-8"))
    change(document)
    report.write_text(json.dumps(document), encoding="utf-8")


def test_a_valid_colocated_report_is_exact_evidence_with_its_reference(tmp_path):
    source, report = _deduped(tmp_path)

    proof = _load(report, scan(source), origin="colocated")

    assert (proof.value, proof.accuracy, proof.source) == (3, "exact", "dedup.report")
    assert proof.report.name == "d.dedup.json"
    assert proof.report.origin == "colocated"
    assert proof.report.content_sha256 == scan(source).source.sha256


def test_a_missing_or_garbled_report_is_unreadable(tmp_path):
    source, _report = _deduped(tmp_path)
    result = scan(source)
    garbled = tmp_path / "g.dedup.json"
    garbled.write_text("{not json", encoding="utf-8")

    assert _load(tmp_path / "absent.dedup.json", result).reason == "dedup_unreadable"
    assert _load(garbled, result).reason == "dedup_unreadable"


def test_a_report_of_a_json_source_is_refused_as_not_csv(tmp_path):
    source, report = _deduped(tmp_path)
    result = scan(source)
    other = tmp_path / "s.json"
    other.write_text('[{"customer_id": "A"}]', encoding="utf-8")
    json_scan = scan(other)
    # Same content hash, so the check that fails is the format of the Scan source.
    json_scan = json_scan.model_copy(
        update={"source": json_scan.source.model_copy(update={"sha256": result.source.sha256})}
    )

    assert _load(report, json_scan).reason == "dedup_not_csv"


def test_an_unsupported_row_identity_is_refused(tmp_path, monkeypatch):
    # Dedup's own schema only knows one identity, so the future value is injected after reading.
    from tabalyst.dedup.report import read_report
    from tabalyst.identifier_uniqueness import proof

    source, report = _deduped(tmp_path)
    parsed = read_report(report)
    other = parsed.model_copy(
        update={"settings": parsed.settings.model_copy(update={"identity": "row_v2"})}
    )
    monkeypatch.setattr(proof, "read_report", lambda _path: other)

    assert _load(report, scan(source)).reason == "dedup_identity_unsupported"


def test_a_forged_report_that_breaks_the_schema_is_unreadable(tmp_path):
    source, report = _deduped(tmp_path)
    _edit(report, lambda d: d["records"].update(total=d["records"]["total"] + 1))

    assert _load(report, scan(source)).reason == "dedup_unreadable"


def test_a_total_that_differs_while_the_report_stays_consistent_is_a_total_mismatch(tmp_path):
    source, report = _deduped(tmp_path)
    result = scan(source)
    longer = result.model_copy(
        update={
            "datasets": [
                result.datasets[0].model_copy(
                    update={"record_count": result.datasets[0].record_count + 1}
                )
            ]
        }
    )

    assert _load(report, longer).reason == "dedup_total_mismatch"


def test_broken_accounting_invariants_are_refused(tmp_path, monkeypatch):
    source, report = _deduped(tmp_path)
    from tabalyst.identifier_uniqueness import proof

    monkeypatch.setattr(proof, "broken_invariants", lambda _report: ["extra_copies"])

    assert _load(report, scan(source)).reason == "dedup_invariants_broken"


def test_encoding_aliases_are_equal_but_utf8_sig_is_not_utf8():
    from tabalyst.identifier_uniqueness.proof import _encoding

    assert _encoding("UTF-8") == _encoding("utf8")
    assert _encoding("utf-8") != _encoding("utf-8-sig")


# ------------------------------------------------------------- where the report comes from


def test_the_colocated_report_is_found_beside_the_source(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source, report = _deduped(tmp_path)

    assert find_dedup_report(source, None) == report
    assert find_dedup_report(tmp_path, None, stem="d") == report


def test_no_colocated_report_is_not_an_error(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source = write_csv(tmp_path, "alone.csv", population(distinct_ids=3))

    assert find_dedup_report(source, None) is None


def test_an_explicit_file_is_used_as_given(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source, report = _deduped(tmp_path)
    moved = tmp_path / "elsewhere.json"
    moved.write_bytes(report.read_bytes())

    assert find_dedup_report(source, moved) == moved


def test_an_explicit_folder_is_searched_for_the_expected_name_only(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source, report = _deduped(tmp_path)
    folder = tmp_path / "reports"
    folder.mkdir()
    (folder / "other.dedup.json").write_bytes(report.read_bytes())

    with pytest.raises(InputError):
        find_dedup_report(source, folder)
    (folder / "d.dedup.json").write_bytes(report.read_bytes())
    assert find_dedup_report(source, folder) == folder / "d.dedup.json"


def test_a_missing_explicit_file_is_an_error_of_the_option(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source, _ = _deduped(tmp_path)

    with pytest.raises(InputError):
        find_dedup_report(source, tmp_path / "nope.dedup.json")


def test_the_option_does_not_fall_back_to_the_colocated_report(tmp_path):
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    source, _ = _deduped(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(InputError):
        find_dedup_report(source, empty)
