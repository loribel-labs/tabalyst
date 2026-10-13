# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What the hierarchical discovery must find in each field of the reference
corpus: families, nodes, facet tables and exact counts (algorithm, sections 7
and 8, as checked by ``test_pattern_score.py``).

Family labels use the decided notation (OPEN-003: ``A`` capital, ``X`` capital
or digit, quoted constants); a family has no range of lengths, it lists its
patterns, one per set of lengths (DEC-034). The score reads whole prefixes (DEC-029 to DEC-031, 12 October 2026).
"""

from __future__ import annotations

from pattern_tree import (
    Declared,
    Expected,
    Family,
    Key,
    Node,
    Rule,
    Table,
    lengths,
    token,
)

from tabalyst.scanner.detectors.phone import PhoneDetector


def head(text: str, distinct: int, index: int = 1, occurrences: int | None = None, children: tuple[Node, ...] = ()) -> Node:
    """A node of the values whose token ``index`` starts with ``text``."""
    return Node(
        f"head:{index}:{text}",
        lambda v: token(v, index).startswith(text),
        distinct,
        distinct if occurrences is None else occurrences,
        children,
    )


def whole(text: str, distinct: int, index: int, children: tuple[Node, ...] = ()) -> Node:
    """A node of the values whose token ``index`` is ``text``."""
    return Node(
        f"token:{index}:{text}", lambda v: token(v, index) == text, distinct, distinct, children
    )


def length(sizes: tuple[int, ...], distinct: int, occurrences: int | None = None, children: tuple[Node, ...] = ()) -> Node:
    """The pattern of the values whose class tokens have the lengths ``sizes``:
    every set of lengths is a pattern of its family (DEC-034)."""
    return Node(
        "length:" + ",".join(map(str, sizes)),
        lambda v: lengths(v) == sizes,
        distinct,
        distinct if occurrences is None else occurrences,
        children,
    )


def composition(last_is_digit: bool, distinct: int) -> Node:
    return Node(
        "composition:DDDDD" if last_is_digit else "composition:DDDDU",
        lambda v: v[-1].isdigit() is last_is_digit,
        distinct,
        distinct,
    )


# A node may not fix a whole value, nor more than three characters of a head
# (RC-11: no complete number is published).
WHOLE_VALUE = Rule("whole value", lambda v: v)
LONG_HEAD = Rule("head longer than 3", lambda v: v[:4])

RC03_NODES = tuple(head(prefix, 50) for prefix in ("AB", "AK", "AZ", "BC", "CD", "DE", "KM", "PQ", "RT", "ZX"))
RC08_AGES = {age: 50 for age in ("21", "22", "23", "24", "71", "72", "73", "74")}
RC08_TAGS = (("LA", 80), ("LB", 60), ("LC", 20), ("MA", 60), ("MB", 40), ("YA", 50), ("YB", 30), ("KA", 30), ("KB", 20), ("KC", 10))
RC16_TAIL_00 = 306

EXPECTED: tuple[Expected, ...] = (
    Expected(
        "RC-01/toy",
        (
            Family(
                "'AK'-999 / 'AK'-9999",
                frozenset({"UP-D"}),
                6,
                6,
                constants=("head:1:AK",),
                nodes=(length((2, 3), 3), length((2, 4), 3)),
            ),
        ),
        note="Lengths and folded constants are rules, not scores: the toy concludes.",
    ),
    Expected(
        "RC-02/scaled",
        (
            Family(
                "'A'A-9999X",
                frozenset({"UP-D", "UP-DU"}),
                200,
                200,
                constants=("head:1:A",),
                nodes=(composition(True, 150), composition(False, 50)),
                tables=(
                    Table("head:1", lambda v: v[:2], {"AK": 80, "AB": 72, "AZ": 48}),
                ),
            ),
        ),
        note="The second letter is independent of the last character: a table.",
    ),
    Expected(
        "RC-02/toy",
        (
            Family(
                "'A'A-9999X",
                frozenset({"UP-D", "UP-DU"}),
                4,
                4,
                constants=("head:1:A",),
                nodes=(composition(True, 3), composition(False, 1)),
                exhaustive=False,
            ),
        ),
        note="Composition nodes need no gain (E3): the toy gives 3 + 1.",
    ),
    Expected(
        "RC-03/scaled",
        (Family("AA-9999", frozenset({"UP-D"}), 500, 500, nodes=RC03_NODES),),
        note="The A? prefixes cover their intermediate A: it is flattened.",
    ),
    Expected(
        "RC-03/toy",
        (Family("AA-9999", frozenset({"UP-D"}), 5, 5),),
        conclusive=False,
        note="Too few values to conclude (algorithm 9.1).",
    ),
    Expected(
        "RC-04/weighted",
        (
            Family(
                "'A'A-9999",
                frozenset({"UP-D"}),
                4,
                20_600,
                constants=("head:1:A",),
                nodes=(head("AK", 2, occurrences=20_000),),
            ),
        ),
        note="AB and AZ carry all their occurrences on one value: the guard refuses them.",
    ),
    Expected(
        "RC-05/invoices",
        (
            Family(
                "AAA-'202'9-999999",
                frozenset({"UP-DP-D"}),
                400,
                400,
                nodes=(head("INV", 200), head("ORD", 200)),
                tables=(Table("token:3", lambda v: token(v, 3), {"2025": 200, "2026": 200}),),
            ),
        ),
        note="The year is independent of the prefix: a table of the family (AC-009).",
    ),
    Expected(
        "RC-05/invoices_dependent",
        (
            Family(
                "AAA-'202'9-999999",
                frozenset({"UP-DP-D"}),
                400,
                400,
                nodes=(
                    head("INV", 200, children=(whole("2025", 150, 3), whole("2026", 50, 3))),
                    head("ORD", 200, children=(whole("2025", 50, 3), whole("2026", 150, 3))),
                ),
            ),
        ),
        note="The year depends on the prefix (dependence 0.19 >= 0.10): four leaves.",
    ),
    Expected(
        "RC-05/references",
        (
            Family(
                "AAA-999999",
                frozenset({"UP-D"}),
                250,
                250,
                nodes=(head("CUS", 150), head("SUP", 100)),
            ),
            Family(
                "'PRD'-AA-999999",
                frozenset({"UP-UP-D"}),
                150,
                150,
                constants=("head:1:PRD",),
                nodes=(head("CA", 80, index=3), head("US", 70, index=3)),
            ),
        ),
        note="Two families, not three: CUS and SUP share the structure UP-D.",
    ),
    Expected(
        "RC-06/invoices",
        (
            Family(
                "'INV'-999 / 'INV'-9999 / 'INV'-99999",
                frozenset({"UP-D"}),
                300,
                300,
                constants=("head:1:INV",),
                nodes=(length((3, 3), 100), length((3, 4), 100), length((3, 5), 100)),
            ),
            Family(
                "'INV'-'2026'-99999",
                frozenset({"UP-DP-D"}),
                100,
                100,
                constants=("head:1:INV", "token:3:2026"),
            ),
        ),
        note="No pattern of any text covers both structures (AC-010).",
    ),
    Expected(
        "RC-07/plates",
        (
            Family("999 AAA", frozenset({"DP U"}), 200, 200),
            Family(
                "AAA 999 / 'C'A 9999",
                frozenset({"UP D"}),
                300,
                300,
                nodes=(
                    length((3, 3), 200),
                    length((2, 4), 100, children=(head("CC", 60), head("CD", 40))),
                ),
            ),
            Family(
                "A99 AAA / 'V'A9 AAA",
                frozenset({"UDP U"}),
                300,
                300,
                nodes=(
                    length((1, 2, 3), 150),
                    length((2, 1, 3), 150, children=(head("VA", 90), head("VE", 60))),
                ),
            ),
            Family("999'H'999", frozenset({"DUD"}), 50, 50, constants=("token:2:H",)),
        ),
        note="'C'A 9999 is the pattern of the lengths 2,4 with C folded, not a node.",
    ),
    Expected(
        "RC-08/plates",
        (
            Family("AA-999-AA", frozenset({"UP-DP-U"}), 600, 600),
            Family(
                "AA99 AAA",
                frozenset({"UDP U"}),
                400,
                400,
                nodes=tuple(head(tag, count) for tag, count in RC08_TAGS),
                tables=(Table("token:2", lambda v: token(v, 2), RC08_AGES),),
            ),
        ),
        note="French letters are near uniform (sigma far below 0.10): no facet.",
    ),
    Expected(
        "RC-09/permits",
        (Family("A9{12}", frozenset({"UD"}), 10_000, 10_000),),
        note="The initial letter and the digits are uniform: no facet.",
    ),
    Expected(
        "RC-10/nine_30",
        (Family("9{9}", frozenset({"D"}), 1_000, 1_000, nodes=(head("9", 300),)),),
        note=(
            "A literal 9 in 30 % of the values: sigma 0.14, b_f of one digit (DEC-030). "
            "The Scan types the column as integers: eligibility (B2) must admit it."
        ),
    ),
    Expected(
        "RC-10/nine_10",
        (Family("9{9}", frozenset({"D"}), 1_000, 1_000),),
        note="A 9 in 10 % of the values is chance for a digit.",
    ),
    Expected(
        "RC-11/cards",
        (
            Family(
                "9{16} / '3'9{14} / '36'9{12}",
                frozenset({"D"}),
                1_000,
                1_000,
                nodes=(
                    length(
                        (16,),
                        800,
                        children=(head("4", 400),) + tuple(head(f"5{d}", 64) for d in range(1, 6)),
                    ),
                    length((15,), 150, children=(head("34", 75), head("37", 75))),
                    length((14,), 50),
                ),
                forbidden=(WHOLE_VALUE, LONG_HEAD),
            ),
        ),
        note=(
            "6 is 10 % of the 16-digit cards: chance, no node. The Scan types the "
            "column as integers: eligibility (B2) must admit it."
        ),
    ),
    Expected(
        "RC-12/isbn",
        (
            Family(
                "'97'9-…-9 (many lengths)",
                frozenset({"DP-DP-DP-DP-D"}),
                1_000,
                1_000,
                constants=("head:1:97",),
                nodes=(
                    head(
                        "978",
                        700,
                        children=(
                            whole("0", 200, 3),
                            whole("1", 150, 3),
                            whole("2", 250, 3),
                            whole("3", 100, 3),
                        ),
                    ),
                    head("979", 300, children=(whole("10", 200, 3), whole("8", 100, 3))),
                ),
            ),
        ),
        conclusive=False,
        note=(
            "A poor candidate: more than six sets of lengths, one pattern each "
            "(DEC-034); the eligibility (B2) should set it aside. If it is kept, "
            "978 and 979 and their dependent groups sit under each length."
        ),
    ),
    Expected(
        "RC-12/codes",
        (
            Family(
                "AA / AAA",
                frozenset({"U"}),
                55,
                1_000,
                nodes=(length((2,), 40, 600), length((3,), 15, 400)),
                allowed=(Rule("head:1", lambda v: v[0]),),
                forbidden=(WHOLE_VALUE,),
            ),
        ),
        note="No node per code: a node would fix every free position.",
    ),
    Expected(
        "RC-13/identifiers",
        (
            Family(
                "AA-999999",
                frozenset({"UP-D"}),
                10_000,
                10_000,
                nodes=(head("AK", 9_500), head("AB", 400), head("AZ", 90)),
            ),
        ),
        note="Whole prefixes (DEC-029): AZ saves 223 bits; the 10 isolated go to the rest.",
    ),
    Expected(
        "RC-14/prefixes",
        (
            Family(
                "AA-9999",
                frozenset({"UP-D"}),
                400,
                400,
                nodes=tuple(head(p, 50) for p in ("AK", "BC", "CD", "DE", "EF", "FG", "GH", "HJ")),
            ),
        ),
        note="The second pass counts the 4 new prefixes in the same table (B5).",
    ),
    Expected(
        "RC-15/raw_variants",
        tuple(
            Family(label, frozenset({key}), 1, 1)
            for label, key in (
                ("'AK'-'1234'", "UP-D"),
                ("'ak'-'1234'", "LP-D"),
                ("'AK' '1234'", "UP D"),
                ("'AK'- '1234'", "UP-P D"),
                ("'AK''1234'", "UD"),
            )
        ),
        note="Five structures, never merged: their stable part is empty (AC-018).",
    ),
    Expected(
        "RC-16/lots",
        (
            Family(
                "AAA-99-999999-AA",
                frozenset({"UP-DP-DP-U"}),
                1_000,
                1_000,
                nodes=(head("LOT", 700), head("SER", 300)),
                tables=(
                    Table(
                        "token:3",
                        lambda v: token(v, 3),
                        {"07": 600, "12": 300, "31": 100},
                    ),
                    Table("token:7", lambda v: token(v, 7), {"EU": 500, "NA": 400, "AS": 100}),
                    Table(
                        "tail:5",
                        lambda v: "00" if token(v, 5).endswith("00") else "rest",
                        {"00": RC16_TAIL_00, "rest": 1_000 - RC16_TAIL_00},
                        required=frozenset({"00"}),
                    ),
                ),
            ),
        ),
        note=(
            "The tail 00 (30.6 %) is a table of the family, not a node (decided on "
            "12 October 2026): the prefix is primary and the tail does not depend on it."
        ),
    ),
    Expected(
        "RC-17/noise",
        (Family("AA-9999", frozenset({"UP-D"}), 1_000, 1_000),),
        note="Uniform noise: one family, zero variants (AC-030).",
    ),
    Expected(
        "RC-20/postal_codes",
        (
            Family(
                "A9A 9A9",
                frozenset({"UDUP DUD"}),
                9_933,
                10_000,
                forbidden=(
                    Rule("tail:1", lambda v: v[-1:]),
                    Rule("tail:2", lambda v: v[-2:]),
                    Rule("tail:3", lambda v: v[-3:]),
                ),
                exhaustive=False,
            ),
        ),
        note="The generic discovery may keep letters; the uniform end never.",
    ),
)


def expected(field_id: str) -> Expected:
    for candidate in EXPECTED:
        if candidate.field == field_id:
            return candidate
    raise KeyError(field_id)


# Declared keys (algorithm, section 4; DEC-027, DEC-028) ---------------------------------

# The listings stop: RC-18 by coverage (fr, 2.9 %, falls after net, 3.5 %),
# RC-19 by coverage under both regions, RC-20 by coverage at S (2 %, above the
# 0.5 % floor) and, under R, by the 5 occurrences (areas of 4 lines at 2 %).
DECLARED: tuple[Declared, ...] = (
    Declared(
        "RC-18/emails",
        "email",
        (
            Key(
                "com",
                7_540,
                (Key("gmail.com", 4_000), Key("hotmail.com", 1_200), Key("outlook.com", 800)),
                other=(997, 1_540),
            ),
            Key("ca", 1_819, (Key("videotron.ca", 500), Key("yahoo.ca", 400)), other=(602, 919)),
            Key("net", 352, (), other=(216, 352)),
        ),
        other=(1, 289),
        masked=True,
    ),
    Declared(
        "RC-19/phones",
        "phone",
        (
            Key(
                "nanp",
                8_000,
                (
                    Key("514", 2_800),
                    Key("450", 1_600),
                    Key("418", 1_200),
                    Key("438", 1_200),
                    Key("819", 800),
                ),
                other=(16, 400),
            ),
            Key("fr", 2_000, (Key("06", 1_000), Key("01", 600), Key("04", 300)), other=(3, 100)),
        ),
        other=(0, 0),
        masked=True,
    ),
    Declared(
        "RC-20/postal_codes",
        "postal_code",
        (
            Key("H", 2_000, (Key("H2X", 200), Key("H3A", 120)), other=(60, 1_680)),
            Key("M", 1_800, (), other=(64, 1_800)),
            Key("G", 1_200, (Key("G1V", 180), Key("G1R", 96)), other=(42, 924)),
            Key("J", 1_000, (), other=(64, 1_000)),
            Key("K", 800, (), other=(64, 800)),
            Key("L", 800, (), other=(64, 800)),
            Key("V", 700, (), other=(64, 700)),
            Key("T", 500, (), other=(64, 500)),
            Key("E", 300, (), other=(64, 300)),
            Key("B", 250, (), other=(64, 250)),
            Key("R", 200, (), other=(64, 200)),
        ),
        other=(7, 450),
        masked=False,
    ),
)


def declared(field_id: str) -> Declared:
    for candidate in DECLARED:
        if candidate.field == field_id:
            return candidate
    raise KeyError(field_id)


def email_keys(value: str) -> tuple[str, str]:
    """The extension and the domain of an e-mail address."""
    domain = value.rsplit("@", 1)[1].lower()
    return domain.rsplit(".", 1)[1], domain


_PHONE = PhoneDetector({})


def phone_keys(value: str) -> tuple[str, str]:
    """The region of a number as the detector reads it, then its North American
    area code or its French zone (``06``)."""
    found = _PHONE.classify(value)
    if found is None or found.state != "matched" or found.value is None:
        raise ValueError(f"not a phone number: {value!r}")
    digits = "".join(char for char in value if char.isdigit())
    if found.value == "nanp":
        return "nanp", digits[-10:-7]
    national = digits[2:] if value.startswith("+33") else digits[1:]
    return "fr", "0" + national[0]


def postal_keys(value: str) -> tuple[str, str]:
    """The first letter and the forward sortation area of a Canadian code."""
    return value[0].upper(), value[:3].upper()
