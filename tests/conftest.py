# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Plain, wide terminal output for every test.

Typer forces colors and a box at 80 columns when it sees GitHub Actions, which splits
the messages the tests look for. The variables are read when Typer is imported, so
they are set here, before any test module imports the CLI.
"""

import os

for name in ("GITHUB_ACTIONS", "FORCE_COLOR"):
    os.environ.pop(name, None)
os.environ["NO_COLOR"] = "1"
os.environ["TERMINAL_WIDTH"] = "200"


import pytest


def _set_sensitive_values_default(value: str) -> None:
    """Change the default of ``scan.exposure.sensitive_values`` and rebuild the models."""
    from tabalyst.scanner import config

    config.ExposureSettings.model_fields["sensitive_values"].default = value
    config.ExposureSettings.model_rebuild(force=True)
    config.ScanConfig.model_rebuild(force=True)


@pytest.fixture(autouse=True)
def _masked_by_default(request: pytest.FixtureRequest):
    """Run every test with the masking default.

    The shipped default is ``show`` (sensitive columns are off for now), but the
    masking and hiding machinery stays tested. A test of the shipped default or of
    the committed schemas carries the ``shipped_exposure_default`` marker.
    """
    if request.node.get_closest_marker("shipped_exposure_default"):
        yield
        return
    _set_sensitive_values_default("mask")
    try:
        yield
    finally:
        _set_sensitive_values_default("show")



