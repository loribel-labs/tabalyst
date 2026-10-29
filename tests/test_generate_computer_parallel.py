# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check that Computer rows rendered by worker processes match those of one process."""

import shutil
import sys
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError, ReportError
from tabalyst.generate_computer_parallel import (
    MAX_WORKERS,
    MIN_PARALLEL_ROWS,
    span_size,
    worker_count,
)
from tabalyst.generate_service import (
    GenerateProgress,
    build_generate_plan,
    generate_datasets,
)

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))


def test_workers_give_the_same_files_as_one_process(tmp_path: Path) -> None:
    """Every artifact, errors included, is byte for byte the same for 1 or 3 workers."""
    for workers in (1, 3):
        generate_datasets(build_generate_plan(
            PACKAGE, output_dir=tmp_path / f"w{workers}", rows=3500, seed=11,
            output_profile="standard", anomaly_profile="dirty_realistic", workers=workers,
        ))
    names = sorted(path.name for path in (tmp_path / "w1").iterdir())
    assert len(names) == 9
    for name in names:
        assert (tmp_path / "w1" / name).read_bytes() == (tmp_path / "w3" / name).read_bytes(), name


def test_workers_report_ordered_progress_and_leave_no_part_files(tmp_path: Path) -> None:
    """Progress ends at the total and the temporary parts are gone afterwards."""
    events: list[GenerateProgress] = []
    result = generate_datasets(
        build_generate_plan(PACKAGE, output=tmp_path / "pcs.csv", rows=3000, workers=2),
        on_progress=events.append,
    )
    done = [event.done for event in events if event.stage == "Generating rows"]
    assert done == sorted(done) and done[0] == 0 and done[-1] == 3000
    assert result.workers == 2
    assert [path.name for path in tmp_path.iterdir()] == ["pcs.csv"]


def test_a_worker_that_cannot_start_stops_the_run_and_leaves_nothing(tmp_path: Path) -> None:
    """A broken package fails with a Generate worker message, with no partial output."""
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    plan = build_generate_plan(package, output=tmp_path / "out" / "pcs.csv", rows=3000, workers=2)
    (package / "dataset.yaml").unlink()
    with pytest.raises(ReportError, match="Generate worker"):
        generate_datasets(plan)
    assert not (tmp_path / "out").exists() or list((tmp_path / "out").iterdir()) == []


@pytest.mark.parametrize(("requested", "rows", "cpus", "expected"), [
    (None, MIN_PARALLEL_ROWS - 1, 8, 1),
    (None, MIN_PARALLEL_ROWS, 8, min(7, MAX_WORKERS)),
    (None, 1_000_000, 4, 3),
    (None, 1_000_000, 64, MAX_WORKERS),
    (None, 1_000_000, 1, 1),
    (1, 1_000_000, 8, 1),
    (5, 10, 2, 5),
])
def test_worker_count_follows_rows_and_processors(
    monkeypatch: pytest.MonkeyPatch, requested: int | None, rows: int, cpus: int, expected: int,
) -> None:
    """A request wins; otherwise one worker per spare processor, from a minimum of rows."""
    monkeypatch.setattr("os.cpu_count", lambda: cpus)
    assert worker_count(requested, rows) == expected


def test_a_frozen_program_renders_in_one_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Workers need a Python interpreter to start, which a frozen program lacks."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert worker_count(4, 1_000_000) == 1


def test_spans_scale_with_rows_and_workers() -> None:
    """Spans stay between 1,000 and 25,000 rows, about eight per worker."""
    assert span_size(3_000, 2) == 1_000
    assert span_size(1_000_000, 3) == 25_000
    assert span_size(80_000, 5) == 2_000


def test_workers_must_be_a_positive_integer_and_only_apply_to_computer(tmp_path: Path) -> None:
    """Bad values and other packages are refused before anything is written."""
    with pytest.raises(ConfigurationError, match="--workers must be an integer of 1 or more"):
        build_generate_plan(PACKAGE, output=tmp_path / "x.csv", workers=0)
    with pytest.raises(ConfigurationError, match="Computer package only"):
        build_generate_plan(example="crm", output=tmp_path / "x.csv", workers=2)
    assert CliRunner().invoke(app, ["generate", "--example", "computer", "-o",
                                    str(tmp_path / "x.csv"), "--workers", "0"]).exit_code == 2


def test_cli_names_the_processes_in_the_closing_line(tmp_path: Path) -> None:
    """With several workers, the report says how many processes made the rows."""
    result = CliRunner().invoke(app, ["generate", "--example", "computer", "-o",
                                      str(tmp_path / "pcs.csv"), "--rows", "2500",
                                      "--workers", "2"])
    assert result.exit_code == 0, result.output
    assert "rows/s, 2 processes)" in result.output.strip().splitlines()[-1]
