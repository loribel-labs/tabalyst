# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Effective, validated options of one Dedup run (design dedup 10)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from tabalyst.config import (
    DEDUP_DEFAULT_MAX_ROWS,
    DEDUP_DEFAULT_MEMORY_BUDGET_MB,
    CsvConfig,
    resolve_config,
)
from tabalyst.errors import ConfigurationError
from tabalyst.service import ConfigPath, _config_paths

DEFAULT_MAX_ROWS = DEDUP_DEFAULT_MAX_ROWS
DEFAULT_MEMORY_BUDGET_MB = DEDUP_DEFAULT_MEMORY_BUDGET_MB


def require_positive_int(name: str, value: object) -> None:
    """Raise ``ConfigurationError`` unless ``value`` is an integer of at least 1."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigurationError(
            f"{name} must be an integer of at least 1, not {value!r}."
        )


@dataclass(frozen=True)
class DedupSettings:
    """Options of a run, checked once so that no option is silently ignored.

    Raises ``ConfigurationError`` on construction for a value below its minimum, a
    ``--quiet`` with ``--verbose`` and a ``--force`` with ``--verify-content``
    (a forced run always reprocesses, so the verification would decide nothing).
    ``temp_dir`` is only checked here for not being a file: whether it is usable
    is known when the store needs it.
    """

    csv: CsvConfig = field(default_factory=CsvConfig)
    max_rows: int = DEFAULT_MAX_ROWS
    memory_budget_mb: int = DEFAULT_MEMORY_BUDGET_MB
    temp_dir: Path | None = None
    output_dir: Path | None = None
    force: bool = False
    verify_content: bool = False
    quiet: bool = False
    verbose: bool = False

    def __post_init__(self) -> None:
        for name in ("max_rows", "memory_budget_mb"):
            require_positive_int(name, getattr(self, name))
        for name in ("temp_dir", "output_dir"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(os.fspath(value)))
        if self.temp_dir is not None and self.temp_dir.is_file():
            raise ConfigurationError(
                f"--temp-dir is a file, not a directory: {self.temp_dir}"
            )
        if self.quiet and self.verbose:
            raise ConfigurationError("--quiet and --verbose cannot be used together.")
        if self.force and self.verify_content:
            raise ConfigurationError(
                "--force and --verify-content cannot be used together: a forced "
                "run reprocesses every source, so there is nothing to verify."
            )


def resolve_dedup_settings(
    config_path: ConfigPath | None = None,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    max_rows: int | None = None,
    memory_budget_mb: int | None = None,
    temp_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
    verify_content: bool = False,
    quiet: bool = False,
    verbose: bool = False,
) -> DedupSettings:
    """Combine the command line, the configuration files and the defaults.

    An option that is given wins over the configuration, which wins over the
    default. ``verify_content_on_skip`` can only turn the verification on, and a
    forced run does not take it from the configuration (it has nothing to verify);
    an explicit ``verify_content`` with ``force`` is still refused.
    """
    settings = resolve_config(
        _config_paths(config_path), separator=delimiter, encoding=encoding
    )
    configured = settings.dedup
    return DedupSettings(
        csv=settings.csv,
        max_rows=configured.max_rows if max_rows is None else max_rows,
        memory_budget_mb=(
            configured.memory_budget_mb
            if memory_budget_mb is None
            else memory_budget_mb
        ),
        temp_dir=Path(temp_dir) if temp_dir is not None else None,
        output_dir=Path(output_dir) if output_dir is not None else None,
        force=force,
        verify_content=verify_content
        or (configured.verify_content_on_skip and not force),
        quiet=quiet,
        verbose=verbose,
    )
