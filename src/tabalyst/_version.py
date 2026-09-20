"""Resolve the application version from its single packaging source of truth."""

import tomllib
from importlib.metadata import Distribution, PackageNotFoundError, version
from pathlib import Path


def get_version() -> str:
    """Return source metadata in a checkout and installed metadata elsewhere."""
    project_file = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if project_file.is_file():
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        return str(project["project"]["version"])
    package_root = Path(__file__).resolve().parent.parent
    for metadata_dir in package_root.glob("tabalyst-*.dist-info"):
        return Distribution.at(metadata_dir).version
    try:
        return version("tabalyst")
    except PackageNotFoundError:
        return "unknown"


__version__ = get_version()
