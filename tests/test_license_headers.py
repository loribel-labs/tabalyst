# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "license_headers.py"


def test_source_files_have_the_mpl_header():
    spec = importlib.util.spec_from_file_location("license_headers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [str(p) for p in module.missing()]
    assert not missing, (
        "Missing MPL-2.0 header (run python scripts/license_headers.py): "
        + ", ".join(missing)
    )
