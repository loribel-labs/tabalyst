# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The tree of content nodes under the patterns of a Scan (Patterns lot P4, design
18.12): nodes, tables of content, the 3-character cap of folded constants, the depth
and the checks of ``check_scan`` on the hierarchy."""

from __future__ import annotations

import random
import string
from collections.abc import Iterator
from pathlib import Path

import pytest
from scan_helpers import write_text

from tabalyst.report_labels import MEASURE_REASON_SETTINGS
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import FieldPatternsComplete, PatternNode, ScanResult
from tabalyst.scanner.patterninfer import compile_signature, matches
from tabalyst.scanner.validation import check_scan


def _scan(tmp_path: Path, rows: list[str], **settings) -> ScanResult:
    source = write_text(tmp_path, "data.csv", "code\n" + "\n".join(rows) + "\n")
    return scan(source, config=ScanConfig.model_validate({"pattern_inference": settings}))


def _entry(result: ScanResult) -> FieldPatternsComplete:
    assert result.derived is not None and result.derived.patterns is not None
    [entry] = result.derived.patterns.fields
    assert isinstance(entry, FieldPatternsComplete)
    return entry


def _walk(nodes: list[PatternNode]) -> Iterator[PatternNode]:
    for node in nodes:
        yield node
        yield from _walk(node.nodes)


def _rows_with_prefixes(seed: str = "tree") -> list[str]:
    """600 identifiers: three prefixes of 200 with a random 4-digit number."""
    rng = random.Random(seed)
    rows: set[str] = set()
    for prefix in ("AK", "BC", "DE"):
        count = 0
        while count < 200:
            row = f"{prefix}-{rng.randrange(10**4):04d}"
            if row not in rows:
                rows.add(row)
                count += 1
    return sorted(rows)


def test_nodes_of_a_facet_publish_their_signature_gain_and_a_matching_set(tmp_path):
    result = _scan(tmp_path, _rows_with_prefixes())
    entry = _entry(result)
    [family] = entry.families
    [pattern] = family.patterns
    assert [node.render for node in pattern.nodes] == ["'AK-'9999", "'BC-'9999", "'DE-'9999"]
    values = {"AK": 0, "BC": 0, "DE": 0}
    for row in _rows_with_prefixes():
        values[row[:2]] += 1
    for node in pattern.nodes:
        assert node.facet == "head:1" and node.level == 2 and node.gain is not None
        assert node.gain.bits_d > 0 and 0.1 <= node.gain.sigma <= 1
        matcher = compile_signature(node.signature)
        assert sum(matches(matcher, row) for row in _rows_with_prefixes()) == node.d == 200
    assert [node.role for node in pattern.nodes] == ["principal", "secondary", "secondary"]
    assert check_scan(result) == []


def test_a_uniform_column_publishes_no_node_and_no_table(tmp_path):
    rng = random.Random("uniform")
    rows = sorted({f"{''.join(rng.choices(string.ascii_uppercase, k=2))}-{rng.randrange(10**4):04d}" for _ in range(900)})
    entry = _entry(_scan(tmp_path, rows))
    [family] = entry.families
    assert all(pattern.nodes == [] for pattern in family.patterns)
    assert family.tables == []


def test_a_constant_folded_into_a_pattern_stays_within_three_characters(tmp_path):
    # Card-like numbers that all start with the same ten digits: a pattern may not
    # publish the start of a number (exposure, RC-11).
    cards = [f"4532015112{n:03d}" for n in range(0, 600, 7)]
    entry = _entry(_scan(tmp_path, cards))
    [pattern] = entry.families[0].patterns
    assert pattern.render == "'453'9{10}"
    assert not any(cards[0][:4] in node.render for node in _walk(pattern.nodes))


def test_a_facet_independent_of_the_nodes_is_a_table_of_the_family(tmp_path):
    rng = random.Random("table")
    rows = set()
    while len(rows) < 800:
        prefix = rng.choice(("INV", "ORD"))
        year = rng.choice(("2025", "2026"))
        rows.add(f"{prefix}-{year}-{rng.randrange(10**6):06d}")
    entry = _entry(_scan(tmp_path, sorted(rows)))
    [family] = entry.families
    [pattern] = family.patterns
    assert {node.facet for node in pattern.nodes} == {"head:1"}
    [table] = family.tables
    assert table.facet == "token:3" and table.gain is not None
    assert sorted(cell.value for cell in table.cells) == ["2025", "2026"]
    assert sum(cell.d for cell in table.cells) + table.others.d == family.d


def test_a_facet_that_depends_on_a_node_is_nested_below_it(tmp_path):
    rng = random.Random("nested")
    rows = set()
    while len(rows) < 800:
        prefix = rng.choice(("INV", "ORD"))
        same = rng.random() < 0.8
        year = ("2025" if prefix == "INV" else "2026") if same else ("2026" if prefix == "INV" else "2025")
        rows.add(f"{prefix}-{year}-{rng.randrange(10**6):06d}")
    result = _scan(tmp_path, sorted(rows))
    entry = _entry(result)
    [family] = entry.families
    [pattern] = family.patterns
    assert len(pattern.nodes) == 2
    for node in pattern.nodes:
        assert [child.facet for child in node.nodes] == ["token:3", "token:3"]
        assert all(child.level == 3 and child.id.startswith(node.id + ".") for child in node.nodes)
    assert family.tables == []
    assert check_scan(result) == []


def test_the_depth_setting_cuts_the_tree_and_says_so(tmp_path):
    rows = _rows_with_prefixes()
    full = _entry(_scan(tmp_path, rows))
    assert full.limits == []
    (tmp_path / "shallow").mkdir()
    shallow = _entry(_scan(tmp_path / "shallow", rows, max_depth=1))
    assert shallow.limits == ["max_depth"]
    assert all(pattern.nodes == [] for family in shallow.families for pattern in family.patterns)


def test_the_depth_is_a_setting_between_one_and_four():
    ScanConfig.model_validate({"pattern_inference": {"max_depth": 4}})
    for depth in (0, 5):
        with pytest.raises(ValueError, match="max_depth"):
            ScanConfig.model_validate({"pattern_inference": {"max_depth": depth}})


def test_the_depth_limit_of_the_patterns_has_its_own_setting_in_the_report():
    # `max_depth` also names the limit of the JSON structure: the measure tells which.
    assert MEASURE_REASON_SETTINGS[("derived.patterns", "max_depth")] == (
        "scan.pattern_inference.max_depth"
    )


def test_the_budget_removes_the_nodes_of_the_lowest_gain_first(tmp_path):
    result = _scan(tmp_path, _rows_with_prefixes(), max_patterns=3)
    entry = _entry(result)
    [pattern] = entry.families[0].patterns
    assert entry.limits == ["max_patterns"]
    assert 1 + sum(1 for _ in _walk(pattern.nodes)) <= 3
    assert len(pattern.nodes) == 2
    assert check_scan(result) == []


def _damaged(tmp_path, mutate) -> list[str]:
    result = _scan(tmp_path, _rows_with_prefixes())
    document = result.model_dump(mode="json")
    mutate(document["derived"]["patterns"]["fields"][0]["families"][0])
    return check_scan(ScanResult.model_validate(document))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda f: f["patterns"][0]["nodes"][0].update(d=500), "part of their parent"),
        (lambda f: f["patterns"][0]["nodes"][0].update(id="f1.p1.n9"), "node id or parent"),
        (lambda f: f["patterns"][0]["nodes"][0].update(level=3), "level must be 2"),
        (lambda f: f["patterns"][0]["nodes"][0].update(facet="composition"), "facet"),
        (lambda f: f["patterns"][0]["nodes"][0].pop("gain"), "gain"),
        (lambda f: f["patterns"][0]["nodes"][0].update(render="9"), "render"),
        (
            lambda f: f["patterns"][0]["nodes"][1].update(role="principal"),
            "only the first node is principal",
        ),
        (lambda f: f["patterns"][0]["nodes"][0].update(value=""), "value must be the text"),
        (
            lambda f: f["patterns"][0]["nodes"][0].update(also=[{"facet": "nope", "value": "x"}]),
            "also must list",
        ),
        (
            lambda f: f["patterns"][0]["nodes"][1].update(value=f["patterns"][0]["nodes"][0]["value"]),
            "a sibling fixes the same text",
        ),
        (lambda f: f["patterns"][0]["nodes"][0].update(d=199), "signature does not accept d"),
        (lambda f: f["patterns"][0].update(d=601), "signature does not accept d"),
    ],
    ids=["sum", "id", "level", "facet", "gain", "render", "role", "value", "also", "twin", "node-d", "pattern-d"],
)
def test_check_scan_catches_a_hierarchy_that_does_not_reconcile(tmp_path, mutate, message):
    problems = _damaged(tmp_path, mutate)
    assert any(message in problem for problem in problems), problems


def test_check_scan_catches_a_table_of_content_that_does_not_add_up(tmp_path):
    rng = random.Random("table")
    rows = set()
    while len(rows) < 800:
        rows.add(
            f"{rng.choice(('INV', 'ORD'))}-{rng.choice(('2025', '2026'))}-{rng.randrange(10**6):06d}"
        )
    result = _scan(tmp_path, sorted(rows))
    document = result.model_dump(mode="json")
    family = document["derived"]["patterns"]["fields"][0]["families"][0]
    family["tables"][0]["cells"][0]["d"] += 1
    assert any("cells and others must add up" in p for p in check_scan(ScanResult.model_validate(document)))


def test_the_tree_does_not_depend_on_the_order_of_the_rows(tmp_path):
    rows = _rows_with_prefixes()
    shuffled = rows[:]
    random.Random("order").shuffle(shuffled)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = _entry(_scan(tmp_path / "a", rows))
    second = _entry(_scan(tmp_path / "b", shuffled))
    assert first.model_dump_json() == second.model_dump_json()


def _merged_rows(after: bool, seed: str = "merged") -> list[str]:
    """Numbers of five digits or of four and a capital, 80 % of the INV ones the
    first and 80 % of the ORD ones the second: the prefix depends on the structure."""
    rng = random.Random(seed)
    rows: set[str] = set()
    while len(rows) < 1000:
        prefix = rng.choice(("INV", "ORD"))
        lettered = (rng.random() < 0.8) == (prefix == "ORD")
        # Five digits, or four and a capital: the block has one length in both.
        number = f"{rng.randrange(10**4):04d}X" if lettered else f"{rng.randrange(10**5):05d}"
        rows.add(f"{number}-{prefix}" if after else f"{prefix}-{number}")
    return sorted(rows)


@pytest.mark.parametrize("after", [False, True], ids=["before_block", "after_block"])
def test_a_facet_that_depends_on_a_merged_structure_is_nested_below_its_node(tmp_path, after):
    rows = _merged_rows(after)
    result = _scan(tmp_path, rows)
    entry = _entry(result)
    [family] = entry.families
    [pattern] = family.patterns
    assert [node.facet for node in pattern.nodes] == ["composition", "composition"]
    for node in pattern.nodes:
        assert len(node.nodes) == 2
        assert {child.facet for child in node.nodes} == {"head:3" if after else "head:1"}
        matcher = compile_signature(node.signature)
        inside = [row for row in rows if matches(matcher, row)]
        assert len(inside) == node.d
        for child in node.nodes:
            child_matcher = compile_signature(child.signature)
            held = [row for row in inside if matches(child_matcher, row)]
            assert len(held) == child.d
            assert len({row[-3:] if after else row[:3] for row in held}) == 1
    assert check_scan(result) == []


def test_a_facet_the_depth_cut_is_not_published_as_a_table(tmp_path):
    entry = _entry(_scan(tmp_path, _rows_with_prefixes(), max_depth=1))
    assert entry.limits == ["max_depth"]
    assert all(family.tables == [] for family in entry.families)


def test_a_tail_that_meets_the_folded_start_is_written_with_the_whole_token():
    from tabalyst.scanner.patterninfer import _signature_of, render_signature

    template = [("D", None, 3, "123")]
    # Folded start "12" and tail "23" overlap on one character: the token is 123.
    signature = _signature_of(template, [2], {0: ("tail", "23")})
    assert render_signature(signature) == "'123'"
    separate = _signature_of([("D", None, 6, "123456")], [2], {0: ("tail", "56")})
    assert render_signature(separate) == "'12'99'56'"
