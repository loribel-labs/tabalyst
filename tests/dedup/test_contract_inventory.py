# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The contract tests cover T01 to T30 and every lot of the design.

This test never skips: it reads the other test files with ``ast`` (so it also works
for a partial selection of tests) and the design document.
"""

import ast
import re
from pathlib import Path

HERE = Path(__file__).parent
DESIGN = Path(__file__).parents[2] / "docs" / "dev" / "dedup" / "design.md"
EXPECTED = {f"T{number:02d}" for number in range(1, 31)}
DASH = chr(0x2014)  # the typography rule of the project: no em dash
LOTS = {str(number) for number in range(1, 12)}


def _marks() -> tuple[set[str], set[str]]:
    """The requirement ids and the lots named by the markers of the contract tests."""
    requirements: set[str] = set()
    lots: set[str] = set()
    for path in sorted(HERE.glob("test_contract_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                    continue
                values = {
                    arg.value
                    for arg in decorator.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                }
                if decorator.func.attr == "dedup_t":
                    requirements |= values
                elif decorator.func.attr == "dedup_lot":
                    lots |= values
    return requirements, lots


def test_every_requirement_test_of_the_specification_has_a_contract_test():
    requirements, _ = _marks()
    assert EXPECTED <= requirements


def test_every_lot_marker_names_a_lot_of_the_plan():
    _, lots = _marks()
    assert lots <= LOTS
    assert {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"} <= lots


def test_the_design_lists_every_requirement_test_and_every_lot_in_its_matrix():
    text = DESIGN.read_text(encoding="utf-8")
    for requirement in sorted(EXPECTED):
        assert re.search(rf"^\| {requirement} \|", text, re.MULTILINE), requirement
    assert "ENABLED_LOTS" in text


def test_the_design_contains_no_em_dash():
    assert DASH not in DESIGN.read_text(encoding="utf-8")
    adr = DESIGN.parents[1] / "adr"
    for path in [*HERE.glob("*.py"), *adr.glob("2026-10-22-dedup-*.md")]:
        assert DASH not in path.read_text(encoding="utf-8"), path.name
