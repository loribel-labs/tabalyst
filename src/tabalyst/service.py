"""Small public service boundary shared by the CLI and future HTTP API."""

from pathlib import Path

from tabalyst.analysis import analyze_dataset
from tabalyst.config import AnalysisConfig
from tabalyst.ingestion import read_csv
from tabalyst.models import DatasetProfile


def analyze_csv(
    path: str | Path, config: AnalysisConfig | None = None
) -> DatasetProfile:
    """Read and analyze one CSV without coupling callers to the CLI."""
    config = config or AnalysisConfig()
    return analyze_dataset(read_csv(Path(path), config.csv), config)
