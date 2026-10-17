# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Details of a column (Report overview lot R8).

The contract is ``docs/dev/report/summary-table.md`` 7.2. The tests check the
exposure of every value, the limits of the lists and the links, not the wording.
"""

from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.report_config import ReportConfig
from tabalyst.report_details import details_for, details_link
from tabalyst.reporting import _environment, dataset_views
from tabalyst.scanner import ScanConfig


def _csv(tmp_path, header, cells, **settings):
    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(cells)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return dataset_views(analyze_csv(source, config))[0].columns[0]


def _measures(details):
    return {item.name: item for item in details.measures}


def test_an_enum_lists_its_values_with_counts_and_shares(tmp_path):
    column = _csv(tmp_path, "status", ["open"] * 6 + ["closed"] * 3 + ["held"])

    details = details_for(column)

    assert details.state == "shown"
    by_value = {item.value: item for item in details.examples}
    assert by_value["open"].count == 6 and by_value["open"].share == 0.6
    assert details.total == 3


def test_a_complete_listing_is_exhaustive_and_has_no_limit_note(tmp_path):
    column = _csv(tmp_path, "status", ["open"] * 6 + ["closed"] * 4)

    details = details_for(column)

    assert details.exhaustive and details.note is None


def test_a_listing_shorter_than_the_distinct_values_is_never_said_exhaustive(tmp_path):
    column = _csv(tmp_path, "customer_id", [f"C{n:05d}" for n in range(200)])

    details = details_for(column)

    assert not details.exhaustive
    assert len(details.examples) < 200 and details.total == 200
    assert details.note and "not exhaustive" in details.note


def test_a_limited_cardinality_gives_a_lower_bound_total(tmp_path):
    cells = [f"C{n:05d}" for n in range(100)]
    column = _csv(tmp_path, "customer_id", cells, limits={"max_distinct_per_field": 50})

    details = details_for(column)

    assert not details.exhaustive
    assert details.total_accuracy == "lower_bound"
    assert details.note and "at least" in details.note


def test_a_masked_column_lists_merged_masks_and_no_raw_value(tmp_path):
    cells = [f"user{n}@example.com" for n in range(30)]
    column = _csv(tmp_path, "contact", cells, exposure={"sensitive_values": "mask"})

    details = details_for(column)

    assert details.state == "masked" and not details.exhaustive
    assert details.total is None
    assert "user" not in details.model_dump_json()
    assert all(not item.value.startswith("user") for item in details.examples)


def test_a_hidden_column_lists_nothing_and_keeps_its_measures(tmp_path):
    cells = [f"user{n}@example.com" for n in range(30)]
    column = _csv(tmp_path, "contact", cells, exposure={"sensitive_values": "hide"})

    details = details_for(column)

    assert details.state == "hidden" and details.examples == []
    assert "example.com" not in details.model_dump_json()
    assert details.note


def test_the_gate_applies_again_to_a_document_holding_raw_values(tmp_path):
    cells = [f"user{n}@example.com" for n in range(30)]
    column = _csv(tmp_path, "contact", cells, exposure={"sensitive_values": "show"})
    assert column.value_profile.values
    for mode in ("mask", "hide"):
        gated = column.model_copy(update={"exposure": mode})

        text = details_for(gated).model_dump_json()

        assert "user" not in text and "example.com" not in text


def test_detector_keys_are_listed_only_for_a_shown_column(tmp_path):
    cells = [f"user{n}@example.com" for n in range(30)] + ["a@other.org"] * 5
    column = _csv(tmp_path, "contact", cells, exposure={"sensitive_values": "show"})
    shown = details_for(column)
    hidden = details_for(column.model_copy(update={"exposure": "hide"}))

    assert _measures(shown)["matched_percent"].accuracy == "exact"
    assert any(item.name == "key" for item in shown.measures)
    assert not any(item.name == "key" for item in hidden.measures)


def test_numeric_details_give_the_mean_and_nothing_for_codes(tmp_path):
    numeric = _csv(tmp_path, "amount", ["1.5", "2.5", "3.5", "4.5"] * 5)
    codes = _csv(tmp_path, "customer_id", [f"C{n:05d}" for n in range(50)])

    assert _measures(details_for(numeric))["mean"].value == 3.0
    assert details_for(codes).measures == []


def test_text_details_give_the_lengths_or_the_fixed_length(tmp_path):
    varied = _csv(tmp_path, "comment", ["ab", "abcd", "abcdef"] * 10)
    fixed = _csv(tmp_path, "comment", ["abcd", "wxyz"] * 10)

    assert {"minimum_length", "maximum_length", "mean_length"} <= set(
        _measures(details_for(varied))
    )
    assert _measures(details_for(fixed))["fixed_length"].value == 4


def test_temporal_details_list_the_recognized_formats(tmp_path):
    column = _csv(tmp_path, "day", ["2024-01-15", "2024-02-20", "2024-03-31"] * 5)

    formats = [item for item in details_for(column).measures if item.name == "format"]

    assert formats and sum(item.value for item in formats) == 15


def test_a_value_that_looks_like_markup_or_a_formula_is_kept_and_escaped(tmp_path):
    cells = ["<script>alert(1)</script>", "=SUM(A1:A9)", "plain"] * 10
    column = _csv(tmp_path, "note", cells)

    details = details_for(column)

    values = {item.value for item in details.examples}
    assert "<script>alert(1)</script>" in values and "=SUM(A1:A9)" in values
    rendered = _environment().from_string("{{ v }}").render(
        v="<script>alert(1)</script>"
    )
    assert "<script>" not in rendered


def test_a_link_exists_only_for_a_page_that_was_written():
    links = {("d1", "name"): "report/col-01-name.html"}

    assert details_link(links, "d1", "name") == "report/col-01-name.html"
    assert details_link(links, "d1", "other") is None
    assert details_link({}, "d1", "name") is None
    assert details_link(None, "d1", "name") is None


def test_details_hold_examples_and_measures_only_no_alert_member(tmp_path):
    column = _csv(tmp_path, "status", ["open"] * 20 + ["OPEN "])

    assert set(type(details_for(column)).model_fields) == {
        "state",
        "examples",
        "exhaustive",
        "total",
        "total_accuracy",
        "note",
        "measures",
    }


def test_a_truncated_stored_value_is_flagged_in_the_examples(tmp_path):
    column = _csv(tmp_path, "note", ["abc"] * 10)
    cut = column.value_profile.values[0].model_copy(update={"truncated": True})
    profile = column.value_profile.model_copy(update={"values": [cut]})

    details = details_for(column.model_copy(update={"value_profile": profile}))

    assert details.examples[0].truncated
