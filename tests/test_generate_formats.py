# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit tests for all format transformations in Generate (F01 to F22)."""

from __future__ import annotations

import random
import unicodedata

from tabalyst.generate_anomalies import FORMAT_VALUES, TEXT_TRANSFORMS
from tabalyst.generate_canonical import (
    canonical_decimal,
    canonical_text,
)


def test_all_format_values_have_matching_transform() -> None:
    """Every registered FORMAT_VALUE exists in TEXT_TRANSFORMS."""
    assert set(TEXT_TRANSFORMS) == FORMAT_VALUES


def test_f01_surrounding_space() -> None:
    """F01: Surrounding spaces (leading and trailing)."""
    rng = random.Random(42)
    fn = TEXT_TRANSFORMS["surrounding_space"]
    assert fn("Tremblay", rng) == " Tremblay "
    # If already surrounded by spaces, unchanged
    assert fn(" Tremblay ", rng) == " Tremblay "
    # Canonical text strips surrounding spaces
    assert canonical_text(fn("Tremblay", rng)) == "Tremblay"


def test_f02_internal_repeated_spaces() -> None:
    """F02: Internal repeated spaces."""
    rng = random.Random(42)
    fn_double = TEXT_TRANSFORMS["double_space"]
    assert fn_double("Jean Tremblay", rng) == "Jean  Tremblay"
    assert fn_double("Tremblay", rng) == "Tremblay"


def test_f03_non_breaking_space_and_invisible_chars() -> None:
    """F03: Non-breaking space and zero-width chars."""
    rng = random.Random(42)
    fn_nbsp = TEXT_TRANSFORMS["insert_non_breaking_space"]
    res_nbsp = fn_nbsp("Tremblay", rng)
    assert "\u00a0" in res_nbsp
    assert len(res_nbsp) == len("Tremblay") + 1
    # If already has nbsp, unchanged
    assert fn_nbsp(res_nbsp, rng) == res_nbsp

    fn_zw = TEXT_TRANSFORMS["insert_zero_width"]
    res_zw = fn_zw("Tremblay", rng)
    assert "\u200b" in res_zw


def test_f04_unicode_nfd_and_nfc() -> None:
    """F04: Unicode NFD and NFC variants."""
    rng = random.Random(42)
    fn_nfd = TEXT_TRANSFORMS["unicode_nfd"]
    fn_nfc = TEXT_TRANSFORMS["unicode_nfc"]

    # Accented word in NFC (standard)
    word_nfc = unicodedata.normalize("NFC", "Montréal")
    assert unicodedata.is_normalized("NFC", word_nfc)

    word_nfd = fn_nfd(word_nfc, rng)
    assert unicodedata.is_normalized("NFD", word_nfd)
    assert word_nfd != word_nfc
    assert len(word_nfd) > len(word_nfc)  # combining char adds code points

    # Transforming NFD back to NFC
    assert fn_nfc(word_nfd, rng) == word_nfc

    # ASCII text is unchanged
    assert fn_nfd("Montreal", rng) == "Montreal"

    # Canonical text normalizes back to NFC
    assert canonical_text(word_nfd) == word_nfc


def test_f05_casing_variations() -> None:
    """F05: Casing variations (upper, lower, title)."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["upper"]("auto", rng) == "AUTO"
    assert TEXT_TRANSFORMS["lower"]("AUTO", rng) == "auto"
    assert TEXT_TRANSFORMS["title_case"]("auto", rng) == "Auto"
    assert TEXT_TRANSFORMS["title_case"]("jean tremblay", rng) == "Jean Tremblay"
    assert TEXT_TRANSFORMS["title_case"]("Auto", rng) == "Auto"


def test_f06_strip_accents() -> None:
    """F06: Accent removal."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["strip_accents"]("Québec", rng) == "Quebec"
    assert TEXT_TRANSFORMS["strip_accents"]("prélèvement", rng) == "prelevement"
    assert TEXT_TRANSFORMS["strip_accents"]("Ontario", rng) == "Ontario"


def test_f07_phone_formats() -> None:
    """F07: Valid phone variations."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["phone_spaces"]("+1-514-555-0123", rng) == "+1 514 555 0123"
    assert TEXT_TRANSFORMS["phone_double_space"]("+1-514-555-0123", rng) == "+1  514-555-0123"


def test_f08_phone_drop_digit() -> None:
    """F08: Invalid phone number with dropped digit."""
    rng = random.Random(42)
    phone = "+1-514-555-0123"
    mutated = TEXT_TRANSFORMS["phone_drop_digit"](phone, rng)
    assert len(mutated) == len(phone) - 1
    assert sum(c.isdigit() for c in mutated) == sum(c.isdigit() for c in phone) - 1
    # Short string with too few digits is unchanged
    assert TEXT_TRANSFORMS["phone_drop_digit"]("+1-55", rng) == "+1-55"


def test_f09_email_invalid() -> None:
    """F09: Corrupt email syntax."""
    rng = random.Random(42)
    email = "client@example.ca"
    assert TEXT_TRANSFORMS["email_invalid"](email, rng) == "clientexample.ca"
    assert TEXT_TRANSFORMS["email_invalid"]("invalid-address", rng) == "invalid-address"


def test_f10_email_forbidden_domain() -> None:
    """F10: Valid email but with disallowed/forbidden test domain."""
    rng = random.Random(42)
    email = "client.42@compagnie.qc.ca"
    forbidden = TEXT_TRANSFORMS["email_forbidden_domain"](email, rng)
    assert forbidden == "client.42@forbidden-test.com"
    # Unchanged if not an email
    assert TEXT_TRANSFORMS["email_forbidden_domain"]("no_at_sign", rng) == "no_at_sign"


def test_f11_postal_no_space() -> None:
    """F11: Postal code without space."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["postal_no_space"]("H1A 1A1", rng) == "H1A1A1"
    assert TEXT_TRANSFORMS["postal_no_space"]("K1P 5L1", rng) == "K1P5L1"
    # Already without space or invalid
    assert TEXT_TRANSFORMS["postal_no_space"]("H1A1A1", rng) == "H1A1A1"
    assert TEXT_TRANSFORMS["postal_no_space"]("invalid", rng) == "invalid"


def test_f12_postal_invalid_syntax() -> None:
    """F12: Postal code with invalid syntax."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["postal_invalid_syntax"]("H1A 1A1", rng) == "H!A 1A1"
    assert TEXT_TRANSFORMS["postal_invalid_syntax"]("invalid", rng) == "invalid"


def test_f13_decimal_comma_and_dot() -> None:
    """F13: Decimal separators comma and dot."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["decimal_comma"]("1234.56", rng) == "1234,56"
    assert TEXT_TRANSFORMS["decimal_comma"]("1234,56", rng) == "1234,56"
    assert TEXT_TRANSFORMS["decimal_comma"]("text", rng) == "text"

    assert TEXT_TRANSFORMS["decimal_dot"]("1234,56", rng) == "1234.56"
    assert TEXT_TRANSFORMS["decimal_dot"]("1234.56", rng) == "1234.56"

    # Canonical decimal restores standard dot
    assert canonical_decimal("1234,56") == "1234.56"


def test_f14_thousands_separators() -> None:
    """F14: Thousands separators space and comma."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["thousands_space"]("1234.56", rng) == "1 234.56"
    assert TEXT_TRANSFORMS["thousands_space"]("1234567.89", rng) == "1 234 567.89"
    assert TEXT_TRANSFORMS["thousands_space"]("12.50", rng) == "12.50"  # no thousands

    assert TEXT_TRANSFORMS["thousands_comma"]("1234.56", rng) == "1,234.56"
    assert TEXT_TRANSFORMS["thousands_comma"]("1234567.89", rng) == "1,234,567.89"
    assert TEXT_TRANSFORMS["thousands_comma"]("12.50", rng) == "12.50"

    # Canonical decimal handles both
    assert canonical_decimal("1 234.56") == "1234.56"
    assert canonical_decimal("1,234.56") == "1234.56"
    assert canonical_decimal("1 234 567.89") == "1234567.89"
    assert canonical_decimal("1,234,567.89") == "1234567.89"


def test_f15_currency_symbols() -> None:
    """F15: Integrated currency symbols."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["currency_suffix"]("1234.56", rng) == "1234.56 $"
    assert TEXT_TRANSFORMS["currency_prefix"]("1234.56", rng) == "$1234.56"
    assert TEXT_TRANSFORMS["currency_fr"]("1234.56", rng) == "1 234,56 $"
    assert TEXT_TRANSFORMS["currency_code"]("1234.56", rng) == "1234.56 CAD"


def test_f18_date_impossible() -> None:
    """F18: Impossible dates (31 Feb or day 32)."""
    rng = random.Random(42)
    fn = TEXT_TRANSFORMS["date_impossible"]
    # ISO
    assert fn("2026-02-15", rng) == "2026-02-31"
    assert fn("2026-05-10", rng) == "2026-05-32"
    # DD-MM-YYYY (Quebec)
    assert fn("15-02-2026", rng) == "31-02-2026"
    assert fn("10-05-2026", rng) == "32-05-2026"
    # MM-DD-YYYY (Ontario)
    assert fn("02-15-2026", rng) == "02-31-2026"
    assert fn("05-10-2026", rng) == "32-10-2026"


def test_f19_date_other_branch_conventions() -> None:
    """F19: Dates in the convention of another branch."""
    rng = random.Random(42)
    assert TEXT_TRANSFORMS["date_dmy"]("2026-10-05", rng) == "05-10-2026"
    assert TEXT_TRANSFORMS["date_iso"]("05-10-2026", rng) == "2026-10-05"
    assert TEXT_TRANSFORMS["date_mdy_iso"]("10-05-2026", rng) == "2026-10-05"


def test_f20_date_ambiguous_swap() -> None:
    """F20: Ambiguous date where day and month <= 12 are swapped."""
    rng = random.Random(42)
    fn = TEXT_TRANSFORMS["date_swap_month_day"]
    # 5 October in ISO (2026-10-05) becomes 10 May (2026-05-10)
    assert fn("2026-10-05", rng) == "2026-05-10"
    # 5 October in Quebec format (05-10-2026) becomes 10 May (10-05-2026)
    assert fn("05-10-2026", rng) == "10-05-2026"
    # 5 October in Ontario format (10-05-2026) becomes 10 May (05-10-2026)
    assert fn("10-05-2026", rng) == "05-10-2026"

    # Non-ambiguous dates (day > 12) are unchanged
    assert fn("2026-10-25", rng) == "2026-10-25"
    assert fn("25-10-2026", rng) == "25-10-2026"
    # Same day and month is unchanged
    assert fn("2026-05-05", rng) == "2026-05-05"


def test_f21_drop_leading_zeros() -> None:
    """F21: Remove zero-padding from identifiers."""
    rng = random.Random(42)
    fn = TEXT_TRANSFORMS["drop_leading_zeros"]
    assert fn("QC-0000123", rng) == "QC-123"
    assert fn("CRT-0042", rng) == "CRT-42"
    assert fn("CLI-000999", rng) == "CLI-999"
    assert fn("00123", rng) == "123"
    # Without leading zeros, unchanged
    assert fn("QC-123", rng) == "QC-123"
    assert fn("AUTO", rng) == "AUTO"


def test_f22_similar_char() -> None:
    """F22: Visually similar characters (0 <-> O, 1 <-> I)."""
    rng = random.Random(42)
    fn = TEXT_TRANSFORMS["similar_char"]
    assert fn("QC-0012", rng) == "QC-O012"
    assert fn("QC-O12", rng) == "QC-012"
    assert fn("CRT-123", rng) == "CRT-I23"
    assert fn("CRT-I23", rng) == "CRT-123"
    assert fn("XYZ", rng) == "XYZ"
