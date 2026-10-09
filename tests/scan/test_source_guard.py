# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Checks before and after a second reading of the source (lot 6b, PASS2-01,
PASS2-06). The contract cases D04, D05 and D08 are in ``test_contract_planner``."""

from pathlib import Path

import pytest
from planner_helpers import scan_csv

from tabalyst.scanner.planner import plan_analyses
from tabalyst.source_guard import (
    SourceGuard,
    SourceNotReadable,
    StalePlan,
    StaleSource,
    check_plan_base,
    prepare_second_pass,
)


def _scanned(tmp_path):
    result = scan_csv(tmp_path, "code", [f"A{n:05d}" for n in range(300)])
    return result, plan_analyses(result), tmp_path / "data.csv"


def test_a_plan_belongs_to_the_scan_it_was_made_for(tmp_path):
    result, plan, _ = _scanned(tmp_path)

    check_plan_base(plan, result)


def test_a_stale_plan_names_what_differs(tmp_path):
    _, plan, _ = _scanned(tmp_path)
    (tmp_path / "other").mkdir()
    other = scan_csv(tmp_path / "other", "code", [f"B{n:05d}" for n in range(300)])

    with pytest.raises(StalePlan) as error:
        check_plan_base(plan, other)

    assert "source_sha256" in str(error.value)
    assert "facts_sha256" in str(error.value)
    assert "engine_version" not in str(error.value)


def test_the_source_as_scanned_is_ready_and_its_digest_closes_the_pass(tmp_path):
    result, plan, source = _scanned(tmp_path)

    guard = prepare_second_pass(plan, result, source)
    guard.finish(result.source.sha256, result.source.size_bytes)

    assert isinstance(guard, SourceGuard) and guard.path == source


def test_a_digest_or_a_size_that_differs_discards_the_pass(tmp_path):
    result, _, source = _scanned(tmp_path)
    guard = SourceGuard(source, result.source)

    with pytest.raises(StaleSource, match="data.csv"):
        guard.finish("0" * 64, result.source.size_bytes)
    with pytest.raises(StaleSource):
        guard.finish(result.source.sha256, result.source.size_bytes - 1)


def test_a_source_that_cannot_be_opened_is_not_readable_and_not_stale(tmp_path, monkeypatch):
    result, _, source = _scanned(tmp_path)
    real_open = Path.open

    def deny(self, *args, **kwargs):
        if self == source:
            raise PermissionError("access denied")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny)

    with pytest.raises(SourceNotReadable, match="access denied"):
        SourceGuard(source, result.source).before()


def test_a_missing_source_names_the_way_out_and_creates_nothing(tmp_path):
    result, plan, source = _scanned(tmp_path)
    source.unlink()
    before = sorted(tmp_path.iterdir())

    with pytest.raises(SourceNotReadable) as error:
        prepare_second_pass(plan, result, source)

    assert "temporary file" in str(error.value)
    assert "scan a readable copy" in str(error.value)
    assert sorted(tmp_path.iterdir()) == before
