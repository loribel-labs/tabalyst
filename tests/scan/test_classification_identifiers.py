# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Identifier role (Report overview lot R3): ID and Unique ID, what the role
replaces, the scope it publishes and the traits that are never a proof."""

import pytest
from scan_helpers import field, run_scan, write_json, write_text

from tabalyst.scanner import scan
from tabalyst.scanner.classify.rules import rule_version


def _csv(tmp_path, header, rows):
    """A CSV with the given header and rows, each row a list of cells."""
    lines = [header, *(",".join(map(str, row)) for row in rows)]
    return write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")


def _column(tmp_path, name, cells, label=True, **settings):
    """The classification of ``name``, the first column of a table.

    A second column keeps an empty cell a cell: in a one-column CSV an empty
    value is a blank line.
    """
    header = f"{name},label" if label else name
    rows = [[value, "x"] if label else [value] for value in cells]
    result = run_scan(_csv(tmp_path, header, rows), **settings)
    return field(result["datasets"][0], name)["classification"]


def _pair(classification):
    return classification["family"], classification["type"]


def _alternatives(classification):
    return {
        (item["family"], item["type"]): item["reason"]
        for item in classification["alternatives"]
    }


def _measure_scopes(classification):
    return {
        item["id"]: item["scope"]
        for item in classification["evidence"]
        if item["source"] == "measure"
    }


IDENTIFIERS = [f"C{n:05d}" for n in range(200)]
UNIQUE_ID = ("identifier", "unique_id")
ID = ("identifier", "id")


# --- ID and Unique ID ------------------------------------------------------------


def test_a_unique_id_replaces_the_text_and_keeps_it_as_an_alternative(tmp_path):
    classification = _column(tmp_path, "customer_id", IDENTIFIERS)

    assert _pair(classification) == UNIQUE_ID
    assert classification["state"] == "candidate"
    assert classification["basis"] == "inferred"
    assert _alternatives(classification) == {("text", "text_short"): "replaced_by_role"}


def test_the_evidence_of_an_id_is_the_technical_type_and_the_name(tmp_path):
    values = IDENTIFIERS[:100] * 2

    classification = _column(tmp_path, "customer_id", values)

    assert _pair(classification) == ID
    assert [
        (item["source"], item["id"], item["role"])
        for item in classification["evidence"]
        if item["role"] == "supports"
    ] == [
        ("technical_type", "text", "supports"),
        ("name_rule", "tokens.customer_id", "supports"),
    ]
    # The facts of the replaced Text stay, as context.
    assert any(
        item["id"] == "string_lengths.median_length" and item["role"] == "context"
        for item in classification["evidence"]
    )


def test_a_unique_id_adds_its_cardinality_and_missing_measures_to_the_evidence(
    tmp_path,
):
    classification = _column(tmp_path, "order_id", IDENTIFIERS)

    scopes = _measure_scopes(classification)
    assert scopes["values.cardinality"] == {
        "population": "present_values",
        "of": 200,
        "partial": False,
        "accuracy": "exact",
    }
    assert scopes["missing.count"] == {
        "population": "positions",
        "of": 200,
        "partial": False,
        "accuracy": "exact",
    }
    assert "observed_unique" in classification["traits"]


def test_an_id_does_not_carry_the_unique_measures(tmp_path):
    classification = _column(tmp_path, "order_id", IDENTIFIERS[:50] * 4)

    assert _pair(classification) == ID
    assert "values.cardinality" not in _measure_scopes(classification)
    assert "observed_unique" not in classification["traits"]


@pytest.mark.parametrize(
    "name",
    ["id", "ID", "identifiant", "customer_id", "CustomerID", "id_client", "order_ref",
     "api_key", "numero_commande_id"],
)
def test_the_names_of_an_identifier_give_the_role(tmp_path, name):
    assert _pair(_column(tmp_path, name, IDENTIFIERS)) == UNIQUE_ID


@pytest.mark.parametrize(
    "name",
    ["validity", "identity", "idea", "column_1", "customer", "paid", "ref", "key"],
)
def test_a_name_that_is_not_an_identifier_gives_no_role(tmp_path, name):
    classification = _column(tmp_path, name, IDENTIFIERS)

    assert classification["family"] == "text"
    assert "observed_unique" in classification["traits"]


@pytest.mark.parametrize("name", ["customer_id_length", "id_count", "order_id_status"])
def test_a_derived_measure_of_an_identifier_is_no_identifier(tmp_path, name):
    classification = _column(tmp_path, name, IDENTIFIERS)

    assert classification["family"] == "text"
    assert not any(a["family"] == "identifier" for a in classification["alternatives"])


# --- Unique ID conditions --------------------------------------------------------


def test_a_value_equal_after_trim_is_not_unique(tmp_path):
    values = ["A", " A ", "B", "C"]

    classification = _column(tmp_path, "id", values)

    assert _pair(classification) == ID
    assert "observed_unique" not in classification["traits"]


def test_values_distinct_after_trim_are_unique(tmp_path):
    classification = _column(tmp_path, "id", [" A ", "B ", " C"])

    assert _pair(classification) == UNIQUE_ID


def test_a_blank_cell_is_a_missing_position(tmp_path):
    values = [*IDENTIFIERS[:10], " ", *IDENTIFIERS[10:30]]

    classification = _column(tmp_path, "id", values)

    assert _pair(classification) == ID
    # The present values are all distinct: the missing position alone decides.
    assert "observed_unique" in classification["traits"]


def test_a_missing_marker_is_a_missing_position(tmp_path):
    values = [*IDENTIFIERS[:10], "N/A"]

    default = _column(tmp_path, "id", values)
    marked = _column(tmp_path, "id", values, values={"null_markers": ["N/A"]})

    # Without the marker "N/A" is one more identifier.
    assert _pair(default) == UNIQUE_ID
    assert _pair(marked) == ID


def test_a_single_present_value_is_not_an_identifier(tmp_path):
    classification = _column(tmp_path, "id", ["C00001"])

    assert classification["family"] != "identifier"
    assert "observed_unique" not in classification["traits"]
    assert _alternatives(classification)[ID] == "name_only"


def test_a_limited_cardinality_is_never_unique(tmp_path):
    classification = _column(
        tmp_path, "id", IDENTIFIERS, limits={"max_distinct_per_field": 50}
    )

    assert _pair(classification) == ID
    assert "observed_unique" not in classification["traits"]


def test_the_records_the_scan_excluded_make_the_scope_partial(tmp_path):
    rows = [[value, "x"] for value in IDENTIFIERS[:20]] + [["broken"]]
    source = _csv(tmp_path, "id,label", rows)

    result = run_scan(source, errors={"policy": "tolerant"})
    classification = field(result["datasets"][0], "id")["classification"]

    assert result["scope"]["records_excluded"] == 1
    assert _pair(classification) == UNIQUE_ID
    scopes = _measure_scopes(classification)
    assert scopes["values.cardinality"]["partial"] is True
    assert scopes["missing.count"]["partial"] is True
    assert scopes["values.cardinality"]["of"] == 20


def test_a_complete_scan_publishes_a_scope_that_is_not_partial(tmp_path):
    classification = _column(tmp_path, "id", IDENTIFIERS)

    assert all(not item["partial"] for item in _measure_scopes(classification).values())


# --- JSON ------------------------------------------------------------------------


def test_the_id_of_a_json_collection_is_a_unique_id(tmp_path):
    rows = [{"id": f"u{n}", "name": f"user {n}"} for n in range(30)]
    result = run_scan(write_json(tmp_path, "data.json", rows))

    classification = field(result["datasets"][0], "id")["classification"]

    assert _pair(classification) == UNIQUE_ID
    assert "first_column" not in classification["traits"]


def test_a_nested_object_key_can_be_a_unique_id(tmp_path):
    rows = [{"customer": {"id": f"u{n}"}} for n in range(30)]
    result = run_scan(write_json(tmp_path, "data.json", rows))

    classification = field(result["datasets"][0], "customer.id")["classification"]

    assert _pair(classification) == UNIQUE_ID


def test_a_field_under_a_json_array_is_an_id_never_a_unique_id(tmp_path):
    rows = [{"orders": [{"id": f"a{n}"}, {"id": f"b{n}"}]} for n in range(30)]
    result = run_scan(write_json(tmp_path, "data.json", rows))

    classifications = {
        item["display"]: item["classification"]
        for item in result["datasets"][0]["fields"]
        if item["name"] == "id"
    }

    assert [_pair(item) for item in classifications.values()] == [ID]
    assert "observed_unique" in next(iter(classifications.values()))["traits"]


def test_a_key_missing_from_a_record_is_a_missing_position_even_if_not_counted(
    tmp_path,
):
    rows = [{"id": f"u{n}"} for n in range(30)] + [{"other": 1}]
    source = write_json(tmp_path, "data.json", rows)

    default = run_scan(source)
    absent_not_counted = run_scan(
        source, values={"missing": ["null", "empty", "blank", "marker"]}
    )

    for result in (default, absent_not_counted):
        classification = field(result["datasets"][0], "id")["classification"]
        assert _pair(classification) == ID


# --- What the role replaces ------------------------------------------------------


def test_a_uuid_keeps_its_type_and_lists_the_role_as_an_alternative(tmp_path):
    values = [f"{n:08x}-1111-4222-8333-444444444444" for n in range(50)]

    classification = _column(tmp_path, "customer_id", values)

    assert _pair(classification) == ("web_network", "uuid")
    assert _alternatives(classification)[ID] == "uuid_name"
    assert "observed_unique" in classification["traits"]


def test_whole_numbers_with_an_identifier_name_become_ids(tmp_path):
    unique = _column(tmp_path, "order_id", range(1, 101))
    repeated = _column(tmp_path, "order_id", list(range(1, 51)) * 2)

    assert _pair(unique) == UNIQUE_ID
    assert _pair(repeated) == ID
    assert _alternatives(unique)[("numeric", "integer")] == "replaced_by_role"


def test_five_digit_integers_read_as_postal_codes_are_settled_by_an_identifier_name(
    tmp_path,
):
    values = [10000 + n * 37 for n in range(60)]

    classification = _column(tmp_path, "client_id", values)

    assert _pair(classification) == UNIQUE_ID
    assert _alternatives(classification)[("geographic", "postal_code")] == (
        "conflicting_candidates"
    )
    assert _alternatives(classification)[("numeric", "integer")] == (
        "conflicting_candidates"
    )


def test_integers_without_an_identifier_name_stay_integers(tmp_path):
    classification = _column(tmp_path, "quantity_sold", range(1, 101))

    assert _pair(classification) == ("numeric", "integer")
    assert "observed_unique" in classification["traits"]


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("email_id", [f"u{n}@example.com" for n in range(40)], ("contact", "email")),
        (
            "date_id",
            [f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}" for n in range(40)],
            ("temporal", "date"),
        ),
        ("price_id", [f"{10 + n}.{n % 100:02d}" for n in range(40)], ("numeric", "number")),
        ("flag_id", ["yes", "no"] * 20, ("categorical", "boolean")),
        ("status_id", ["new", "open", "closed"] * 200, ("categorical", "enum")),
    ],
)
def test_a_more_specific_type_is_never_replaced_by_the_role(
    tmp_path, name, values, expected
):
    classification = _column(tmp_path, name, values)

    assert _pair(classification) == expected


def test_a_name_that_the_values_do_not_allow_is_a_name_only_alternative(tmp_path):
    classification = _column(
        tmp_path, "email_id", [f"u{n}@example.com" for n in range(40)]
    )

    assert _alternatives(classification)[ID] == "name_only"


def test_a_date_named_like_an_identifier_does_not_list_the_role(tmp_path):
    classification = _column(
        tmp_path,
        "date_id",
        [f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}" for n in range(40)],
    )

    assert ID not in _alternatives(classification)


def test_a_constant_column_with_an_identifier_name_stays_constant(tmp_path):
    text = _column(tmp_path, "id", ["same"] * 10)
    number = _column(tmp_path, "id", [7] * 10)

    assert _pair(text) == ("categorical", "constant")
    assert _pair(number) == ("numeric", "integer")
    assert "constant" in number["traits"]


def test_a_text_with_a_value_outside_its_family_is_not_compatible(tmp_path):
    # Whole numbers among text codes: the technical type stays text, one value
    # outside its family, so the values are not compatible with the role.
    values = [*IDENTIFIERS[:100], "12345"]

    classification = _column(tmp_path, "id", values)

    assert classification["family"] == "text"
    assert _alternatives(classification)[ID] == "name_only"


# --- Traits ----------------------------------------------------------------------


def test_the_first_column_of_a_table_has_the_trait_and_no_role(tmp_path):
    first = _column(tmp_path, "reference", IDENTIFIERS)

    assert first["family"] == "text"
    assert {"first_column", "observed_unique"} <= set(first["traits"])


def test_only_the_first_column_has_first_column(tmp_path):
    source = _csv(tmp_path, "a,b", [[value, value] for value in IDENTIFIERS])

    fields = run_scan(source)["datasets"][0]["fields"]

    assert {
        item["display"]: "first_column" in item["classification"]["traits"]
        for item in fields
    } == {"a": True, "b": False}


def test_a_json_field_is_never_the_first_column(tmp_path):
    rows = [{"ref": f"r{n}"} for n in range(20)]
    result = run_scan(write_json(tmp_path, "data.json", rows))

    classification = field(result["datasets"][0], "ref")["classification"]

    assert "first_column" not in classification["traits"]
    assert "observed_unique" in classification["traits"]


def test_the_traits_never_give_a_role_to_a_column_without_an_identifier_name(tmp_path):
    for name in ("column_1", "timestamp", "price", "code", "x"):
        classification = _column(tmp_path, name, [f"{n}.5" for n in range(40)])
        assert classification["family"] != "identifier"


def test_high_cardinality_is_not_emitted(tmp_path):
    # No threshold comes from the tracked limits: the contract leaves it out.
    classification = _column(tmp_path, "id", IDENTIFIERS)

    assert "high_cardinality" not in classification["traits"]


# --- Versions and determinism ----------------------------------------------------


def test_the_rule_version_includes_the_identifier_rules(tmp_path):
    classification = _column(tmp_path, "id", IDENTIFIERS)

    assert classification["rule_version"] == rule_version()


def test_the_identifier_roles_are_the_same_with_any_worker_count(tmp_path):
    source = _csv(
        tmp_path,
        "customer_id,order_id,label",
        [[f"C{n:05d}", n % 40, f"L{n % 5}"] for n in range(2000)],
    )

    one = [item.classification for item in scan(source, workers=1).datasets[0].fields]
    several = [
        item.classification for item in scan(source, workers=2).datasets[0].fields
    ]

    assert one == several
    assert [item.type for item in one] == ["unique_id", "id", "enum"]
