"""Persistent performance history for successful CLI analyses."""

import json
import subprocess
import tomllib
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from tabalyst.models import DatasetProfile

EXECUTION_LOG_NAME = "execution.json"
EXECUTION_SCHEMA_VERSION = "1.0"


def tabalyst_version() -> str:
    """Return source metadata in a clone and installed metadata elsewhere."""
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if project_file.is_file():
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        return str(project["project"]["version"])
    try:
        return version("tabalyst")
    except PackageNotFoundError:
        return "unknown"


def git_state(directory: Path) -> dict[str, Any]:
    """Describe the current checkout without requiring Git in production."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "commit": None, "dirty": None, "state": None}
    suffix = "+working" if dirty else ""
    return {
        "available": True,
        "commit": commit,
        "dirty": dirty,
        "state": f"{commit[:8]}{suffix}",
    }


def build_execution_entry(
    *,
    source: Path,
    html_output: Path,
    json_output: Path,
    profile: DatasetProfile,
    total_seconds: float,
    git_directory: Path,
) -> dict[str, Any]:
    """Build one portable history item using names relative to its output folder."""
    return {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "tabalyst_version": tabalyst_version(),
        "source_file": source.name,
        "html_file": html_output.name,
        "json_file": json_output.name,
        "rows": profile.summary.row_count,
        "columns": profile.summary.column_count,
        "analysis_seconds": profile.processing_seconds,
        "total_seconds": round(total_seconds, 4),
        "git": git_state(git_directory),
    }


def append_execution(path: Path, entry: dict[str, Any]) -> None:
    """Append an item and atomically replace the JSON history file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        history = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(history, dict) or not isinstance(
            history.get("executions"), list
        ):
            raise ValueError(f"Invalid execution history: {path}")
        if history.get("schema_version") != EXECUTION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported execution history schema: {path}"
            )
    else:
        history = {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "executions": [],
        }
    history["executions"].append(entry)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)
