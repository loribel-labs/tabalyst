# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Case ``examples/cases/sample-injected-errors``: what a smart sample keeps.

The case injects known errors in the insurance example; these tests state which
error classes a smart sample of 100 rows keeps, and which it is known to miss.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

CASE_FILE = (
    Path(__file__).resolve().parents[2]
    / "examples" / "cases" / "sample-injected-errors" / "case.py"
)


def _load_case() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sample_injected_errors_case", CASE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


case = _load_case()

KEPT = [
    "email_malformed",
    "phone_malformed",
    "postal_malformed",
    "birthdate_invalid",
    "premium_outlier",
    "id_trailing_space",
    "name_long_weird",
    "end_before_start",
    "novel_category_typo",
]
# Known gaps of the smart sample (no target for them yet). strict: the day one is
# closed, the test fails and the class moves to KEPT.
GAPS = ["missing_required", "duplicate_rows"]


@pytest.fixture(scope="module")
def smart_counts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, int]:
    output = tmp_path_factory.mktemp("case") / "sample.csv"
    case.run_sample("smart", 100, 1, output)
    return case.score(output)


def test_the_committed_input_is_the_deterministic_build() -> None:
    header, rows, classes = case.build()

    assert json.loads(case.TRUTH.read_text(encoding="utf-8")) == classes
    committed = case.DIRTY.read_text(encoding="utf-8").splitlines()
    assert len(committed) == len(rows) + 1
    assert committed[0] == ",".join(header)


@pytest.mark.parametrize("name", KEPT)
def test_smart_sample_keeps_a_row_of_each_detectable_error_class(
    smart_counts: dict[str, int], name: str
) -> None:
    assert smart_counts[name] > 0


@pytest.mark.parametrize("name", GAPS)
@pytest.mark.xfail(strict=True, reason="no smart target for this error class yet")
def test_smart_sample_misses_the_classes_without_a_target(
    smart_counts: dict[str, int], name: str
) -> None:
    assert smart_counts[name] > 0
