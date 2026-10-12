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
