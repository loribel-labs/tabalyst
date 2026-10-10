# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The web page of a smart sample (design 20.16): the report of the sample, read.

``tabalyst sample --sample-method smart`` writes it beside the report document.
It is rendered from the ``tabalyst.sample`` document alone: it reads neither the
source nor the sample CSV.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from tabalyst.reporting import _environment
from tabalyst.scanner.smart.reasons import miss_text
from tabalyst.scanner.smart.result import STATEMENTS, SampleDocument

PAGE_SUFFIX = ".html"

FAMILY_WORDS: dict[str, str] = {
    "low_cardinality": "Few values",
    "structured_string": "Structured text",
    "numeric": "Numbers",
    "date": "Dates",
    "quality": "Quality",
    "relations": "Relations",
}


def sample_page_path(report: Path) -> Path:
    """Where the page goes: beside the report document, with the same name and the
    extension ``.html`` (``customers.sample.json`` gives ``customers.sample.html``)."""
    return report.with_suffix(PAGE_SUFFIX)


def render_sample_page(document: SampleDocument) -> str:
    """The page of a smart sample, as one self-contained HTML text."""
    resources = files("tabalyst")
    template = _environment().from_string(
        resources.joinpath("templates/sample.html").read_text(encoding="utf-8")
    )
    return template.render(
        doc=document,
        cov=document.coverage,
        sel=document.selection,
        records=document.plan.size.records,
        family_words=FAMILY_WORDS,
        miss_text=miss_text,
        statement_words=STATEMENTS,
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
    )
