# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrast of the colours the Errors, Issues and type families are drawn with (RT-16).

Reads the tokens of ``theme.css`` in both themes. The target is WCAG 2.2 AA (4.5:1 for
text, 3:1 for the shapes and bars that carry a meaning), with no claim of certification.
"""

import re
from pathlib import Path

import pytest

import tabalyst

CSS = (Path(tabalyst.__file__).parent / "static" / "theme.css").read_text(encoding="utf-8")
FAMILIES = (
    "identifier",
    "categorical",
    "numeric",
    "temporal",
    "contact",
    "geographic",
    "web_network",
    "text",
    "other",
)
TEXT_TOKENS = ("err-text", "info-text", "attn-text", "text-2", "text-3", "text")
TYPE_TOKENS = ("text", "integer", "number", "boolean", "date", "empty")
SHAPE_TOKENS = (
    "err",
    "issue",
    "info-text",
    "tb-viz-warning",
    *(f"fam-{name}" for name in FAMILIES),
    *(f"tb-viz-type-{name}" for name in TYPE_TOKENS),
)
SURFACES = ("s0", "s1", "s2", "s3")


def _block(selector: str) -> dict[str, str]:
    start = CSS.index(selector + "{")
    body = CSS[start + len(selector) + 1 : CSS.index("}", start)]
    return dict(re.findall(r"--([a-z0-9_-]+)\s*:\s*([^;]+);", body))


def _themes() -> dict[str, dict[str, str]]:
    dark = _block(":root")
    light = {**dark, **_block(':root[data-theme="light"]')}
    return {"dark": dark, "light": light}


def _hex(value: str, tokens: dict[str, str]) -> str:
    value = value.strip()
    if value.startswith("var("):
        return _hex(tokens[value[4:-1].lstrip("-")], tokens)
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), value
    return value


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _backgrounds(theme: str, tokens: dict[str, str]) -> dict[str, str]:
    surfaces = {name: _hex(tokens[name], tokens) for name in SURFACES}
    # The cards are a gradient: both ends are backgrounds a bar or a word sits on.
    card = tokens["g-card"]
    for index, stop in enumerate(re.findall(r"#[0-9A-Fa-f]{6}", card)):
        surfaces[f"g-card-{index}"] = stop
    return surfaces


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_text_colours_of_findings_reach_aa_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [
        (token, surface, round(contrast(_hex(tokens[token], tokens), color), 2))
        for token in TEXT_TOKENS
        for surface, color in _backgrounds(theme, tokens).items()
        if contrast(_hex(tokens[token], tokens), color) < 4.5
    ]
    assert not failures


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_the_shapes_that_carry_a_meaning_reach_three_to_one_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [
        (token, surface, round(contrast(_hex(tokens[token], tokens), color), 2))
        for token in SHAPE_TOKENS
        for surface, color in _backgrounds(theme, tokens).items()
        if contrast(_hex(tokens[token], tokens), color) < 3
    ]
    assert not failures


def _family_token(name: str) -> str:
    """The dataviz token a family colour points to (``--fam-web_network`` is ``--tb-viz-family-web-network``)."""
    target = _block(":root")[f"fam-{name}"].strip()
    assert target.startswith("var(--tb-viz-family-"), f"fam-{name} is not a dataviz family token"
    return target[4:-1].lstrip("-")


def test_every_family_has_a_colour_in_both_themes():
    light = _block(':root[data-theme="light"]')
    for name in FAMILIES:
        token = _family_token(name)
        assert token in _block(":root")
        assert token in light, f"{token} falls back to a dark-theme colour"


def test_the_brand_orange_is_not_the_colour_of_a_family():
    for theme, tokens in _themes().items():
        for name in FAMILIES:
            colour = _hex(tokens[f"fam-{name}"], tokens).upper()
            assert colour not in {"#F98510", "#B85200", "#D06500"}, f"{name} is orange in {theme}"


def test_the_families_are_told_apart_in_both_themes():
    for theme, tokens in _themes().items():
        colours = {name: _hex(tokens[f"fam-{name}"], tokens).upper() for name in FAMILIES}
        assert len(set(colours.values())) == len(FAMILIES), f"two families share a colour in {theme}"
