"""Parameters of Excel Inspect detection (design inspect excel.md).

Provisional until they are measured on real workbooks: lot X-2 fixed them on
synthetic ones (the maintainer chose to go on without real workbooks). Tests
import these names and build their data from them.
"""

# Rows searched, from the first filled row, for the header of a sheet (shared
# with the Excel reader, which must find the same header).
from tabalyst.scanner.readers.excel_table import HEADER_SCAN_ROWS  # noqa: F401

# Header names listed per candidate in the detection.
COLUMNS_LISTED = 100
# Candidates kept per workbook.
MAX_CANDIDATES = 100
# Data row ratio from which the largest eligible candidate stands out
# (the value of JSON Inspect, not measured for tables yet).
DOMINANCE_RATIO = 10
# Ineligible candidates described one by one in the warnings; the rest is counted.
MAX_INELIGIBLE_NOTES = 10
