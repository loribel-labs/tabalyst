# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verifiable rules of a Generate package: their grammar, their catalogue and a pure evaluator.

The contract is ``docs/dev/generate/insurance-v2.md`` 5.3. Rules are data (D10): the generator
checks its clean file with them and a reader of ``rules.json`` can check a row with them alone.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from tabalyst.generate_scenarios import DETECTION_FAMILIES

RULES_FORMAT: Final = "tabalyst.generate.rules"
FORMAT_VERSION: Final = "0.2.0"
FORMAT_REVISION: Final = 1

ColumnName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
# The pattern of a scenario id (contract 3.5): ``M17``, ``F09``.
RuleId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{0,15}$")]
ValueType = Literal["date", "decimal", "text"]
# The categories of contract 3.1 a rule can break (``valid_atypical`` is never a defect).
Category = Literal["format_variant", "format_invalid", "semantic_invalid",
                   "business_rule_violation", "contextual_invalid"]
Severity = Literal["info", "minor", "major", "critical"]
_PLAIN_DECIMAL = re.compile(r"[+-]?\d+(?:\.\d+)?")
_ISO_DATE = "%Y-%m-%d"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Constant(_Model):
    """A constant operand, written as text and read with the type of its comparison."""

    value: str


class Parameter(_Model):
    """An operand taken from the document: ``as_of_date`` is the reference date of the run."""

    param: Literal["as_of_date"]


# A bare string names a column; an object is a constant or a parameter.
Operand = ColumnName | Constant | Parameter


class Compare(_Model):
    """``left <op> right`` read as ``as``; false when an operand is empty or unreadable."""

    op: Literal["eq", "gt", "gte", "lt", "lte"]
    left: Operand
    right: Operand
    as_: ValueType = Field("text", alias="as")


class Between(_Model):
    """``low <= column <= high`` read as ``as``."""

    op: Literal["between"]
    column: ColumnName
    low: Operand
    high: Operand
    as_: ValueType = Field("text", alias="as")


class Membership(_Model):
    """The cell is (``in``) or is not (``not_in``) one of ``values``, compared as text."""

    op: Literal["in", "not_in"]
    column: ColumnName
    values: list[str] = Field(min_length=1, max_length=4096)


class Pattern(_Model):
    """The whole cell matches the regular expression ``pattern``."""

    op: Literal["regex"]
    column: ColumnName
    pattern: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _compiles(self) -> Pattern:
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"regex pattern does not compile: {exc}") from exc
        return self


class Presence(_Model):
    """The cell is not empty (``not_empty``) or empty (``empty``)."""

    op: Literal["not_empty", "empty"]
    column: ColumnName


class Unique(_Model):
    """No two rows where the rule applies share the values of ``columns``.

    The only rule that reads several rows: it stands alone as the ``assert`` of a rule.
    """

    op: Literal["unique"]
    columns: list[ColumnName] = Field(min_length=1, max_length=16)


class Implies(_Model):
    """``then`` holds wherever ``if`` holds."""

    op: Literal["implies"]
    if_: Expression = Field(alias="if")
    then: Expression


class Junction(_Model):
    """Every (``and``) or any (``or``) of ``args`` holds."""

    op: Literal["and", "or"]
    args: list[Expression] = Field(min_length=2, max_length=64)


class Negation(_Model):
    """``arg`` does not hold."""

    op: Literal["not"]
    arg: Expression


Expression = Annotated[
    Compare | Between | Membership | Pattern | Presence | Unique | Implies | Junction | Negation,
    Field(discriminator="op"),
]
Implies.model_rebuild()
Junction.model_rebuild()
Negation.model_rebuild()

OPERATORS: Final = frozenset({
    "eq", "gt", "gte", "lt", "lte", "between", "in", "not_in", "regex", "not_empty", "empty",
    "unique", "implies", "and", "or", "not",
})


def _children(expression: Expression) -> list[Expression]:
    if isinstance(expression, Implies):
        return [expression.if_, expression.then]
    if isinstance(expression, Junction):
        return list(expression.args)
    if isinstance(expression, Negation):
        return [expression.arg]
    return []


def expression_columns(expression: Expression) -> set[str]:
    """Return the columns an expression reads."""
    found: set[str] = set()
    if isinstance(expression, Compare):
        found.update(o for o in (expression.left, expression.right) if isinstance(o, str))
    elif isinstance(expression, Between):
        found.add(expression.column)
        found.update(o for o in (expression.low, expression.high) if isinstance(o, str))
    elif isinstance(expression, Membership | Pattern | Presence):
        found.add(expression.column)
    elif isinstance(expression, Unique):
        found.update(expression.columns)
    for child in _children(expression):
        found |= expression_columns(child)
    return found


def _nested_unique(expression: Expression) -> bool:
    return any(isinstance(child, Unique) or _nested_unique(child)
               for child in _children(expression))


class Rule(_Model):
    """One verifiable rule: where it applies, what must hold and what is allowed anyway.

    A row breaks the rule when ``when`` holds (or is absent), ``assert`` does not hold and no
    expression of ``exceptions`` holds. ``valid_boundaries`` describe, for people, the values
    that sit on the rule and are valid; they are never evaluated.
    """

    id: RuleId
    family: Literal["business", "format", "domain"]
    title: str = Field(min_length=1, max_length=200)
    columns: list[ColumnName] = Field(min_length=1, max_length=64)
    category: Category
    severity: Severity
    detection: str
    when: Expression | None = None
    assert_: Expression = Field(alias="assert")
    exceptions: list[Expression] = Field(default_factory=list, max_length=32)
    valid_boundaries: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def _coherent(self) -> Rule:
        tokens = self.detection.split("|")
        if (any(token not in DETECTION_FAMILIES - {"none"} for token in tokens)
                or len(set(tokens)) != len(tokens)):
            raise ValueError("detection must join distinct families of "
                             f"{', '.join(sorted(DETECTION_FAMILIES - {'none'}))} with |")
        guards = [self.when, *self.exceptions] if self.when is not None else list(self.exceptions)
        if (_nested_unique(self.assert_)
                or any(isinstance(g, Unique) or _nested_unique(g) for g in guards)):
            raise ValueError("unique stands alone as the assert of a rule")
        read = expression_columns(self.assert_)
        for guard in guards:
            read |= expression_columns(guard)
        if len(set(self.columns)) != len(self.columns) or read != set(self.columns):
            raise ValueError(
                f"columns must list, once each, the columns the rule reads: {sorted(read)}")
        return self


class Conventions(_Model):
    """What a reader needs to read the cells: the branch of a row and its date format."""

    branch_column: ColumnName
    date_format: dict[str, str] = Field(min_length=1)
    decimal: Literal["plain"] = "plain"


class RuleCatalogue(_Model):
    """The rules a package declares (its ``rules.yaml``); a profile uses those it names."""

    conventions: Conventions
    rules: list[Rule] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _distinct(self) -> RuleCatalogue:
        ids = [rule.id for rule in self.rules]
        if len(set(ids)) != len(ids):
            raise ValueError("rule ids must be distinct")
        return self

    def by_id(self) -> dict[str, Rule]:
        """Return the rules indexed by id, in catalogue order."""
        return {rule.id: rule for rule in self.rules}


class RulesDocument(_Model):
    """``<dataset>.<profile>.rules.json``: the rules a profile uses, with its conventions."""

    format: Literal["tabalyst.generate.rules"] = RULES_FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    dataset: str
    profile: str
    as_of_date: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    conventions: Conventions
    rules: list[Rule]


@dataclass(frozen=True)
class Violation:
    """A row that breaks a rule.

    ``group_id`` names the rows of one multi-row case (a repeated key), empty otherwise.
    ``cause_row`` is the row whose values made the case: the repeat for the first row of a
    repeated key, the row itself otherwise.
    """

    rule_id: str
    row_number: int
    group_id: str
    cause_row: int


class RuleContext:
    """Read cells and constants with the conventions and the reference date of a document."""

    def __init__(self, conventions: Conventions, as_of_date: str) -> None:
        self.conventions = conventions
        self.as_of_date = as_of_date

    def _operand(self, operand: Operand, row: Mapping[str, str]) -> tuple[str, bool]:
        """Return the text of an operand and whether it is a cell (read in the row's format)."""
        if isinstance(operand, str):
            return row.get(operand, ""), True
        if isinstance(operand, Constant):
            return operand.value, False
        return self.as_of_date, False

    def read(self, operand: Operand, row: Mapping[str, str],
             kind: ValueType) -> date | Decimal | str | None:
        """Return the typed value of an operand, or None when it is empty or unreadable.

        A date cell is read with the format of its row's branch and must be written exactly
        that way (``2026-1-5`` is not ``2026-01-05``); a constant date is ISO 8601.
        """
        text, cell = self._operand(operand, row)
        if not text:
            return None
        if kind == "text":
            return text
        if kind == "decimal":
            if not _PLAIN_DECIMAL.fullmatch(text):
                return None
            try:
                return Decimal(text)
            except InvalidOperation:
                return None
        if cell:
            pattern = self.conventions.date_format.get(
                row.get(self.conventions.branch_column, ""))
            if pattern is None:
                return None
        else:
            pattern = _ISO_DATE
        try:
            parsed = datetime.strptime(text, pattern)  # noqa: DTZ007 - a date has no zone
        except ValueError:
            return None
        return parsed.date() if parsed.strftime(pattern) == text else None


def _compare(op: str, left: date | Decimal | str, right: date | Decimal | str) -> bool:
    if op == "eq":
        return left == right
    if op == "gt":
        return left > right  # type: ignore[operator]
    if op == "gte":
        return left >= right  # type: ignore[operator]
    if op == "lt":
        return left < right  # type: ignore[operator]
    return left <= right  # type: ignore[operator]


def holds(expression: Expression, row: Mapping[str, str], context: RuleContext) -> bool | None:
    """Tell whether a row-level expression holds for one row: True, False or None (unknown).

    A test of a value is unknown when the cell is empty or does not read as its type: an
    absent or malformed value is the subject of a presence or format rule, never a business
    violation (``format_vs_business``, report 4). ``and``, ``or``, ``not`` and ``implies``
    follow three-valued (Kleene) logic; ``not_empty`` and ``empty`` are always known.
    ``unique`` reads several rows and is evaluated by ``RuleEvaluator``; here it raises
    ValueError.
    """
    if isinstance(expression, Compare):
        left = context.read(expression.left, row, expression.as_)
        right = context.read(expression.right, row, expression.as_)
        if left is None or right is None:
            return None
        return _compare(expression.op, left, right)
    if isinstance(expression, Between):
        value = context.read(expression.column, row, expression.as_)
        low = context.read(expression.low, row, expression.as_)
        high = context.read(expression.high, row, expression.as_)
        if value is None or low is None or high is None:
            return None
        return _compare("gte", value, low) and _compare("lte", value, high)
    if isinstance(expression, Membership | Pattern):
        cell = row.get(expression.column, "")
        if not cell:
            return None
        if isinstance(expression, Pattern):
            return re.fullmatch(expression.pattern, cell) is not None
        return (cell in expression.values) == (expression.op == "in")
    if isinstance(expression, Presence):
        present = row.get(expression.column, "") != ""
        return present if expression.op == "not_empty" else not present
    if isinstance(expression, Implies):
        condition = holds(expression.if_, row, context)
        if condition is False:
            return True
        result = holds(expression.then, row, context)
        return True if result is True else (None if condition is None else result)
    if isinstance(expression, Junction):
        results = [holds(arg, row, context) for arg in expression.args]
        decisive = expression.op == "or"
        if decisive in results:
            return decisive
        return None if None in results else not decisive
    if isinstance(expression, Negation):
        result = holds(expression.arg, row, context)
        return None if result is None else not result
    raise ValueError("unique reads several rows: evaluate it with RuleEvaluator")


class RuleEvaluator:
    """Check the rows of one file, in order, against a list of rules.

    A row breaks a rule when ``when`` is absent or true, no exception is true and ``assert``
    is false; an unknown ``assert`` is not a violation. Memory is constant per row-level rule;
    a ``unique`` rule keeps the keys it has seen, one entry per row where it applies.
    """

    def __init__(self, rules: Sequence[Rule], context: RuleContext) -> None:
        self.rules = tuple(rules)
        self.context = context
        self._first: dict[str, dict[tuple[str, ...], int]] = {
            rule.id: {} for rule in self.rules if isinstance(rule.assert_, Unique)}
        self._grouped: set[tuple[str, int]] = set()

    def check(self, row_number: int, row: Mapping[str, str]) -> list[Violation]:
        """Return the violations this row reveals, in rule order.

        A repeated key reveals two rows the first time: the earlier one and this one. A key
        with an empty part is unknown and never repeats.
        """
        found: list[Violation] = []
        for rule in self.rules:
            if rule.when is not None and holds(rule.when, row, self.context) is not True:
                continue
            if any(holds(exception, row, self.context) is True
                   for exception in rule.exceptions):
                continue
            target = rule.assert_
            if isinstance(target, Unique):
                key = tuple(row.get(column, "") for column in target.columns)
                if not all(key):
                    continue
                first = self._first[rule.id].setdefault(key, row_number)
                if first == row_number:
                    continue
                group = f"{rule.id}-{first}"
                if (rule.id, first) not in self._grouped:
                    self._grouped.add((rule.id, first))
                    found.append(Violation(rule.id, first, group, row_number))
                found.append(Violation(rule.id, row_number, group, row_number))
            elif holds(target, row, self.context) is False:
                found.append(Violation(rule.id, row_number, "", row_number))
        return found


def parse_catalogue(document: object) -> RuleCatalogue:
    """Validate the rules catalogue of a package.

    Raises ValueError naming the member and the rule that failed, for example
    ``rules.2.assert: ...``.
    """
    try:
        return RuleCatalogue.model_validate(document)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "catalogue"
        raise ValueError(f"{where}: {first['msg']}") from exc
