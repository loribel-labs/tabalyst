# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The previews of a report share one dialog filled when it opens (lot R10b, 20.6)."""

import re

from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.reporting import render_report


def _html(tmp_path):
    lines = ["contact,row"]
    lines += [f"user{n}@example.org,{n}" for n in range(100)]
    lines += [f"bad {n}@example.org,{100 + n}" for n in range(3)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    return render_report(analyze_csv(source))


def test_the_page_holds_a_single_dialog_element(tmp_path):
    html = _html(tmp_path)

    assert html.count('role="dialog"') == 1
    assert re.search(r'<div class="pop" id="pop" role="dialog" hidden></div>', html)


def test_every_preview_button_names_a_template_of_the_page(tmp_path):
    html = _html(tmp_path)

    targets = re.findall(r'data-pop="([^"]+)"', html)
    templates = set(re.findall(r'<template id="([^"]+)" data-label="[^"]*"', html))

    assert targets
    assert set(targets) <= templates
    assert all(f'id="{name}"' not in html.replace(f'<template id="{name}"', "") for name in targets)
