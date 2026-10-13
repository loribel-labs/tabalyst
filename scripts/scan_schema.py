# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write or check the committed JSON Schemas of the Scan, Report, second-pass and smart sample
documents.

python scripts/scan_schema.py          # write src/tabalyst/schemas/
python scripts/scan_schema.py --check  # fail when a file is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tabalyst.report_schema import SCHEMA_FILE as REPORT_FILE
from tabalyst.report_schema import report_schema_text
from tabalyst.scanner.schema import SCHEMA_FILE as SCAN_FILE
from tabalyst.scanner.schema import scan_schema_text
from tabalyst.scanner.secondpass.schema import SCHEMA_FILE as DEEP_FILE
from tabalyst.scanner.secondpass.schema import deep_schema_text
from tabalyst.scanner.smart.result import SCHEMA_FILE as SAMPLE_FILE
from tabalyst.scanner.smart.result import sample_schema_text

DIRECTORY = ROOT / "src" / "tabalyst" / "schemas"
SCHEMAS = {
    SCAN_FILE: scan_schema_text,
    REPORT_FILE: report_schema_text,
    DEEP_FILE: deep_schema_text,
    SAMPLE_FILE: sample_schema_text,
}


def main(argv: list[str]) -> int:
    failed = False
    for name, generate in SCHEMAS.items():
        target = DIRECTORY / name
        text = generate()
        if "--check" in argv:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != text:
                print(f"{target} is out of date: run python scripts/scan_schema.py")
                failed = True
            continue
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {target}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
