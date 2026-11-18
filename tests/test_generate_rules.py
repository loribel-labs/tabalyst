# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The grammar and evaluator of Generate rules, and the refusals of their catalogue."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from pydantic import TypeAdapter

from tabalyst.errors import ConfigurationError
from tabalyst.generate_rules import (
    OPERATORS,
    Conventions,
    Expression,
    Rule,
    RuleContext,
    RuleEvaluator,
    holds,
    parse_catalogue,
)
from tabalyst.generate_service import validate_generate_package

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))
CONTEXT = RuleContext(Conventions(branch_column="filiale", date_format={
    "principal": "%Y-%m-%d", "ontario": "%m-%d-%Y", "quebec": "%d-%m-%Y"}), "2026-09-16")
EXPRESSION: TypeAdapter[Expression] = TypeAdapter(Expression)


def _holds(expression: Mapping[str, object], **row: str) -> bool | None:
    return holds(EXPRESSION.validate_python(expression), row, CONTEXT)


def _rule(assertion: dict[str, object], columns: list[str], **extra: object) -> Rule:
    return Rule.model_validate({
        "id": "M99", "family": "business", "title": "Test", "columns": columns,
        "category": "business_rule_violation", "severity": "major",
        "detection": "cross_column", "assert": assertion, **extra})


@pytest.mark.parametrize(("op", "expected"), [
    ("eq", False), ("gt", True), ("gte", True), ("lt", False), ("lte", False)])
def test_comparisons_read_dates_with_the_convention_of_the_row_branch(
        op: str, expected: bool) -> None:
    # 05-10-2026 is 5 October in Quebec; 10-04-2026 is 4 October in Ontario.
    # Two cells of a row share its convention; a constant is ISO 8601.
    assert _holds({"op": op, "left": "a", "right": "b", "as": "date"},
                  a="05-10-2026", b="04-10-2026", filiale="quebec") is expected
    assert _holds({"op": op, "left": "a", "right": {"value": "2026-10-04"}, "as": "date"},
                  a="05-10-2026", filiale="quebec") is expected
    assert _holds({"op": op, "left": "a", "right": {"value": "2026-10-04"}, "as": "date"},
                  a="10-05-2026", filiale="ontario") is expected


def test_a_date_written_in_another_convention_is_unknown_not_false() -> None:
    expression = {"op": "gte", "left": "a", "right": {"param": "as_of_date"}, "as": "date"}
    assert _holds(expression, a="2026-10-05", filiale="quebec") is None
    assert _holds(expression, a="5-10-2026", filiale="quebec") is None  # not written exactly
    assert _holds(expression, a="05-10-2026", filiale="atlantis") is None
    assert _holds(expression, a="05-10-2026", filiale="quebec") is True


def test_decimal_and_text_comparisons() -> None:
    assert _holds({"op": "gt", "left": "p", "right": {"value": "0"}, "as": "decimal"},
                  p="12.50") is True
    assert _holds({"op": "gt", "left": "p", "right": {"value": "0"}, "as": "decimal"},
                  p="-1.00") is False
    assert _holds({"op": "gt", "left": "p", "right": {"value": "0"}, "as": "decimal"},
                  p="12,50 $") is None
    assert _holds({"op": "eq", "left": "a", "right": "b"}, a="x", b="x") is True
    assert _holds({"op": "between", "column": "p", "low": {"value": "1"},
                   "high": {"value": "9"}, "as": "decimal"}, p="9") is True
    assert _holds({"op": "between", "column": "p", "low": {"value": "1"},
                   "high": {"value": "9"}, "as": "decimal"}, p="9.01") is False


def test_value_tests_on_an_empty_cell_are_unknown_and_presence_is_always_known() -> None:
    for expression in ({"op": "in", "column": "s", "values": ["a"]},
                       {"op": "not_in", "column": "s", "values": ["a"]},
                       {"op": "regex", "column": "s", "pattern": "[a-z]+"},
                       {"op": "lt", "left": "s", "right": {"value": "b"}}):
        assert _holds(expression, s="") is None
    assert _holds({"op": "in", "column": "s", "values": ["a"]}, s="a") is True
    assert _holds({"op": "not_in", "column": "s", "values": ["a"]}, s="a") is False
    assert _holds({"op": "regex", "column": "s", "pattern": "[a-z]+"}, s="ab1") is False
    assert _holds({"op": "empty", "column": "s"}, s="") is True
    assert _holds({"op": "not_empty", "column": "s"}, s="") is False


@pytest.mark.parametrize(("op", "values", "expected"), [
    ("and", ["t", "u"], None), ("and", ["f", "u"], False), ("and", ["t", "t"], True),
    ("or", ["t", "u"], True), ("or", ["f", "u"], None), ("or", ["f", "f"], False)])
def test_junctions_follow_three_valued_logic(op: str, values: list[str],
                                             expected: bool | None) -> None:
    leaf = {"t": {"op": "not_empty", "column": "x"}, "f": {"op": "empty", "column": "x"},
            "u": {"op": "in", "column": "y", "values": ["a"]}}
    assert _holds({"op": op, "args": [leaf[v] for v in values]}, x="1", y="") is expected


def test_implies_and_not() -> None:
    present = {"op": "not_empty", "column": "x"}
    unknown = {"op": "in", "column": "y", "values": ["a"]}
    assert _holds({"op": "implies", "if": present, "then": unknown}, x="", y="") is True
    assert _holds({"op": "implies", "if": present, "then": unknown}, x="1", y="") is None
    assert _holds({"op": "implies", "if": present, "then": unknown}, x="1", y="b") is False
    assert _holds({"op": "implies", "if": unknown, "then": present}, x="1", y="") is True
    assert _holds({"op": "not", "arg": unknown}, y="") is None
    assert _holds({"op": "not", "arg": present}, x="") is True


def test_every_operator_of_the_contract_is_in_the_grammar() -> None:
    assert OPERATORS == {"eq", "gt", "gte", "lt", "lte", "between", "in", "not_in", "regex",
                         "not_empty", "empty", "unique", "implies", "and", "or", "not"}


def test_a_rule_breaks_only_where_it_applies_and_no_exception_holds() -> None:
    rule = _rule({"op": "gte", "left": "fin", "right": "debut", "as": "date"},
                 ["debut", "fin", "motif"],
                 when={"op": "not_empty", "column": "fin"},
                 exceptions=[{"op": "in", "column": "motif", "values": ["retro"]}])
    evaluator = RuleEvaluator([rule], CONTEXT)
    rows = [{"debut": "2026-01-02", "fin": "2026-01-01", "motif": "", "filiale": "principal"},
            {"debut": "2026-01-02", "fin": "", "motif": "", "filiale": "principal"},
            {"debut": "2026-01-02", "fin": "2026-01-01", "motif": "retro", "filiale": "principal"},
            {"debut": "2026-01-02", "fin": "01-01-2026", "motif": "", "filiale": "principal"}]
    found = [v for n, row in enumerate(rows, 2) for v in evaluator.check(n, row)]
    assert [(v.rule_id, v.row_number) for v in found] == [("M99", 2)]


def test_unique_reports_both_rows_of_a_repeated_key_in_one_group() -> None:
    evaluator = RuleEvaluator([_rule({"op": "unique", "columns": ["id"]}, ["id"],
                                     detection="uniqueness")], CONTEXT)
    found = []
    for number, key in enumerate(["A", "B", "A", "", "", "A"], 2):
        found.extend(evaluator.check(number, {"id": key}))
    assert [(v.row_number, v.group_id, v.cause_row) for v in found] == [
        (2, "M99-2", 4), (4, "M99-2", 4), (7, "M99-2", 7)]


@pytest.mark.parametrize(("change", "message"), [
    ({"columns": ["a"]}, r"columns must list, once each, the columns the rule reads"),
    ({"detection": "none"}, r"detection must join distinct families"),
    ({"assert": {"op": "and", "args": [{"op": "unique", "columns": ["a"]},
                                       {"op": "empty", "column": "b"}]}},
     r"unique stands alone"),
    ({"assert": {"op": "regex", "column": "a", "pattern": "("}}, r"does not compile"),
    ({"assert": {"op": "like", "column": "a"}}, r"assert"),
    ({"category": "valid_atypical"}, r"category"),
])
def test_invalid_rules_are_refused(change: dict[str, object], message: str) -> None:
    rule = {"id": "M99", "family": "business", "title": "Test", "columns": ["a", "b"],
            "category": "business_rule_violation", "severity": "major",
            "detection": "cross_column",
            "assert": {"op": "gte", "left": "a", "right": "b", "as": "date"}, **change}
    with pytest.raises(ValueError, match=message):
        parse_catalogue({"conventions": {"branch_column": "filiale",
                                         "date_format": {"principal": "%Y-%m-%d"}},
                         "rules": [rule]})


def test_catalogue_refuses_two_rules_with_one_id() -> None:
    rule = {"id": "M99", "family": "business", "title": "T", "columns": ["a"],
            "category": "semantic_invalid", "severity": "major", "detection": "domain",
            "assert": {"op": "not_empty", "column": "a"}}
    with pytest.raises(ValueError, match="rule ids must be distinct"):
        parse_catalogue({"conventions": {"branch_column": "f", "date_format": {"x": "%Y"}},
                         "rules": [rule, rule]})


def _package(tmp_path: Path, operations: list[dict[str, object]] | None = None,
             targets: list[str] | None = None, rules: str | None = None,
             manifest: dict[str, object] | None = None, source: Path = PACKAGE) -> Path:
    package = tmp_path / "package"
    shutil.copytree(source, package)
    path = package / "dataset.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if operations is not None:
        document["anomaly_profiles"]["v2"] = {
            "targets": targets or ["insurance-combined"], "operations": operations}
    document.update(manifest or {})
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    if rules is not None:
        (package / "rules.yaml").write_text(rules, encoding="utf-8")
    return package


def _operation(**extra: object) -> dict[str, object]:
    return {"kind": "set_missing", "column": "courriel", "count": 2, "scenario_id": "S1",
            "category": "semantic_invalid", "severity": "major", **extra}


def test_shipped_package_has_a_valid_rules_catalogue() -> None:
    assert validate_generate_package(PACKAGE).package_id == "insurance"


def test_rule_id_must_name_a_rule_of_the_package(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match=r"profile v2: operations\[1\]: rule_id M99 "
                                                 r"is not a rule of the package \(known: M01"):
        validate_generate_package(_package(tmp_path, [_operation(rule_id="M99")]))
    assert validate_generate_package(_package(tmp_path / "ok", [_operation(rule_id="M01")]))


def test_scenario_profile_needs_a_target_with_the_branch_column(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match=r"target insurance-quebec has no filiale "
                                                 r"column"):
        validate_generate_package(_package(tmp_path, [_operation()], ["insurance-quebec"]))


def test_scenario_profile_needs_the_rules_catalogue(tmp_path: Path) -> None:
    package = _package(tmp_path, [_operation()])
    path = package / "dataset.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("rules: rules.yaml\n", ""),
                    encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"a scenario profile needs the rules catalogue"):
        validate_generate_package(package)


def test_catalogue_date_formats_must_be_those_of_the_branches(tmp_path: Path) -> None:
    rules = (PACKAGE / "rules.yaml").read_text(encoding="utf-8").replace(
        'ontario: "%m-%d-%Y"', 'ontario: "%d-%m-%Y"')
    with pytest.raises(ConfigurationError, match=r"PACKAGE_RULES: rules.yaml: conventions"):
        validate_generate_package(_package(tmp_path, rules=rules))


def test_invalid_catalogue_names_the_member(tmp_path: Path) -> None:
    rules = (PACKAGE / "rules.yaml").read_text(encoding="utf-8").replace(
        "detection: uniqueness", "detection: magic")
    with pytest.raises(ConfigurationError, match=r"PACKAGE_RULES: rules.yaml: rules\.\d+"):
        validate_generate_package(_package(tmp_path, rules=rules))


@pytest.mark.parametrize("package_id", ["crm", "computer"])
def test_another_package_cannot_declare_rules(tmp_path: Path, package_id: str) -> None:
    source = Path(str(files("tabalyst").joinpath("generate_examples", package_id)))
    package = _package(tmp_path, manifest={"rules": "rules.yaml"}, source=source)
    shutil.copyfile(PACKAGE / "rules.yaml", package / "rules.yaml")
    with pytest.raises(ConfigurationError,
                       match=r"rules is not supported by the [a-z_]+ package"):
        validate_generate_package(package)


@pytest.mark.parametrize("description", ["", "two\nlines", "x" * 501, 7, "red\x1b[31m",
                                         "line\u2028separator"])
def test_scenario_description_is_one_short_line(tmp_path: Path, description: object) -> None:
    with pytest.raises(ConfigurationError, match=r"operation.description must be one line"):
        validate_generate_package(_package(tmp_path, [_operation(description=description)]))


def test_operations_of_one_scenario_share_its_description(tmp_path: Path) -> None:
    operations = [_operation(description="One"),
                  _operation(column="telephone", description="Two")]
    with pytest.raises(ConfigurationError, match=r"scenario S1 declares description 'Two'"):
        validate_generate_package(_package(tmp_path, operations))
