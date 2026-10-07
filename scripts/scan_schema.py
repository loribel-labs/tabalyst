# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Write or check the committed JSON Schema of the Scan document.

python scripts/scan_schema.py          # write src/tabalyst/schemas/
python scripts/scan_schema.py --check  # fail when the file is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tabalyst.scanner.schema import SCHEMA_FILE, scan_schema_text

TARGET = ROOT / "src" / "tabalyst" / "schemas" / SCHEMA_FILE


def main(argv: list[str]) -> int:
    text = scan_schema_text()
    if "--check" in argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET} is out of date: run python scripts/scan_schema.py")
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
