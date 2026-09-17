from pathlib import Path

from tabalyst.analysis import analyze_dataset
from tabalyst.config import AnalysisConfig
from tabalyst.ingestion import read_csv
from tabalyst.models import DatasetProfile


def analyze_csv(
    path: str | Path, config: AnalysisConfig | None = None
) -> DatasetProfile:
    config = config or AnalysisConfig()
    return analyze_dataset(read_csv(Path(path), config.csv), config)
