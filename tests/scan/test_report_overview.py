# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Overview sentences of a column (Report overview lot R7).

The contract is ``docs/dev/report/summary-table.md`` 7.1. The tests read the
facts a sentence uses (``Overview.facts``) and the words that RF-10 forbids;
they do not freeze the wording.
"""

from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.report_config import ReportConfig
from tabalyst.report_overview import overview_for, overview_sentence, overview_text
from tabalyst.reporting import dataset_views
from tabalyst.scanner import ScanConfig


def _csv(tmp_path, header, cells, **settings):
    """The view of the first column of a CSV; a second column of row numbers lets
    the first one hold empty cells."""
    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(cells)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return dataset_views(analyze_csv(source, config))[0].columns[0]


def _facts(column):
    return {fact.name: fact for fact in overview_for(column).facts}


def test_a_unique_identifier_says_all_present_values_are_distinct(tmp_path):
    column = _csv(tmp_path, "customer_id", [f"C{n:05d}" for n in range(100)])

    overview = overview_for(column)

    assert column.classification.type == "unique_id"
    assert overview_sentence(overview).startswith("All 100 present values are distinct")
    assert _facts(column)["present"].value == 100


def test_an_identifier_gives_its_distinct_values_and_formats(tmp_path):
    cells = [f"C{n:05d}" for n in range(100)] + ["C00001"]
    column = _csv(tmp_path, "customer_id", cells)

    assert column.classification.type == "id"
    facts = _facts(column)
    assert facts["distinct"].value == 100 and facts["distinct"].accuracy == "exact"
    assert overview_text(column).startswith("100 distinct values")


def test_a_limited_cardinality_is_never_said_exact(tmp_path):
    cells = [f"C{n:05d}" for n in range(100)] + ["C00001"]
    column = _csv(tmp_path, "customer_id", cells, limits={"max_distinct_per_field": 50})

    facts = _facts(column)

    assert facts["distinct"].accuracy == "lower_bound"
    assert overview_text(column).lower().startswith("at least ")


def test_an_enum_gives_its_categories_and_the_share_of_the_most_frequent(tmp_path):
    column = _csv(tmp_path, "status", ["open"] * 360 + ["closed"] * 180 + ["held"] * 60)

    facts = _facts(column)

    assert column.classification.type == "enum"
    assert facts["distinct"].value == 3
    assert facts["top_share"].value == 0.6
    assert "60.0%" in overview_text(column)


def test_a_boolean_does_not_name_its_states(tmp_path):
    column = _csv(tmp_path, "active", ["true"] * 7 + ["false"] * 3)

    text = overview_text(column)

    assert column.classification.type == "boolean"
    assert "true" not in text.lower() and "false" not in text.lower()
    assert _facts(column)["top_share"].value == 0.7


def test_a_constant_column_is_described_without_its_value(tmp_path):
    column = _csv(tmp_path, "country", ["secretland"] * 20)

    text = overview_text(column)

    assert column.classification.type == "constant"
    assert "secretland" not in text
    assert _facts(column)["present"].value == 20


def test_a_numeric_column_gives_its_range_and_median_without_a_mean(tmp_path):
    column = _csv(tmp_path, "weight", [120, 500, 1450, 3000, 8900])

    facts = _facts(column)

    assert facts["minimum"].value == 120 and facts["maximum"].value == 8900
    assert facts["median"].value == 1450
    assert "mean" not in overview_text(column).lower()
    assert "average" not in overview_text(column).lower()


def test_bare_numbers_are_never_given_a_currency(tmp_path):
    column = _csv(tmp_path, "amount", [10.5, 20.25, 30.75, 41.5])

    assert column.classification.type == "number"
    text = overview_text(column).lower()
    assert "currency" not in text and "$" not in text


def test_an_identifier_made_of_numbers_has_no_range(tmp_path):
    column = _csv(tmp_path, "client_id", list(range(1000, 1100)))

    assert column.classification.family == "identifier"
    assert "ranging" not in overview_text(column)


def test_dates_give_their_range_per_kind(tmp_path):
    cells = ["2015-01-02", "2020-06-30", "2026-03-04"] * 5
    column = _csv(tmp_path, "signed", cells)

    facts = _facts(column)

    assert facts["date_minimum"].value == "2015-01-02"
    assert facts["date_maximum"].value == "2026-03-04"
    assert "ambiguous" not in overview_text(column)


def test_ambiguous_dates_are_left_out_without_repeating_their_number(tmp_path):
    cells = ["2015-01-31", "2020-06-30"] * 5 + ["05-05-2020", "03/04/2025"]
    column = _csv(tmp_path, "signed", cells)

    text = overview_text(column)

    assert "ambiguous dates left out" in text
    assert "2" not in text.split("left out")[1]


def test_an_email_column_is_email_shaped_and_shows_no_address(tmp_path):
    column = _csv(tmp_path, "email", [f"user{n}@example.com" for n in range(30)])

    text = overview_text(column)

    assert column.classification.type == "email"
    assert text.startswith("Email-shaped values")
    assert "example.com" not in text


def test_a_text_column_gives_its_median_length_and_diversity(tmp_path):
    column = _csv(tmp_path, "comment", [f"note number {n}" for n in range(30)])

    facts = _facts(column)

    assert column.classification.family == "text"
    assert facts["median_length"].value == 14
    assert "median length of 14" in overview_text(column)


def test_several_patterns_name_no_subsidiary(tmp_path):
    values = ["CLI-0001", "CLI-0002", "X9", "X10", "A-1-B", "A-2-B"] * 10
    column = _csv(tmp_path, "code", values)

    text = overview_text(column).lower()

    assert "subsidiar" not in text and "branch" not in text and "country" not in text


def test_a_mixed_column_lists_the_representations_it_combines(tmp_path):
    column = _csv(tmp_path, "value", ["12", "abc", "13", "def", "14", "ghi"] * 3)

    assert column.classification.type == "mixed"
    assert overview_text(column) == (
        "Present values combine numeric and text representations."
    )


def test_an_empty_column_says_there_is_no_present_value(tmp_path):
    column = _csv(tmp_path, "note", [""] * 10)

    assert column.classification.type == "empty"
    assert overview_text(column) == "No present values in the analyzed scope."


def test_an_overview_never_repeats_a_missing_error_or_issue_figure(tmp_path):
    cells = ["a@b.com"] * 20 + ["bad address"] * 3 + [""] * 7
    column = _csv(tmp_path, "email", cells)

    text = overview_text(column).lower()

    assert not any(word in text for word in ("missing", "invalid", "error", "issue"))


def test_the_sentence_is_deterministic(tmp_path):
    column = _csv(tmp_path, "status", ["open"] * 360 + ["closed"] * 180 + ["held"] * 60)

    assert overview_for(column) == overview_for(column)


def test_a_share_just_below_everything_is_not_rounded_to_one_hundred_percent(tmp_path):
    cells = ["open"] * 2999 + ["closed"]
    column = _csv(tmp_path, "status", cells)

    assert column.classification.type == "enum"
    assert "100.0%" not in overview_text(column)
    assert "more than 99.9%" in overview_text(column)


def test_the_dominant_unit_of_a_quantity_column_is_given_with_its_accuracy(tmp_path):
    column = _csv(tmp_path, "weight", [f"{n} kg" for n in range(1, 40)])

    facts = _facts(column)

    assert column.classification.type == "quantity"
    assert facts["dominant"].value == "kg" and facts["dominant"].accuracy == "exact"


def test_a_marker_of_another_detector_is_not_the_dominant_one(tmp_path):
    column = _csv(tmp_path, "price", [f"${n}.50" for n in range(1, 40)])
    other = column.field.model_copy(
        update={
            "detectors": [
                item.model_copy(update={"id": "quantity"})
                if item.id == "currency"
                else item
                for item in column.field.detectors
            ]
        }
    )

    assert column.classification.type == "currency"
    assert "dominant" in _facts(column)
    assert "dominant" not in _facts(column.model_copy(update={"field": other}))


def test_a_hidden_or_masked_column_does_not_print_its_unit(tmp_path):
    column = _csv(tmp_path, "price", [f"${n}.50" for n in range(1, 40)])

    for mode in ("mask", "hide"):
        hidden = column.model_copy(update={"exposure": mode})
        assert "dominant" not in _facts(hidden)
        assert "$" not in overview_text(hidden)


def test_one_distinct_value_is_singular(tmp_path):
    column = _csv(tmp_path, "ident", ["A1"])

    assert "1 distinct value." in overview_text(column)


def test_a_lower_bound_of_one_keeps_the_singular_noun():
    from tabalyst.report_overview import _counted
    from tabalyst.summary_models import OverviewFact

    fact = OverviewFact(name="formats", value=1, accuracy="lower_bound")

    assert _counted(fact, "format", "formats") == "at least 1 format"


def test_a_mixed_column_names_only_the_representations_it_holds(tmp_path):
    column = _csv(tmp_path, "v", ["12", "abc", "true", "2020-01-01"] * 5)
    counts = {**column.type_counts, "empty": 3, "complex": 2}

    text = overview_text(column.model_copy(update={"type_counts": counts}))

    assert "empty" not in text and "complex" not in text
    assert "boolean, date, numeric and text" in text


def test_two_temporal_kinds_get_one_range_each(tmp_path):
    from tabalyst.scanner.models import Complete, TemporalKind, TemporalStats

    column = _csv(tmp_path, "signed", ["2015-01-02", "2026-03-04"] * 5)
    kinds = [
        TemporalKind(kind="date", count=5, min="2015-01-02", max="2026-03-04", years=None),
        TemporalKind(
            kind="datetime_aware",
            count=5,
            min="2020-05-06T10:00:00+00:00",
            max="2021-05-06T10:00:00+00:00",
            years=None,
        ),
    ]
    field = column.field.model_copy(
        update={"temporal": Complete(value=TemporalStats(count=10, ambiguous=0, kinds=kinds))}
    )

    text = overview_text(column.model_copy(update={"field": field}))

    assert "Dates range from 2015-01-02 to 2026-03-04" in text
    assert "Date-times with a time zone range from 2020-05-06 to 2021-05-06" in text


def test_competing_types_say_that_none_is_established(tmp_path):
    column = _csv(tmp_path, "stamp", ["2020-01-01"] * 10 + ["2020-01-01T10:00:00Z", "2021-02-03T11:00:00"] * 5)

    assert column.classification.type == "unknown"
    assert overview_text(column) == "Values fit more than one type; none is established."
