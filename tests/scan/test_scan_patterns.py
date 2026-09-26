"""Scan contract: declarative patterns and sensitive values (lot 3b)."""

import json

import pytest
from scan_helpers import dataset, detector, field, run_scan, write_text

pytestmark = pytest.mark.lot("3b")

CUSTOMER_NUMBER = {
    "id": "customer_number",
    "regex": r"C-\d{4}",
    "description": "Customer number",
}
SECRET = {"id": "secret", "regex": r"SECRET-\d{4}", "sensitive": True}


def test_declarative_pattern_needs_no_engine_change(tmp_path):
    """CA14 and EF29."""
    source = write_text(tmp_path, "customers.csv", "customer\nC-0001\nC-0002\nX-1\n")

    customer = field(
        dataset(run_scan(source, patterns=[CUSTOMER_NUMBER]), "rows"), "customer"
    )

    coverage = detector(customer, "pattern:customer_number")["coverage"]
    assert (coverage["eligible"], coverage["matched"], coverage["not_matched"]) == (
        3,
        2,
        1,
    )


@pytest.mark.parametrize(
    "patterns",
    [
        [{"id": "broken", "regex": "("}],
        [CUSTOMER_NUMBER, CUSTOMER_NUMBER],
        [{"id": "long", "regex": "a" * 1001}],
    ],
    ids=["invalid-regex", "duplicate-id", "too-long"],
)
def test_invalid_patterns_are_rejected_before_scanning(patterns):
    """ET18 and O11."""
    from tabalyst.scanner import ScanConfig

    with pytest.raises(ValueError):
        ScanConfig.model_validate({"patterns": patterns})


@pytest.mark.parametrize(
    ("exposure", "visible_shape"),
    [("hide", None), ("mask", "AAAAAA-9999")],
)
def test_sensitive_values_never_leak_through_another_block(
    tmp_path, exposure, visible_shape
):
    """CA20, ET17 and O10: one exposure gate for every value-bearing block."""
    source = write_text(
        tmp_path,
        "secrets.csv",
        "code,city\nSECRET-1111,Laval\nSECRET-2222,Laval\n SECRET-1111 ,Laval\n",
    )

    result = run_scan(
        source, patterns=[SECRET], exposure={"sensitive_values": exposure}
    )

    text = json.dumps(result, ensure_ascii=False)
    assert "SECRET-1111" not in text
    assert "SECRET-2222" not in text
    rows = dataset(result, "rows")
    assert field(rows, "code")["sensitive"] is True
    assert field(rows, "city")["sensitive"] is False
    assert "Laval" in text
    if visible_shape:
        assert visible_shape in text
