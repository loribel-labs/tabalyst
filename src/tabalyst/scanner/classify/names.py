# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Name engine: the comparison form of a field name and the versioned rules that read it.

A name never creates a type (contract ``docs/dev/report/summary-table.md``
decision 14): the rules give hints that ``rules.py`` uses to reinforce a type the
values support, to break a tie between supported types, or to weaken one. This
module knows nothing of the values, so a rule is tested on a name alone.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from tabalyst.scanner.models import FieldResult

# Increased by every change of a rule, an expression or an operator below. It
# is part of ``Classification.rule_version`` (contract section 10).
NAME_RULES_VERSION = 2

Strength = Literal["exact", "sequence", "affix", "token"]
Polarity = Literal["supports", "weakens"]
Operator = Literal[
    "exact_any",
    "starts_with",
    "ends_with",
    "contains_token",
    "contains_sequence",
    "tokens_all",
]
Tokens = tuple[str, ...]

# From the most specific evidence to the weakest, so that of two rules for the
# same candidate the more specific one is kept.
_STRENGTH_RANK = {"exact": 0, "sequence": 1, "affix": 2, "token": 3}
_STRENGTH_OF: dict[Operator, Strength] = {
    "exact_any": "exact",
    "contains_sequence": "sequence",
    "tokens_all": "sequence",
    "starts_with": "affix",
    "ends_with": "affix",
    "contains_token": "token",
}

# A last token that says the column describes a property of the thing named
# before it (its status, its length, whether it is valid) and not the thing:
# ``email_status`` is not an email, ``customer_id_length`` is not an identifier.
DERIVED_MEASURE_TOKENS = frozenset(
    {
        "status",
        "statut",
        "length",
        "len",
        "longueur",
        "count",
        "nb",
        "nombre",
        "total",
        "sum",
        "format",
        "type",
        "valid",
        "invalid",
        "validity",
        "error",
        "errors",
        "check",
        "hash",
        "flag",
    }
)


# --- Comparison form ------------------------------------------------------------


def _split_case(text: str) -> str:
    """Put a space at the boundaries of CamelCase and of acronyms.

    ``CustomerID`` gives ``Customer ID``, ``ZIPCode`` gives ``ZIP Code`` and
    ``idClient`` gives ``id Client``. Digits stay with their word. This must run
    before the case is lost, which is why it is the second step.
    """
    out: list[str] = []
    for index, char in enumerate(text):
        if index:
            previous = text[index - 1]
            following = text[index + 1] if index + 1 < len(text) else ""
            lower_then_upper = (previous.islower() or previous.isdigit()) and (
                char.isupper()
            )
            acronym_end = previous.isupper() and char.isupper() and following.islower()
            if lower_then_upper or acronym_end:
                out.append(" ")
        out.append(char)
    return "".join(out)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    kept = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", kept)


def segment_tokens(segment: str) -> Tokens:
    """The tokens of one name, in the order that matters.

    Unicode NFC, CamelCase and acronyms, accents, lower case, then every run of
    characters that are not letters or digits is one separator.
    """
    text = _strip_accents(_split_case(unicodedata.normalize("NFC", segment))).lower()
    return tuple("".join(c if c.isalnum() else " " for c in text).split())


@dataclass(frozen=True, slots=True)
class NameParts:
    """A field name: the original untouched and the form compared by the rules.

    ``tokens`` are those of the last segment; the tokens of the segments before
    it (the parents of a JSON path) are kept as context, which no L0 rule reads.
    """

    original: str
    segments: tuple[str, ...]
    tokens: Tokens
    context: tuple[Tokens, ...]


def name_parts(name: str | Sequence[str] | NameParts) -> NameParts:
    """Split a name, or the segments of a JSON path, into the compared form.

    A literal key containing a dot is a single segment: the path segments
    decide, not the separators of the flattened display name.
    """
    if isinstance(name, NameParts):
        return name
    segments = (name,) if isinstance(name, str) else tuple(name)
    if not segments:
        return NameParts("", (), (), ())
    return NameParts(
        original=segments[-1],
        segments=segments,
        tokens=segment_tokens(segments[-1]),
        context=tuple(segment_tokens(item) for item in segments[:-1]),
    )


def name_tokens(name: str | Sequence[str] | NameParts) -> Tokens:
    """The comparison tokens of a name (the last segment of a path)."""
    return name_parts(name).tokens


def field_name_parts(field: FieldResult) -> NameParts:
    """The name of a field: its key segments for JSON, its header otherwise.

    The path of a JSON field gives its keys (array items are skipped); the other
    sources have no key and the header is the name.
    """
    from tabalyst.scanner.models import KeySegment

    keys = tuple(item.key for item in field.path if isinstance(item, KeySegment))
    return name_parts(keys or field.name)


# --- Operators ------------------------------------------------------------------


def exact_any(tokens: Tokens, expressions: Sequence[Tokens]) -> bool:
    """The whole name equals one of the expressions (``exact`` is a set of one)."""
    return tokens in expressions


def starts_with(tokens: Tokens, expression: Tokens) -> bool:
    """The first tokens equal the expression and the name goes on after them."""
    return len(tokens) > len(expression) and tokens[: len(expression)] == expression


def ends_with(tokens: Tokens, expression: Tokens) -> bool:
    """The last tokens equal the expression and the name starts before it."""
    return len(tokens) > len(expression) and tokens[-len(expression) :] == expression


def contains_token(tokens: Tokens, token: str) -> bool:
    """A whole token is present: ``id`` is not in ``validity``."""
    return token in tokens


def contains_sequence(tokens: Tokens, sequence: Tokens) -> bool:
    """The tokens appear contiguously and in order; scattered ones do not count."""
    size = len(sequence)
    return any(tokens[i : i + size] == sequence for i in range(len(tokens) - size + 1))


def tokens_all(tokens: Tokens, groups: Sequence[frozenset[str]]) -> bool:
    """Every group has a token in the name, in any order (a group is synonyms)."""
    return all(group & set(tokens) for group in groups)


def negative_match(tokens: Tokens) -> bool:
    """The name ends with a derived-measure token after at least one other token.

    The caller weakens the candidates that other operators found in the earlier
    tokens; nothing is erased and no type is imposed.
    """
    return len(tokens) > 1 and tokens[-1] in DERIVED_MEASURE_TOKENS


# --- Rules ----------------------------------------------------------------------

# A candidate is (family, type); the type is ``None`` for a whole family (Text,
# whose length is decided by the median).
Candidate = tuple[str, str | None]
_ANY_TECHNICAL = ("text", "integer", "number", "boolean", "date", "mixed")
_TEXTUAL = ("text", "mixed")
_DIGITS = ("text", "integer", "mixed")
_QUANTITATIVE = ("text", "integer", "number", "mixed")
_VULNERABLE: frozenset[Operator] = frozenset(
    {"starts_with", "contains_token", "contains_sequence", "tokens_all"}
)


@dataclass(frozen=True, slots=True)
class Match:
    """One operator over its expressions, in the form it compares.

    ``expressions`` are token tuples; for ``tokens_all`` each one is a group of
    synonyms written ``a|b``.
    """

    operator: Operator
    expressions: tuple[Tokens, ...]

    @property
    def vocabulary(self) -> frozenset[str]:
        return frozenset(token for item in self.expressions for token in item)

    def fires(self, tokens: Tokens) -> bool:
        if self.operator == "exact_any":
            return exact_any(tokens, self.expressions)
        if self.operator == "starts_with":
            return any(starts_with(tokens, item) for item in self.expressions)
        if self.operator == "ends_with":
            return any(ends_with(tokens, item) for item in self.expressions)
        if self.operator == "contains_token":
            return any(contains_token(tokens, item[0]) for item in self.expressions)
        if self.operator == "contains_sequence":
            return any(contains_sequence(tokens, item) for item in self.expressions)
        return tokens_all(tokens, [frozenset(item) for item in self.expressions])


def _m(operator: Operator, *phrases: str) -> Match:
    """A match from phrases such as ``"postal code"`` (``a|b`` for a group)."""
    return Match(operator, tuple(segment_tokens(phrase) for phrase in phrases))


def _groups(*groups: str) -> Match:
    """A ``tokens_all`` match: each argument is synonyms separated by ``|``."""
    return Match("tokens_all", tuple(tuple(group.split("|")) for group in groups))


@dataclass(frozen=True, slots=True)
class NameRule:
    """A rule of the registry: its id, how it matches and what it hints.

    ``candidate`` is the type the name suggests, ``weakens`` the types the name
    argues against. ``technical`` lists the technical types a hint is worth
    recording for as a name-only alternative. ``measure_veto`` turns the hints of
    the vulnerable operators into weakenings when the name ends with a
    derived-measure token (``email_status``).
    """

    id: str
    matches: tuple[Match, ...]
    candidate: Candidate | None
    weakens: tuple[Candidate, ...] = ()
    technical: tuple[str, ...] = _ANY_TECHNICAL
    measure_veto: bool = True


_ID: Candidate = ("identifier", "id")
_DATE: Candidate = ("temporal", "date")
_DATETIME: Candidate = ("temporal", "datetime")
_TIME: Candidate = ("temporal", "time")

# Only text and whole numbers can carry the identifier role (``rules.py`` turns
# these hints into ID and Unique ID): a date or a boolean named ``date_id`` is
# no identifier, and the role is not even worth listing as an alternative.
_IDENTIFIABLE = ("text", "integer")

NAME_RULES: tuple[NameRule, ...] = (
    NameRule(
        "name.identifier",
        (_m("exact_any", "id", "identifiant", "identifier"),),
        _ID,
        technical=_IDENTIFIABLE,
    ),
    NameRule(
        "name.id_suffix", (_m("ends_with", "id"),), _ID, technical=_IDENTIFIABLE
    ),
    NameRule(
        "name.id_prefix", (_m("starts_with", "id"),), _ID, technical=_IDENTIFIABLE
    ),
    NameRule(
        "name.reference_suffix",
        (_m("ends_with", "ref", "key"),),
        _ID,
        technical=_IDENTIFIABLE,
    ),
    NameRule(
        "tokens.customer_id",
        (_groups("client|customer", "id"),),
        _ID,
        technical=_IDENTIFIABLE,
    ),
    NameRule(
        "tokens.order_id",
        (_groups("order|commande", "id"),),
        _ID,
        technical=_IDENTIFIABLE,
    ),
    NameRule(
        "name.uuid",
        (_m("exact_any", "uuid", "guid"), _m("ends_with", "uuid", "guid")),
        ("web_network", "uuid"),
        technical=_TEXTUAL,
    ),
    NameRule(
        "name.url",
        (
            _m("exact_any", "url", "website", "web site", "site web"),
            _m("ends_with", "url"),
        ),
        ("web_network", "url"),
        technical=_TEXTUAL,
    ),
    NameRule(
        "name.email",
        (
            _m(
                "exact_any",
                "email",
                "e mail",
                "mail",
                "courriel",
                "email address",
                "adresse email",
                "adresse courriel",
            ),
            _m("ends_with", "email", "courriel", "mail"),
            _m("contains_token", "email", "courriel"),
        ),
        ("contact", "email"),
        technical=_TEXTUAL,
    ),
    NameRule(
        "name.phone",
        (
            _m(
                "exact_any",
                "telephone",
                "phone",
                "tel",
                "telephone mobile",
                "mobile phone",
                "phone number",
                "numero telephone",
            ),
            _m("ends_with", "phone", "telephone", "tel"),
            _m("contains_token", "phone", "telephone"),
        ),
        ("contact", "phone"),
        technical=_DIGITS,
    ),
    NameRule(
        "name.postal",
        (
            _m(
                "exact_any",
                "postal code",
                "code postal",
                "zip code",
                "zip",
                "postcode",
            ),
            _m("contains_sequence", "postal code", "code postal", "zip code"),
        ),
        ("geographic", "postal_code"),
        technical=_DIGITS,
    ),
    NameRule(
        "tokens.postal_code",
        (_groups("postal", "code"),),
        ("geographic", "postal_code"),
        technical=_DIGITS,
    ),
    NameRule(
        "name.boolean_prefix",
        (_m("starts_with", "is", "has", "can", "est"),),
        ("categorical", "boolean"),
        technical=("text", "boolean", "integer", "mixed"),
        measure_veto=False,
    ),
    NameRule(
        "name.flag_suffix",
        (_m("ends_with", "flag"),),
        ("categorical", "boolean"),
        technical=("text", "boolean", "integer", "mixed"),
        measure_veto=False,
    ),
    NameRule(
        "name.sex_category",
        (_m("exact_any", "sexe", "sex", "gender", "genre"),),
        ("categorical", "enum"),
        weakens=(("categorical", "boolean"),),
        technical=("text", "integer", "mixed"),
    ),
    NameRule(
        "name.birth_date",
        (_m("exact_any", "birth date", "date naissance", "date of birth", "dob"),),
        _DATE,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "tokens.birth_date",
        (_groups("birth|naissance", "date"),),
        _DATE,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.date",
        (_m("exact_any", "date"),),
        _DATE,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.date_suffix",
        (_m("ends_with", "date"),),
        _DATE,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.date_prefix",
        (_m("starts_with", "date"),),
        _DATE,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.datetime",
        (
            _m(
                "exact_any",
                "created at",
                "updated at",
                "modified at",
                "deleted at",
                "timestamp",
                "datetime",
                "date time",
            ),
        ),
        _DATETIME,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.at_suffix",
        (_m("ends_with", "at"),),
        _DATETIME,
        technical=_TEXTUAL + ("date",),
    ),
    NameRule(
        "name.time_suffix",
        (_m("exact_any", "time", "heure"), _m("ends_with", "time", "heure")),
        _TIME,
        technical=_TEXTUAL + ("date",),
    ),
    # A year, a month or a day is not a date: ``birth_year`` is no generic Date.
    NameRule(
        "name.calendar_part",
        (_m("contains_token", "year", "annee", "month", "mois", "day", "jour"),),
        None,
        weakens=(_DATE, _DATETIME, _TIME),
        measure_veto=False,
    ),
    NameRule(
        "name.text",
        (
            _m(
                "exact_any",
                "description",
                "commentaire",
                "comment",
                "comments",
                "note",
                "notes",
                "remarque",
                "remarques",
            ),
        ),
        ("text", None),
        technical=("text",),
    ),
    NameRule(
        "name.amount",
        (
            _m(
                "exact_any",
                "price",
                "prix",
                "amount",
                "montant",
                "cost",
                "cout",
            ),
            _m("ends_with", "price", "amount", "cost", "prix", "montant"),
            _m("starts_with", "prix", "montant"),
        ),
        ("numeric", "currency"),
        technical=_QUANTITATIVE,
    ),
    NameRule(
        "name.quantity",
        (
            _m("exact_any", "quantity", "quantite", "qty"),
            _m("ends_with", "qty", "quantity"),
            _m("starts_with", "quantite"),
        ),
        ("numeric", "quantity"),
        technical=_QUANTITATIVE,
    ),
    NameRule(
        "name.percentage",
        (
            _m("ends_with", "pct", "percent", "percentage", "pourcentage"),
            _groups("discount|remise", "pct|percent|pourcentage"),
        ),
        ("numeric", "percentage"),
        technical=_QUANTITATIVE,
    ),
)

DERIVED_MEASURE_RULE = "name.derived_measure"


@dataclass(frozen=True, slots=True)
class NameHint:
    """What a name says about one candidate.

    ``strength`` is how the name matched, ``polarity`` whether it supports or
    weakens the candidate. A hint carries no score. ``via`` is the rule whose
    support a derived-measure token turned into a weakening.
    """

    rule: str
    family: str
    type: str | None
    strength: Strength
    polarity: Polarity
    technical: tuple[str, ...] = _ANY_TECHNICAL
    via: str | None = None

    @property
    def candidate(self) -> Candidate:
        return self.family, self.type

    def covers(self, family: str, type_: str) -> bool:
        """Whether the hint is about this pair (a family-wide hint covers its types)."""
        return self.family == family and self.type in (None, type_)

    def sort_key(self) -> tuple[str, str, str, int, str]:
        return (
            self.family,
            self.type or "",
            self.polarity,
            _STRENGTH_RANK[self.strength],
            self.rule,
        )


def _fired(rule: NameRule, tokens: Tokens) -> list[tuple[Match, bool]]:
    """The matches of a rule that fire, each with whether a measure token vetoes it."""
    fired = []
    for match in rule.matches:
        if not match.fires(tokens):
            continue
        vetoed = (
            rule.measure_veto
            and match.operator in _VULNERABLE
            and negative_match(tokens)
            and tokens[-1] not in match.vocabulary
        )
        fired.append((match, vetoed))
    return fired


def _strongest(matches: list[Match]) -> Strength | None:
    if not matches:
        return None
    return min(
        (_STRENGTH_OF[m.operator] for m in matches), key=_STRENGTH_RANK.__getitem__
    )


def _evaluate(rule: NameRule, tokens: Tokens) -> list[NameHint]:
    """The hints one rule gives for a name.

    A match that a derived-measure token vetoes weakens the candidate under the
    rule ``name.derived_measure``; the others support it.
    """
    fired = _fired(rule, tokens)
    supporting = _strongest([m for m, vetoed in fired if not vetoed])
    vetoed_strength = _strongest([m for m, vetoed in fired if vetoed])
    hints: list[NameHint] = []
    if rule.candidate is not None:
        family, type_ = rule.candidate
        if supporting is not None:
            hints.append(
                NameHint(rule.id, family, type_, supporting, "supports", rule.technical)
            )
        if vetoed_strength is not None:
            hints.append(
                NameHint(
                    DERIVED_MEASURE_RULE,
                    family,
                    type_,
                    vetoed_strength,
                    "weakens",
                    rule.technical,
                    via=rule.id,
                )
            )
    if supporting is not None:
        hints += [
            NameHint(rule.id, family, type_, supporting, "weakens", rule.technical)
            for family, type_ in rule.weakens
        ]
    return hints


def name_hints(name: str | Sequence[str] | NameParts) -> tuple[NameHint, ...]:
    """The hints of the rules for a name, one per candidate and polarity.

    Several rules that agree on the same candidate are correlated evidence of
    the name, not independent: the most specific is kept, ties by rule id, so
    the order of the registry changes nothing.
    """
    tokens = name_parts(name).tokens
    if not tokens:
        return ()
    best: dict[tuple[Candidate, str], NameHint] = {}
    for rule in NAME_RULES:
        for hint in _evaluate(rule, tokens):
            key = (hint.candidate, hint.polarity)
            kept = best.get(key)
            if kept is None or hint.sort_key() < kept.sort_key():
                best[key] = hint
    return tuple(sorted(best.values(), key=NameHint.sort_key))


# --- Tie-break ------------------------------------------------------------------

Pair = tuple[str, str]


@dataclass(frozen=True, slots=True)
class TieBreak:
    """What the name does to credible types the values cannot separate.

    ``winner`` is set when the name leaves exactly one. ``remaining`` are the
    types still in competition, ``removed`` the ones the name weakened and
    ``outranked`` the ones a supported type passed.
    """

    winner: Pair | None
    remaining: tuple[Pair, ...]
    removed: tuple[Pair, ...]
    outranked: tuple[Pair, ...]


def break_tie(pairs: Sequence[Pair], hints: Sequence[NameHint]) -> TieBreak:
    """Separate credible types by their names.

    A weakened type is removed only while another one stays. If exactly one of
    the rest is supported by the name it wins; with no supported type, the sole
    survivor of the weakening wins; otherwise the competition goes on among the
    supported types, or among the survivors.
    """

    def weakened(pair: Pair) -> bool:
        return any(h.polarity == "weakens" and h.covers(*pair) for h in hints)

    def supported(pair: Pair) -> bool:
        return any(h.polarity == "supports" and h.covers(*pair) for h in hints)

    survivors = [pair for pair in pairs if not weakened(pair)]
    if not survivors:
        survivors = list(pairs)
    removed = tuple(pair for pair in pairs if pair not in survivors)
    remaining = [pair for pair in survivors if supported(pair)] or survivors
    outranked = tuple(pair for pair in survivors if pair not in remaining)
    winner = remaining[0] if len(remaining) == 1 else None
    return TieBreak(winner, tuple(remaining), removed, outranked)
