"""Excel selection rule and candidates (design inspect ``excel.md``, cases A).

The table of a sheet is found by ``tabalyst.scanner.readers.excel_table``,
which the Excel reader shares."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from tabalyst.inspector.excel_inspect import parameters
from tabalyst.scanner.readers.excel_table import (  # noqa: F401
    Facts,
    analyze_rows,
    find_header,
    merged_in_table,
)


@dataclass(slots=True)
class Candidate:
    """A sheet or a named table, with what Inspect learned about it."""

    path: str
    kind: str
    sheet: str
    table: str | None
    visible: bool
    elements: int = 0
    eligible: bool = False
    ineligible_reason: str | None = None
    range: str | None = None
    header_row: int | None = None
    columns: list[str] = field(default_factory=list)
    blank_rows: int = 0
    merged_ranges: int = 0


@dataclass(frozen=True, slots=True)
class Choice:
    """The outcome of the selection rule."""

    path: str | None
    basis: str
    over: str | None = None


def select(candidates: Sequence[Candidate], *, truncated: bool) -> Choice:
    """Choose the table to read, or none, from the exact row counts.

    Deterministic: sheet names play no role and a tie never selects. A hidden
    sheet competes only when no visible table is eligible."""
    if truncated:
        # An incomplete list can never prove that a table stands out.
        return Choice(None, "candidates_truncated")
    eligible = [item for item in candidates if item.eligible]
    pool = [item for item in eligible if item.visible] or eligible
    pool.sort(key=lambda item: item.elements, reverse=True)
    if not pool:
        return Choice(None, "no_eligible_candidate")
    if len(pool) == 1:
        return Choice(pool[0].path, "only_eligible_candidate")
    first, second = pool[0], pool[1]
    if first.elements >= parameters.DOMINANCE_RATIO * second.elements:
        return Choice(first.path, "dominant_candidate", over=second.path)
    return Choice(None, "ambiguous")
