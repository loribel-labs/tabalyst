# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second pass: a targeted reading of the source that adds analyses to a
finished Scan (design 20)."""

from tabalyst.scanner.secondpass.document import (
    analysis_key,
    deep_document,
    deep_path_for,
    load_deep,
)
from tabalyst.scanner.secondpass.executor import (
    EXECUTABLE,
    SecondPassOutcome,
    pending_candidates,
    run_second_pass,
)
from tabalyst.scanner.secondpass.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    AnalysisResult,
    DeepResult,
)

__all__ = [
    "EXECUTABLE",
    "FORMAT",
    "FORMAT_REVISION",
    "FORMAT_VERSION",
    "AnalysisResult",
    "DeepResult",
    "SecondPassOutcome",
    "analysis_key",
    "deep_document",
    "deep_path_for",
    "load_deep",
    "pending_candidates",
    "run_second_pass",
]
