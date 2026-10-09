# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Keep the contract tests of the Scan and JSON work complete and gated.

An expected failure hides a test that was never written or never activated.
This index fails when a required test identifier (specification section 22)
has no test, when a test has no lot, or when a lot name is unknown.
"""

import ast
import re
from pathlib import Path

from scan_json_gate import ENABLED_LOTS, KNOWN_LOTS

HERE = Path(__file__).parent
FILES = (
    "test_contract_scan_json.py",
    "test_contract_bottomk.py",
    "test_report_document.py",
    "test_contract_rowsample.py",
    "test_contract_patterns.py",
    "test_contract_quality.py",
    "test_contract_html.py",
    "test_contract_planner.py",
    "test_contract_second_pass.py",
    "test_contract_exact_distinct.py",
)
REQUIRED = [f"A0{n}" for n in range(1, 7)] + ["A10", "A11", "A14", "A18"] + [f"B{n:02d}" for n in range(1, 14)] + [f"C0{n}" for n in range(1, 10)] + ["C10", "A07", "A12", "A15", "D01", "D02", "D03", "D04", "D05", "D06", "D07", "D08", "D09", "D10", "D11", "D13", "F01", "F02", "F03", "F04", "F06"]


def _declared() -> dict[str, list[str | None]]:
    """Test identifier to the lots of its tests (None when a test has none)."""
    found: dict[str, list[str | None]] = {}
    for name in FILES:
        for node in ast.parse((HERE / name).read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            match = re.match(r"test_([A-F]\d\d)_", node.name)
            if match is None:
                continue
            lot = None
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "scan_json_lot"
                ):
                    lot = decorator.args[0].value
            found.setdefault(match.group(1), []).append(lot)
    return found


def test_every_required_identifier_has_a_test():
    assert sorted(set(REQUIRED) - set(_declared())) == []


def test_every_contract_test_names_a_known_lot():
    for identifier, lots in _declared().items():
        for lot in lots:
            assert lot in KNOWN_LOTS, f"{identifier} has the lot {lot!r}"


def test_only_known_lots_are_enabled():
    assert ENABLED_LOTS <= KNOWN_LOTS
