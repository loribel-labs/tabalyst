"""Excel Inspect: describes a workbook and proposes the table to read (design
inspect ``excel.md``).

``inspect_workbook`` reads a workbook once and returns an ``InspectDocument``.
"""

from tabalyst.inspector.excel_inspect import parameters
from tabalyst.inspector.excel_inspect.build import inspect_workbook

__all__ = ["inspect_workbook", "parameters"]
