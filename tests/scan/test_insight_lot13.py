# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 13: gaps closed without reading the source again (G01 to G09).

The coverage of the numeric block and its refusal for codes, the observation
``minority_length`` and the measures the report derives from existing blocks.
"""

from scan_helpers import dataset, detector, field, run_scan, write_text

from tabalyst.report_measures import (
    decades,
    dominant_share,
    frequency_tail,
    length_spread,
)
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.validation import check_scan


def _csv(directory, header: str, rows) -> object:
    return write_text(directory, "data.csv", header + "\n" + "\n".join(rows) + "\n")


def _scan_model(source):
    return scan(source, config=ScanConfig.model_validate({}))


def _field(result: dict, display: str) -> dict:
    return field(dataset(result, "rows"), display)


def test_G01_the_numeric_block_declares_the_share_of_values_it_covers(tmp_path):
    rows = [f"{index}.5" if index % 4 == 0 else f"n/a{index}" for index in range(400)]

    block = _field(run_scan(_csv(tmp_path, "m", rows)), "m")["numeric"]["value"]

    assert block["count"] == 100
    assert block["coverage"] == {"of": 400, "share": 0.25}


def test_G02_a_column_of_numbers_is_covered_entirely(tmp_path):
    block = _field(run_scan(_csv(tmp_path, "n", [str(i) for i in range(50)])), "n")["numeric"]

    assert block["value"]["coverage"] == {"of": 50, "share": 1.0}


def test_G03_postal_codes_read_as_integers_get_no_numeric_block(tmp_path):
    zips = [f"{10000 + index * 37:05d}" for index in range(300)]
    canadian = ["H2X 1Y4", "K1A 0B1", "M5V 2T6", "V6B 1A1"] * 100
    rows = zips + canadian

    column = _field(run_scan(_csv(tmp_path, "postal", rows)), "postal")

    assert detector(column, "postal_code")["coverage"]["matched"] >= 500
    assert column["numeric"] == {"status": "not_applicable", "reason": "code_interpretation"}


def test_G04_postal_codes_with_leading_zeros_stay_text_and_have_no_block(tmp_path):
    rows = [f"{index:05d}" for index in range(200)]

    column = _field(run_scan(_csv(tmp_path, "zip", rows)), "zip")

    assert column["numeric"]["status"] != "complete"


def test_G05_an_ordinary_integer_column_keeps_its_numeric_block(tmp_path):
    rows = [str(index) for index in range(1, 300)] + ["12345", "54321"]

    column = _field(run_scan(_csv(tmp_path, "amount", rows)), "amount")

    assert column["numeric"]["status"] == "complete"


def test_G06_a_malformed_value_among_uniform_lengths_is_a_minority_length(tmp_path):
    rows = [f"CLI-{1000001 + index}" for index in range(300)] + ["CLI-12"]

    result = run_scan(_csv(tmp_path, "client_id", rows))

    item = next(i for i in result["observations"]["items"] if i["rule"] == "minority_length")
    assert (item["count"], item["of"], item["population"]) == (1, 301, "content_strings")
    assert (item["category"], item["status"]) == ("patterns", "candidate_anomaly")
    assert result["observations"]["version"] == 2


def test_G07_varied_lengths_or_few_values_raise_no_minority_length(tmp_path):
    varied = _csv(tmp_path, "name", ["a" * (1 + index % 9) for index in range(300)])
    few = write_text(tmp_path, "few.csv", "k\n" + "\n".join(["abcdef"] * 5 + ["a"]) + "\n")

    for source in (varied, few):
        items = run_scan(source)["observations"]["items"]
        assert all(item["rule"] != "minority_length" for item in items)


def test_G08_the_scan_with_coverage_passes_the_validator(tmp_path):
    result = _scan_model(_csv(tmp_path, "n", [str(i) for i in range(30)] + ["x"]))

    assert check_scan(result) == []


def test_G09_derived_measures_come_from_existing_blocks(tmp_path):
    rows = ["x" * 5 if index < 90 else "y" * (7 + index % 3) for index in range(100)]
    model = _scan_model(_csv(tmp_path, "t", rows))
    column = model.datasets[0].fields[0]

    spread = length_spread(column)

    assert (spread.q25, spread.median, spread.q75) == (5, 5, 5)
    assert spread.iqr == 0
    assert frequency_tail(column) is None  # the listing is whole
    assert decades(column) is None


def test_G10_decades_and_the_dominant_unit_are_exact(tmp_path):
    dates = ["1999-05-01", "2001-02-03", "2005-01-01", "2013-07-07"] * 5
    units = ["10 Go", "20 Go", "30 Go", "5 km/h"] * 5
    source = _csv(tmp_path, "d,s", [f"{a},{b}" for a, b in zip(dates, units, strict=True)])
    fields = {item.display: item for item in _scan_model(source).datasets[0].fields}

    assert [(d.decade, d.count) for d in decades(fields["d"])] == [(1990, 5), (2000, 10), (2010, 5)]
    dominant = dominant_share(fields["s"])
    assert (dominant.value, dominant.count, dominant.total, dominant.exact) == ("Go", 15, 20, True)
    assert dominant.share == 0.75


def test_G11_the_tail_of_a_cut_frequency_listing_is_what_the_listing_leaves_out(tmp_path):
    rows = [f"v{index % 150}" for index in range(300)]
    column = _scan_model(_csv(tmp_path, "v", rows)).datasets[0].fields[0]

    tail = frequency_tail(column)

    assert (tail.values, tail.of) == (100, 300)
    assert round(tail.share, 4) == 0.3333


def test_G12_a_code_detector_below_half_of_the_values_keeps_the_numeric_block(tmp_path):
    rows = [str(100 + index) for index in range(400)] + ["90210"] * 100

    column = _field(run_scan(_csv(tmp_path, "mix", rows)), "mix")

    assert column["numeric"]["status"] == "complete"
