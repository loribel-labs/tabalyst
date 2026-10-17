# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The name engine (Report overview lot R2): the comparison form, the operators,
the dictionary of rules, and what the name does to a classification: reinforce a
type the values support, break a tie between supported types, weaken one, and
never create one."""

import json

import pytest
from scan_helpers import field, run_scan, write_json, write_text

from tabalyst.scanner import scan
from tabalyst.scanner.classify import (
    classification_versions,
    names,
    version_record,
)
from tabalyst.scanner.classify.catalog import CATALOGUE_VERSION, is_catalogued
from tabalyst.scanner.classify.names import (
    NAME_RULES,
    NAME_RULES_VERSION,
    break_tie,
    contains_sequence,
    contains_token,
    ends_with,
    exact_any,
    name_hints,
    name_parts,
    name_tokens,
    negative_match,
    segment_tokens,
    starts_with,
    tokens_all,
)


def _classification(tmp_path, header, values, **settings):
    source = write_text(
        tmp_path, "data.csv", "\n".join([header, *map(str, values)]) + "\n"
    )
    return field(run_scan(source, **settings)["datasets"][0], header)["classification"]


def _pair(classification):
    return classification["family"], classification["type"]


def _supported(name):
    return {
        (hint.family, hint.type)
        for hint in name_hints(name)
        if hint.polarity == "supports"
    }


def _weakened(name):
    return {
        (hint.family, hint.type)
        for hint in name_hints(name)
        if hint.polarity == "weakens"
    }


def _name_evidence(classification, role=None):
    return [
        item
        for item in classification["evidence"]
        if item["source"] == "name_rule" and (role is None or item["role"] == role)
    ]


# --- Comparison form ------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "tokens"),
    [
        ("CustomerID", ("customer", "id")),
        ("customer_id", ("customer", "id")),
        ("CUSTOMER-ID", ("customer", "id")),
        ("ZIPCode", ("zip", "code")),
        ("idClient", ("id", "client")),
        ("Date-Naissance", ("date", "naissance")),
        ("date naissance", ("date", "naissance")),
        ("Numéro civique", ("numero", "civique")),
        ("ÉCOLE_primaire", ("ecole", "primaire")),
        ("address2Line", ("address2", "line")),
        ("billing.address", ("billing", "address")),
        ("a  /  b", ("a", "b")),
        ("e-mail", ("e", "mail")),
        ("", ()),
    ],
)
def test_the_comparison_form_of_a_name(name, tokens):
    assert segment_tokens(name) == tokens


def test_a_decomposed_accent_gives_the_same_tokens_as_the_composed_one():
    assert segment_tokens("Numéro") == segment_tokens("Numéro") == ("numero",)


def test_the_original_name_is_kept_untouched():
    parts = name_parts("CustomerID")

    assert parts.original == "CustomerID"
    assert parts.segments == ("CustomerID",)


def test_the_parents_of_a_json_path_are_context_not_the_name():
    parts = name_parts(["billing", "Address", "city"])

    assert parts.tokens == ("city",)
    assert parts.context == (("billing",), ("address",))


def test_a_literal_key_with_a_dot_is_one_segment_and_a_nested_path_is_not():
    literal = name_tokens(["postal.code"])
    nested = name_tokens(["postal", "code"])

    assert literal == ("postal", "code")
    assert nested == ("code",)
    assert _supported(["postal.code"]) == {("geographic", "postal_code")}
    assert not _supported(["postal", "code"])


# --- Operators ------------------------------------------------------------------


def test_exact_any_compares_the_whole_name_and_never_a_substring():
    assert exact_any(("email",), [("email",), ("courriel",)])
    assert not exact_any(("email", "status"), [("email",)])
    assert not exact_any(("emails",), [("email",)])


def test_starts_with_and_ends_with_need_a_token_boundary_and_more_name():
    assert starts_with(("id", "client"), ("id",))
    assert not starts_with(("identity",), ("id",))
    assert not starts_with(("id",), ("id",))
    assert ends_with(("customer", "id"), ("id",))
    assert not ends_with(("valid",), ("id",))
    assert not ends_with(("id",), ("id",))


def test_contains_token_is_a_whole_token():
    assert contains_token(("customer", "email", "address"), "email")
    assert not contains_token(("validity",), "id")


def test_contains_sequence_is_contiguous_and_ordered():
    assert contains_sequence(("billing", "postal", "code"), ("postal", "code"))
    assert not contains_sequence(("postal", "address", "code"), ("postal", "code"))
    assert not contains_sequence(("code", "postal"), ("postal", "code"))


def test_tokens_all_ignores_the_order_and_accepts_synonyms():
    groups = [frozenset({"client", "customer"}), frozenset({"id"})]

    assert tokens_all(("id", "client"), groups)
    assert tokens_all(("customer", "number", "id"), groups)
    assert not tokens_all(("customer", "name"), groups)


def test_negative_match_needs_a_derived_measure_after_another_token():
    assert negative_match(("email", "status"))
    assert negative_match(("customer", "id", "length"))
    assert not negative_match(("status",))
    assert not negative_match(("phone", "number"))


# --- The dictionary -------------------------------------------------------------

DICTIONARY = [
    # identifier (evaluated, used by lot R3)
    ("id", ("identifier", "id")),
    ("Identifiant", ("identifier", "id")),
    ("customer_id", ("identifier", "id")),
    ("id_client", ("identifier", "id")),
    ("order_key", ("identifier", "id")),
    ("commande_ref", ("identifier", "id")),
    ("CustomerID", ("identifier", "id")),
    # web and network
    ("uuid", ("web_network", "uuid")),
    ("session_guid", ("web_network", "uuid")),
    ("url", ("web_network", "url")),
    ("site_web", ("web_network", "url")),
    ("image_url", ("web_network", "url")),
    # contact
    ("email", ("contact", "email")),
    ("E-mail", ("contact", "email")),
    ("courriel", ("contact", "email")),
    ("customer_email_address", ("contact", "email")),
    ("work_email", ("contact", "email")),
    ("telephone", ("contact", "phone")),
    ("phone", ("contact", "phone")),
    ("mobile_phone", ("contact", "phone")),
    ("fax_tel", ("contact", "phone")),
    ("phone_number", ("contact", "phone")),
    # geographic
    ("postal_code", ("geographic", "postal_code")),
    ("code_postal", ("geographic", "postal_code")),
    ("ZIPCode", ("geographic", "postal_code")),
    ("billing_postal_code", ("geographic", "postal_code")),
    ("zip", ("geographic", "postal_code")),
    # categorical
    ("is_active", ("categorical", "boolean")),
    ("has_children", ("categorical", "boolean")),
    ("est_actif", ("categorical", "boolean")),
    ("is_valid", ("categorical", "boolean")),
    ("delete_flag", ("categorical", "boolean")),
    ("sexe", ("categorical", "enum")),
    ("Gender", ("categorical", "enum")),
    # temporal
    ("date", ("temporal", "date")),
    ("birth_date", ("temporal", "date")),
    ("date_naissance", ("temporal", "date")),
    ("dob", ("temporal", "date")),
    ("signed_date", ("temporal", "date")),
    ("date_signature", ("temporal", "date")),
    ("created_at", ("temporal", "datetime")),
    ("timestamp", ("temporal", "datetime")),
    ("synced_at", ("temporal", "datetime")),
    ("heure", ("temporal", "time")),
    ("start_time", ("temporal", "time")),
    # numeric
    ("price", ("numeric", "currency")),
    ("prix_unitaire", ("numeric", "currency")),
    ("total_amount", ("numeric", "currency")),
    ("montant", ("numeric", "currency")),
    ("quantity", ("numeric", "quantity")),
    ("stock_qty", ("numeric", "quantity")),
    ("quantite_commandee", ("numeric", "quantity")),
    ("discount_pct", ("numeric", "percentage")),
    ("remise_pourcentage", ("numeric", "percentage")),
    # text
    ("description", ("text", None)),
    ("Commentaire", ("text", None)),
    ("notes", ("text", None)),
]


@pytest.mark.parametrize(("name", "candidate"), DICTIONARY)
def test_the_dictionary_rules_support_their_candidate(name, candidate):
    assert candidate in _supported(name)


@pytest.mark.parametrize(
    "name",
    [
        "validity",
        "identity",
        "paid",
        "email_status",
        "customer_email_status",
        "customer_id_length",
        "postal_code_status",
        "phone_type",
        "date_format",
        "street_name",
        "column_1",
        "value",
        "",
    ],
)
def test_the_adverse_names_of_the_specification_support_nothing(name):
    assert not _supported(name)


def test_a_derived_measure_weakens_what_the_rest_of_the_name_suggests():
    cases = {
        "email_status": ("contact", "email"),
        "customer_email_status": ("contact", "email"),
        "postal_code_status": ("geographic", "postal_code"),
        "customer_id_length": ("identifier", "id"),
        "date_format": ("temporal", "date"),
        "phone_type": ("contact", "phone"),
    }
    for name, candidate in cases.items():
        weakened = [
            hint
            for hint in name_hints(name)
            if hint.polarity == "weakens" and hint.candidate == candidate
        ]
        assert [hint.rule for hint in weakened] == ["name.derived_measure"], name
        assert weakened[0].via


def test_a_boolean_prefix_is_not_vetoed_by_the_word_valid():
    assert ("categorical", "boolean") in _supported("is_valid")


def test_birth_year_is_no_generic_date_it_weakens_the_temporal_types():
    assert not _supported("birth_year")
    assert {("temporal", "date"), ("temporal", "datetime"), ("temporal", "time")} <= (
        _weakened("birth_year")
    )


def test_the_sex_rule_supports_enum_and_argues_against_boolean():
    assert _supported("sexe") == {("categorical", "enum")}
    assert ("categorical", "boolean") in _weakened("sexe")


def test_hints_for_one_candidate_are_one_hint_the_most_specific():
    hints = [
        hint
        for hint in name_hints("billing_postal_code")
        if hint.candidate == ("geographic", "postal_code")
    ]
    exact = [
        hint for hint in name_hints("postal_code") if hint.family == "geographic"
    ]

    assert [hint.strength for hint in hints] == ["sequence"]
    assert [hint.strength for hint in exact] == ["exact"]


def test_the_hints_do_not_depend_on_the_order_of_the_registry(monkeypatch):
    names_to_try = ["billing_postal_code", "customer_email_status", "created_at"]
    before = [name_hints(name) for name in names_to_try]

    monkeypatch.setattr(names, "NAME_RULES", tuple(reversed(NAME_RULES)))

    assert [name_hints(name) for name in names_to_try] == before


def test_every_rule_has_a_unique_id_and_a_candidate_of_the_catalogue():
    ids = [rule.id for rule in NAME_RULES]
    assert len(ids) == len(set(ids))
    for rule in NAME_RULES:
        for family, type_ in (*([rule.candidate] if rule.candidate else []), *rule.weakens):
            if type_ is None:
                assert family == "text"
            elif family != "identifier":
                assert is_catalogued(family, type_), rule.id
            else:
                assert (family, type_) == ("identifier", "id"), rule.id


def test_a_hint_carries_no_score():
    hint = name_hints("email")[0]

    assert not hasattr(hint, "score") and not hasattr(hint, "confidence")


# --- Breaking a tie -------------------------------------------------------------

POSTAL = ("geographic", "postal_code")
INTEGER = ("numeric", "integer")
PHONE = ("contact", "phone")


def test_a_supported_type_wins_the_tie():
    verdict = break_tie([INTEGER, POSTAL], name_hints("postal_code"))

    assert verdict.winner == POSTAL
    assert verdict.outranked == (INTEGER,)


def test_a_weakened_type_is_removed_while_another_stays():
    verdict = break_tie([INTEGER, POSTAL], name_hints("postal_code_status"))

    assert verdict.winner == INTEGER
    assert verdict.removed == (POSTAL,)


def test_a_name_that_says_nothing_leaves_the_conflict():
    verdict = break_tie([INTEGER, POSTAL, PHONE], name_hints("value"))

    assert verdict.winner is None
    assert set(verdict.remaining) == {INTEGER, POSTAL, PHONE}


def test_a_name_that_narrows_leaves_a_smaller_conflict():
    verdict = break_tie([INTEGER, POSTAL, PHONE], name_hints("phone_status"))

    assert verdict.winner is None
    assert set(verdict.remaining) == {INTEGER, POSTAL}
    assert verdict.removed == (PHONE,)


def test_the_last_type_is_never_removed():
    verdict = break_tie([POSTAL], name_hints("postal_code_status"))

    assert verdict.removed == ()
    assert verdict.remaining == (POSTAL,)


# --- What the name does to a classification --------------------------------------


def test_a_name_settles_five_digit_integers_as_a_postal_code_candidate(tmp_path):
    classification = _classification(
        tmp_path, "postal_code", ["12345", "90210", "10001", "60601"] * 10
    )

    assert _pair(classification) == POSTAL
    assert classification["state"] == "candidate"
    assert classification["basis"] == "inferred"
    assert [item["id"] for item in _name_evidence(classification, "supports")] == [
        "name.postal"
    ]
    assert {(a["type"], a["reason"]) for a in classification["alternatives"]} == {
        ("integer", "outranked_by_name")
    }
    context = {item["source"] for item in classification["evidence"] if item["role"] == "context"}
    assert context == {"technical_type"}


@pytest.mark.parametrize("name", ["code_postal", "ZIPCode", "billing_postal_code"])
def test_the_french_english_and_camel_case_names_settle_alike(tmp_path, name):
    classification = _classification(tmp_path, name, ["12345", "90210", "10001"] * 10)

    assert _pair(classification) == POSTAL
    assert classification["state"] == "candidate"


def test_the_same_digits_with_a_derived_measure_name_stay_an_integer(tmp_path):
    classification = _classification(
        tmp_path, "postal_code_status", ["12345", "90210", "10001", "60601"] * 10
    )

    assert _pair(classification) == INTEGER
    assert classification["state"] == "candidate"
    assert {(a["type"], a["reason"]) for a in classification["alternatives"]} == {
        ("postal_code", "weakened_by_name")
    }
    assert [item["id"] for item in _name_evidence(classification, "context")] == [
        "name.derived_measure"
    ]


def test_ten_digits_named_telephone_are_a_phone_candidate(tmp_path):
    classification = _classification(
        tmp_path, "telephone", ["5145551234", "6135559876"] * 5
    )

    assert _pair(classification) == PHONE
    assert classification["state"] == "candidate"


def test_a_neutral_name_leaves_the_digits_undetermined(tmp_path):
    classification = _classification(tmp_path, "value", ["12345", "90210"] * 10)

    assert _pair(classification) == INTEGER
    assert classification["state"] == "undetermined"
    assert not _name_evidence(classification)


def test_a_name_breaks_the_tie_between_dates_and_datetimes(tmp_path):
    values = ["2024-01-01 10:00:00", "2024-01-02", "2024-03-01 10:00:00", "2024-04-05"]

    stamped = _classification(tmp_path, "created_at", values * 10)
    dated = _classification(tmp_path, "created_date", values * 10)
    neutral = _classification(tmp_path, "when", values * 10)

    assert _pair(stamped) == ("temporal", "datetime")
    assert _pair(dated) == ("temporal", "date")
    assert stamped["state"] == dated["state"] == "candidate"
    assert _pair(neutral) == ("other", "unknown")
    assert neutral["state"] == "undetermined"


def test_a_name_reinforces_without_changing_the_type_or_the_state(tmp_path):
    values = [f"user{n}@example.com" for n in range(30)]

    named = _classification(tmp_path, "email", values)
    neutral = _classification(tmp_path, "contact", values)

    assert _pair(named) == _pair(neutral) == ("contact", "email")
    assert named["state"] == neutral["state"] == "established"
    assert named["basis"] == neutral["basis"]
    assert [item["id"] for item in _name_evidence(named, "supports")] == ["name.email"]
    assert not _name_evidence(neutral)


def test_a_name_that_argues_against_a_supported_type_adds_a_contradiction(tmp_path):
    values = [f"user{n}@example.com" for n in range(30)]

    classification = _classification(tmp_path, "email_status", values)

    assert _pair(classification) == ("contact", "email")
    assert classification["state"] == "established"
    assert [item["id"] for item in _name_evidence(classification, "contradicts")] == [
        "name.derived_measure"
    ]


def test_a_name_alone_creates_no_type_it_is_a_name_only_alternative(tmp_path):
    for header, expected in [
        ("phone", ("contact", "phone")),
        ("is_active", ("categorical", "boolean")),
        ("created_at", ("temporal", "datetime")),
        ("url", ("web_network", "url")),
    ]:
        classification = _classification(
            tmp_path, header, ["red", "green", "blue", "pink", "gray", "teal"] * 4
        )
        assert _pair(classification) != expected, header
        reasons = {
            (a["family"], a["type"]): a["reason"]
            for a in classification["alternatives"]
        }
        assert reasons[expected] == "name_only", header
        assert not _name_evidence(classification), header


def test_a_name_only_alternative_needs_a_compatible_technical_type(tmp_path):
    classification = _classification(tmp_path, "email", [10, 20, 35, 120, 99])

    assert _pair(classification) == ("numeric", "integer")
    assert all(a["reason"] != "name_only" for a in classification["alternatives"])


def test_a_name_never_makes_a_column_without_values_anything(tmp_path):
    classification = _classification(tmp_path, "email", ['""', '""', '""'])

    assert _pair(classification) == ("other", "empty")
    assert classification["alternatives"] == []
    assert not _name_evidence(classification)


def test_a_sex_name_keeps_enum_and_a_two_state_boolean_is_contradicted(tmp_path):
    enum = _classification(tmp_path, "sexe", ["M", "F"] * 300)
    boolean = _classification(tmp_path, "sexe", ["yes", "no"] * 30)

    assert _pair(enum) == ("categorical", "enum")
    assert [item["id"] for item in _name_evidence(enum, "supports")] == [
        "name.sex_category"
    ]
    assert _pair(boolean) == ("categorical", "boolean")
    assert [item["id"] for item in _name_evidence(boolean, "contradicts")] == [
        "name.sex_category"
    ]


def test_an_amount_name_does_not_make_a_bare_number_a_currency(tmp_path):
    classification = _classification(tmp_path, "price", [10, 20, 35, 120, 99, 42])

    assert _pair(classification) == INTEGER
    assert {(a["type"], a["reason"]) for a in classification["alternatives"]} == {
        ("currency", "name_only")
    }


def test_a_text_name_reinforces_a_text_of_any_length(tmp_path):
    classification = _classification(
        tmp_path, "description", ["a long free text value " * 3 + str(n) for n in range(20)]
    )

    assert classification["family"] == "text"
    assert [item["id"] for item in _name_evidence(classification, "supports")] == [
        "name.text"
    ]


def test_an_identifier_name_is_evidence_of_the_role_it_gives(tmp_path):
    classification = _classification(
        tmp_path, "customer_id", [f"C{n:05d}" for n in range(200)]
    )

    assert classification["family"] == "identifier"
    # Two rules agree on the role: the more specific one is the only evidence.
    assert [item["id"] for item in _name_evidence(classification, "supports")] == [
        "tokens.customer_id"
    ]


def test_json_fields_are_named_by_their_key_not_by_the_flattened_display(tmp_path):
    rows = [
        {"billing": {"postal_code": str(12345 + n % 3), "code": str(12345 + n % 3)}}
        for n in range(30)
    ]
    source = write_json(tmp_path, "data.json", rows)

    dataset = run_scan(source)["datasets"][0]
    postal = field(dataset, "billing.postal_code")["classification"]
    plain = field(dataset, "billing.code")["classification"]

    assert _pair(postal) == POSTAL
    assert _pair(plain) == INTEGER
    assert plain["state"] == "undetermined"


def test_a_json_key_with_a_dot_is_named_as_a_whole(tmp_path):
    rows = [{"postal.code": str(12345 + n % 3)} for n in range(30)]
    source = write_text(tmp_path, "data.json", json.dumps(rows))

    dataset = run_scan(source)["datasets"][0]
    classification = dataset["fields"][0]["classification"]

    assert _pair(classification) == POSTAL


def test_the_name_engine_gives_the_same_result_with_any_worker_count(tmp_path):
    source = write_text(
        tmp_path,
        "data.csv",
        "postal_code,created_at\n"
        + "\n".join(f"{12345 + n % 7},2024-01-0{n % 9 + 1}" for n in range(300))
        + "\n",
    )

    one = [item.classification for item in scan(source, workers=1).datasets[0].fields]
    several = [
        item.classification for item in scan(source, workers=2).datasets[0].fields
    ]

    assert one == several


# --- Versions -------------------------------------------------------------------


def test_the_rule_version_combines_the_catalogue_and_the_name_rules(tmp_path):
    classification = _classification(tmp_path, "note", ["alpha", "beta"])

    assert classification["rule_version"] == CATALOGUE_VERSION * 1000 + NAME_RULES_VERSION
    assert classification_versions() == (CATALOGUE_VERSION, NAME_RULES_VERSION)
    assert version_record() == {
        "catalogue": CATALOGUE_VERSION,
        "names": NAME_RULES_VERSION,
    }


def test_a_scan_records_both_versions_in_the_engine(tmp_path):
    result = scan(write_text(tmp_path, "data.csv", "note\nalpha\n"))

    assert result.engine.classification == version_record()
    assert set(result.engine.classification) == {"catalogue", "names"}
