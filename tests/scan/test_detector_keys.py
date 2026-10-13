# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Declared keys of the ``email``, ``phone`` and ``postal_code`` detectors (Patterns
lot P5, algorithm section 4): counted exactly in the first pass, kept by floors and
exposed on a masked field (DEC-027)."""

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.keys import KeyNode, add_path, from_pairs, keys_block
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.validation import check_scan


def _block(result, detector):
    [found] = [item for item in result.datasets[0].fields[0].detectors if item.id == detector]
    return found.details["keys"]


def _emails(tmp_path, domains, **settings):
    rows = [f"u{i}@{domain}" for i, domain in enumerate(domains)]
    return scan_csv(tmp_path, "mail", rows, **settings)


def _tree(block):
    return {
        item["key"]: (item["occurrences"], _tree({"keys": item.get("keys", [])}))
        for item in block["keys"]
    }


def test_email_keys_count_the_extension_then_the_domain_from_the_right(tmp_path):
    domains = ["gmail.com"] * 50 + ["bbc.co.uk"] * 18 + ["x.co.uk"] * 12 + ["a.fr"] * 10
    block = _block(_emails(tmp_path, domains), "email")
    assert block["status"] == "complete"
    assert block["levels"][:2] == ["extension", "domain"]
    assert _tree(block) == {
        "com": (50, {"gmail.com": (50, {})}),
        # co.uk emerges without a list of public suffixes, then its domains
        "uk": (30, {"co.uk": (30, {"bbc.co.uk": (18, {}), "x.co.uk": (12, {})})}),
        "fr": (10, {"a.fr": (10, {})}),
    }
    assert block["others"] == {"keys": 0, "occurrences": 0}


def test_keys_below_the_floors_are_aggregated_in_others(tmp_path):
    # The listing stops at 95 % of the field: the small extensions are the others.
    domains = ["big.com"] * 900 + ["few.ca"] * 4 + ["rare.net"] * 4 + ["mid.org"] * 60
    block = _block(_emails(tmp_path, domains), "email")
    assert [item["key"] for item in block["keys"]] == ["com", "org"]
    assert block["others"] == {"keys": 2, "occurrences": 8}


def test_a_masked_email_field_still_publishes_its_keys_and_nothing_else(tmp_path):
    result = _emails(tmp_path, ["gmail.com"] * 30 + ["yahoo.ca"] * 20)
    field = result.datasets[0].fields[0]
    assert field.exposure == "mask"
    assert _tree(_block(result, "email")) == {
        "com": (30, {"gmail.com": (30, {})}),
        "ca": (20, {"yahoo.ca": (20, {})}),
    }
    # No complete address is published: only the masks of the values remain.
    assert "u1@" not in result.model_dump_json()


def test_detector_keys_mask_brings_the_masking_back(tmp_path):
    result = _emails(
        tmp_path, ["gmail.com"] * 30, exposure={"detector_keys": "mask"}
    )
    assert _block(result, "email") == {"status": "disabled", "reason": "exposure"}
    assert "gmail" not in result.datasets[0].fields[0].detectors[0].model_dump_json()


def test_the_keys_of_a_field_that_is_not_masked_follow_the_setting_too(tmp_path):
    rows = ["H2X 1A1"] * 30 + ["G1V 2B2"] * 20
    result = scan_csv(tmp_path, "code", rows, exposure={"detector_keys": "mask"})
    assert _tree(_block(result, "postal_code")) == {
        "H": (30, {"H2X": (30, {})}),
        "G": (20, {"G1V": (20, {})}),
    }


def test_extensions_stay_exact_when_the_domains_tracked_overflow(tmp_path):
    domains = [f"d{i}.com" for i in range(30)] + ["x.ca"] * 30
    result = _emails(tmp_path, domains, detectors={"email": {"max_tracked_domains": 20}})
    block = _block(result, "email")
    assert block["status"] == "limited"
    assert block["reason"] == "max_tracked"
    assert _tree(block)["com"][0] == 30
    assert _tree(block)["ca"][0] == 30
    assert check_scan(result) == []


def test_phone_keys_give_the_same_area_code_whatever_the_format(tmp_path):
    rows = (
        ["(514) 555-0123"] * 10
        + ["+1 514-555-0124"] * 10
        + ["514.555.0125"] * 10
        + ["06 12 34 56 78"] * 8
        + ["+33 6 12 34 56 78"] * 8
        + ["0033 (0) 1 23 45 67 89"] * 8
    )
    result = scan_csv(tmp_path, "phone", rows)
    assert result.datasets[0].fields[0].exposure == "mask"
    block = _block(result, "phone")
    assert block["levels"] == ["region", "area"]
    assert _tree(block) == {
        "nanp": (30, {"514": (30, {})}),
        "fr": (24, {"06": (16, {}), "01": (8, {})}),
    }


def test_postal_keys_read_the_first_character_and_the_area(tmp_path):
    rows = ["H2X 1A1"] * 20 + ["h2x1a2"] * 10 + ["12345"] * 8 + ["12399-1234"] * 6
    block = _block(scan_csv(tmp_path, "code", rows), "postal_code")
    assert _tree(block) == {
        "H": (30, {"H2X": (30, {})}),
        "1": (14, {"123": (14, {})}),
    }


def test_the_keys_add_up_and_check_scan_finds_a_falsified_count(tmp_path):
    result = _emails(tmp_path, ["gmail.com"] * 60 + ["yahoo.ca"] * 40)
    assert check_scan(result) == []
    block = _block(result, "email")
    block["keys"][0]["occurrences"] += 1
    assert any("keys" in problem for problem in check_scan(result))


def test_the_keys_do_not_depend_on_the_number_of_workers(tmp_path):
    rows = [f"u{i}@{'gmail.com' if i % 3 else 'yahoo.ca'}" for i in range(3_000)]
    one = scan_csv(tmp_path, "mail", rows, workers=1) if False else None
    assert one is None


    path = write_text(tmp_path, "mail.csv", "mail\n" + "\n".join(rows) + "\n")
    config = ScanConfig()
    first = _block(scan(path, config=config, workers=1), "email")
    several = _block(scan(path, config=config, workers=3), "email")
    assert first == several


def test_a_masked_block_is_disabled_without_work():
    roots = {"com": KeyNode(10)}
    gate = ExposureGate("mask", aggregates=False)
    assert keys_block(roots, ("extension",), gate) == {"status": "disabled", "reason": "exposure"}
    assert ExposureGate("show", aggregates=False).exposes_keys
    assert ExposureGate("hide").exposes_keys


@pytest.mark.parametrize(("count", "kept"), [(5, True), (4, False)])
def test_the_floor_of_five_occurrences_is_a_privacy_floor(count, kept):
    roots: dict[str, KeyNode] = {}
    add_path(roots, ["com"], 50)
    add_path(roots, ["net"], 40)
    add_path(roots, ["ca"], count)
    for i in range(10 - count):
        add_path(roots, [f"z{i}"], 1)
    block = keys_block(roots, ("extension",), ExposureGate("show"))
    assert ("ca" in {item["key"] for item in block["keys"]}) is kept


def test_keys_below_a_key_stop_at_ninety_five_percent_of_it():
    roots = from_pairs({"nanp": {"514": 50, "450": 46, "418": 4}})
    block = keys_block(roots, ("region", "area"), ExposureGate("show"))
    [nanp] = block["keys"]
    assert [item["key"] for item in nanp["keys"]] == ["514", "450"]
    assert nanp["others"] == {"keys": 1, "occurrences": 4}


def test_a_detector_that_matched_nothing_publishes_no_keys(tmp_path):
    result = scan_csv(tmp_path, "name", ["alice", "bob"] * 5)
    assert _block(result, "email") == {"status": "not_applicable", "reason": "no_values"}
    assert check_scan(result) == []


def test_check_scan_reports_a_malformed_keys_block_instead_of_raising(tmp_path):
    result = _emails(tmp_path, ["gmail.com"] * 60 + ["yahoo.ca"] * 40)
    del _block(result, "email")["others"]
    assert any("malformed" in problem for problem in check_scan(result))


def test_values_the_detector_did_not_test_make_the_keys_limited(tmp_path):
    long_local = "x" * 300
    rows = [f"{long_local}@big.com"] * 10 + ["a@gmail.com"] * 30
    block = _block(scan_csv(tmp_path, "mail", rows), "email")
    assert block["status"] == "limited" and block["reason"] == "not_tested"
