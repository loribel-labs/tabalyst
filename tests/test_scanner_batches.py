# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Batch processing of distinct values gives the results of the value by value
rules (design 13): prefiltered ``classify_many`` of each built-in detector,
the inline normalization of printable strings, masks, record digests and
record batches."""

import pytest

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.config import NormalizationSettings
from tabalyst.scanner.detectors.registry import BUILT_INS
from tabalyst.scanner.exposure import _symbol, mask
from tabalyst.scanner.measures import ValueMeasures, characteristic_flags
from tabalyst.scanner.normalization import STAGES, Normalizer
from tabalyst.scanner.records import _table_digest

VALUES = [
    "",
    " ",
    "a",
    "Z",
    "abc",
    "ABC",
    "Abc",
    " abc",
    "abc ",
    "a  b",
    "a\tb",
    "a\nb",
    "a\x1fb",
    "a\x00b",
    "café",
    "café",
    "CAFÉ",
    "École",
    "straße",
    "ſeptember 5, 2026",
    "Ｊａｎｕａｒｙ 5, 2026",
    "東京",
    "\U0001f600",
    "x y",
    "a b",
    " lead",
    "Ⅻ",
    "ǅ",
    "0",
    "00",
    "007",
    "-0",
    "+1",
    "12",
    "１２",
    "١٢٣",
    "²",
    "12345",
    "123456",
    "1.5",
    "1.500",
    "1,5",
    "1,500",
    "1.234,5",
    "1 234",
    "1 234",
    "12,345.67",
    "1e3",
    "1E-3",
    "1e99999999999999999999",
    ".5",
    "5.",
    "1-2",
    "1+2",
    "2026-09-26",
    "26/09/2026",
    "09/26/2026",
    "01/02/2026",
    "2026-02-30",
    "2026-09-26T10:20:30Z",
    "2026-09-26 10:20:30+05:00",
    "2026-09-26T10:20z",
    "10:20",
    "25:61",
    "26 September 2026",
    "1er janvier 2026",
    "September 26, 2026",
    "Sept. 5 2026",
    "5 sept. 2026",
    "2026.09.26",
    "2026/9/6",
    "true",
    "FALSE",
    "yes",
    "N",
    "oui",
    "Vrai",
    "jane@example.com",
    "Jane.Doe@Example.COM",
    "bad@@x.com",
    "a b@x.com",
    "x@localhost",
    "http://example.com",
    "https://ex.org/a?b#c",
    "www.example.com",
    "ftp://[::1]:21/x",
    "HTTP://EXAMPLE.COM",
    "http://h:99999",
    "514-555-0100",
    "(514) 555-0100",
    "+1 514 555 0100",
    "5145550100",
    "06 12 34 56 78",
    "+33 6 12 34 56 78",
    "0033 (0) 6 12 34 56 78",
    "+33 0612345678",
    "H2X 1Y4",
    "h2x1y4",
    "D2X 1Y4",
    "12345-6789",
    "02134",
    "$12.50",
    "12,50 €",
    "CAD 1,234.56",
    "($1,234.56)",
    "-€5",
    "USD12",
    "XYZ 5",
    "12%",
    "12,5 %",
    "-3.5%",
    "10 Go",
    "1 024 Mo",
    "90 km/h",
    "12 ans",
    "12B",
    "5 er",
    "123e4567-e89b-12d3-a456-426614174000",
    "{123E4567-E89B-12D3-A456-426614174000}",
    "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
    "123g4567-e89b-12d3-a456-426614174000",
    "192.168.0.1",
    "256.1.1.1",
    "01.2.3.4",
    "::1",
    "2001:db8::1",
    "::ffff:192.168.0.1",
    "22:00:00",
    "00:1A:2B:3C:4D:5E",
    "C-1234",
    "x" * 300,
]

SETTINGS = {
    "number": [{}, {"conventions": ["comma"]}, {"ambiguous_convention": "comma"}],
    "date": [
        {},
        {"orders": ["DMY"], "separators": ["/"], "month_languages": ["fr"]},
        {"ambiguous_order": "MDY"},
    ],
    "boolean": [{}, {"pairs": [["on", "off"]]}],
    "url": [{}, {"schemes": ["ftp"], "www": False}],
    "phone": [{}, {"regions": ["fr"]}],
    "postal_code": [{}, {"regions": ["us"]}],
    "currency": [{}, {"conventions": ["comma"]}],
    "percentage": [{}, {"conventions": ["dot"]}],
    "quantity": [{}, {"ambiguous_convention": "dot"}],
    "ip_address": [{}, {"versions": ["ipv6"]}],
}


def _detectors():
    config = ScanConfig()
    for detector_class in BUILT_INS:
        section = getattr(config.detectors, detector_class.id)
        for override in SETTINGS.get(detector_class.id, [{}]):
            settings = {**section.model_dump(), **override}
            yield pytest.param(
                detector_class(settings), id=f"{detector_class.id}-{override}"
            )


@pytest.mark.parametrize("detector", list(_detectors()))
def test_classify_many_equals_classify(detector):
    assert detector.classify_many(VALUES) == [detector.classify(v) for v in VALUES]


NORMALIZATIONS = [
    {},
    {"casefold": False},
    {"strip_accents": False},
    {"nfc": False},
    {"trim": False},
    {"collapse_whitespace": False},
]


@pytest.mark.parametrize("settings", NORMALIZATIONS)
def test_batch_normalization_equals_the_value_by_value_rules(settings):
    normalizer = Normalizer(NormalizationSettings(**settings))
    raws = [value for value in VALUES if value.strip()]
    measures = ValueMeasures()
    forms: dict[str, tuple[str, ...]] = {}

    texts, lengths = measures.add_strings(raws, [1] * len(raws), normalizer, forms)

    flags: dict[int, int] = {}
    changes: dict[int, int] = {}
    for raw, text, length in zip(raws, texts, lengths, strict=True):
        stages, changed = normalizer.run(raw)
        assert text == stages[2], raw
        assert length == len(stages[2])
        assert forms.get(raw) == (stages if changed else None), raw
        flag = characteristic_flags(raw)
        flags[flag] = flags.get(flag, 0) + 1
        if changed:
            changes[changed] = changes.get(changed, 0) + 1
    assert measures.flags == flags
    assert measures.changes == changes
    assert len(measures.changed) == len(STAGES)


def test_masks_are_the_same_through_the_translation_table():
    for value in VALUES:
        assert mask(value) == "".join(map(_symbol, value)), value


def test_table_digests_tell_values_apart_around_nul_characters():
    rows = [["a", "b"], ["a\0", "b"], ["a", "\0b"], ["a\0b", ""], ["", "a\0b"]]
    digests = [_table_digest(row) for row in rows]

    assert len(set(digests)) == len(rows)
    assert _table_digest(["a", "b"]) == digests[0]


def test_record_hook_receives_each_record_of_a_batch(tmp_path):
    source = tmp_path / "rows.csv"
    source.write_bytes(b'a,b\n1,"two\nlines"\n2,x\n3\n4,y\n')
    records = []

    scan(
        source,
        config=ScanConfig.model_validate({"errors": {"policy": "tolerant"}}),
        on_record=records.append,
    )

    assert [(r.index, r.location.line) for r in records] == [(1, 2), (2, 4), (4, 6)]
    assert [[o.value for o in r.observations[1:]] for r in records] == [
        ["1", "two\nlines"],
        ["2", "x"],
        ["4", "y"],
    ]
