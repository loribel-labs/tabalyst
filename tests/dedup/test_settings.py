# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Options and configuration of a Dedup run (design dedup 10, D13, DD-15)."""

import json
from pathlib import Path

import pytest

from tabalyst.dedup.settings import (
    DEFAULT_MAX_ROWS,
    DEFAULT_MEMORY_BUDGET_MB,
    DedupSettings,
    resolve_dedup_settings,
)
from tabalyst.errors import ConfigurationError


def _config(tmp_path: Path, document: dict, name: str = "tabalyst.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.dedup_lot("1")
def test_defaults_are_the_limits_of_the_specification():
    settings = DedupSettings()
    assert settings.max_rows == DEFAULT_MAX_ROWS == 10_000_000
    assert settings.memory_budget_mb == DEFAULT_MEMORY_BUDGET_MB == 512
    assert (settings.force, settings.verify_content) == (False, False)
    assert settings.temp_dir is None and settings.output_dir is None
    assert (settings.csv.delimiter, settings.csv.encoding) == (",", "utf-8-sig")


@pytest.mark.dedup_lot("1")
@pytest.mark.parametrize("name", ["max_rows", "memory_budget_mb"])
@pytest.mark.parametrize("value", [0, -5, True, 1.5, "10"])
def test_a_limit_below_one_or_not_an_integer_is_refused(name, value):
    with pytest.raises(ConfigurationError, match=name):
        DedupSettings(**{name: value})


@pytest.mark.dedup_lot("1")
def test_the_smallest_limits_are_accepted():
    settings = DedupSettings(max_rows=1, memory_budget_mb=1)
    assert (settings.max_rows, settings.memory_budget_mb) == (1, 1)


@pytest.mark.dedup_lot("1")
def test_quiet_and_verbose_together_are_refused():
    with pytest.raises(ConfigurationError, match="quiet"):
        DedupSettings(quiet=True, verbose=True)
    assert DedupSettings(quiet=True).quiet
    assert DedupSettings(verbose=True).verbose


@pytest.mark.dedup_lot("1")
def test_force_with_verify_content_is_refused():
    with pytest.raises(ConfigurationError, match="force"):
        DedupSettings(force=True, verify_content=True)


@pytest.mark.dedup_lot("1")
def test_paths_are_stored_as_paths_and_a_temp_dir_that_is_a_file_is_refused(tmp_path):
    settings = DedupSettings(temp_dir=str(tmp_path), output_dir=str(tmp_path / "out"))
    assert settings.temp_dir == tmp_path
    assert settings.output_dir == tmp_path / "out"
    stray = tmp_path / "file.txt"
    stray.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="temp-dir"):
        DedupSettings(temp_dir=stray)
    # A folder that does not exist yet is the store's business, when it needs it.
    assert DedupSettings(temp_dir=tmp_path / "later").temp_dir == tmp_path / "later"


@pytest.mark.dedup_lot("1")
def test_the_resolved_settings_without_a_file_or_option_are_the_defaults():
    assert resolve_dedup_settings() == DedupSettings()


@pytest.mark.dedup_lot("1")
def test_a_configuration_file_sets_the_dedup_and_csv_options(tmp_path):
    path = _config(
        tmp_path,
        {
            "csv": {"delimiter": ";", "encoding": "latin-1"},
            "dedup": {
                "max_rows": 50,
                "memory_budget_mb": 8,
                "verify_content_on_skip": True,
            },
        },
    )
    settings = resolve_dedup_settings(path)
    assert (settings.max_rows, settings.memory_budget_mb) == (50, 8)
    assert (settings.csv.delimiter, settings.csv.encoding) == (";", "latin-1")
    assert settings.verify_content is True


@pytest.mark.dedup_lot("1")
def test_the_command_line_wins_over_the_configuration(tmp_path):
    path = _config(
        tmp_path,
        {"csv": {"delimiter": ";"}, "dedup": {"max_rows": 50, "memory_budget_mb": 8}},
    )
    settings = resolve_dedup_settings(
        path, delimiter="|", encoding="utf-8", max_rows=7, memory_budget_mb=3
    )
    assert (settings.max_rows, settings.memory_budget_mb) == (7, 3)
    assert (settings.csv.delimiter, settings.csv.encoding) == ("|", "utf-8")


@pytest.mark.dedup_lot("1")
def test_a_later_configuration_file_overrides_an_earlier_one(tmp_path):
    first = _config(tmp_path, {"dedup": {"max_rows": 50, "memory_budget_mb": 8}}, "a.json")
    second = _config(tmp_path, {"dedup": {"max_rows": 60}}, "b.json")
    settings = resolve_dedup_settings([first, second])
    assert (settings.max_rows, settings.memory_budget_mb) == (60, 8)


@pytest.mark.dedup_lot("1")
def test_the_verification_of_the_configuration_cannot_be_turned_off_by_a_flag(tmp_path):
    path = _config(tmp_path, {"dedup": {"verify_content_on_skip": True}})
    assert resolve_dedup_settings(path).verify_content is True
    assert resolve_dedup_settings(path, verify_content=False).verify_content is True


@pytest.mark.dedup_lot("1")
def test_a_forced_run_ignores_the_configured_verification_but_not_a_flag(tmp_path):
    path = _config(tmp_path, {"dedup": {"verify_content_on_skip": True}})
    forced = resolve_dedup_settings(path, force=True)
    assert (forced.force, forced.verify_content) == (True, False)
    with pytest.raises(ConfigurationError):
        resolve_dedup_settings(path, force=True, verify_content=True)


@pytest.mark.dedup_lot("1")
@pytest.mark.parametrize(
    "document",
    [
        {"dedup": {"unknown": 1}},
        {"dedup": {"max_rows": 0}},
        {"dedup": {"memory_budget_mb": 0}},
        {"dedup": {"verify_content_on_skip": "maybe"}},
        {"dedup": 3},
        {"csv": {"delimiter": "ab"}},
    ],
)
def test_an_invalid_configuration_is_a_configuration_error(tmp_path, document):
    with pytest.raises(ConfigurationError):
        resolve_dedup_settings(_config(tmp_path, document))


@pytest.mark.dedup_lot("1")
def test_an_invalid_delimiter_option_and_a_missing_file_are_configuration_errors(
    tmp_path,
):
    with pytest.raises(ConfigurationError):
        resolve_dedup_settings(delimiter="ab")
    with pytest.raises(ConfigurationError):
        resolve_dedup_settings(tmp_path / "missing.json")


@pytest.mark.dedup_lot("1")
def test_the_dedup_block_does_not_change_the_other_commands(tmp_path):
    from tabalyst.config import load_config

    settings = load_config([_config(tmp_path, {"csv": {"delimiter": ";"}})])
    assert settings.dedup.max_rows == DEFAULT_MAX_ROWS
    assert settings.csv.delimiter == ";"
