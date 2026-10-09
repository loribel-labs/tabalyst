# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The calibrated cost model of the planner (design 20.2, lot 6b).

Every constant below stands on a measure made with
``benchmarks/planner_costs.py`` or on the baselines of ``docs/dev/scan/
benchmarks.md``; the comment says which. Sizes are payloads of the structures,
not process memory (specification 11.3). Nothing here depends on the machine
that plans: the plan uses these constants, never a measured time, so the same
Scan gives the same plan anywhere (principle 7). Changing a value changes
``COST_MODEL_VERSION``.
"""

from __future__ import annotations

from tabalyst.scanner.planner.models import CPU_ORDER, CpuClass

COST_MODEL_VERSION = 1

# Sizes in bytes -------------------------------------------------------------

COUNTER_BYTES = 8
# CPython ASCII text: 41 bytes of header and terminator, plus one byte per
# character (measured; a text with wider characters is larger, which the exact
# set of lot 7b avoids with an injective compact key).
STR_OBJECT_BYTES = 41
INT_OBJECT_BYTES = 32
# Bytes the hash table of a set adds to each entry: (minimum, expected,
# maximum). A set holds 27 to 53 bytes a slot between 60% and 30% of load
# (sets of 100,000 to 1,000,000 entries measured 25.5 to 42); the maximum
# includes the old and the new table that coexist while it grows (measured
# peaks up to 56).
SET_SLOT_BYTES = (27, 37, 80)
# A table of counts: dictionary entry and count, plus the key text (measured 98
# to 101 bytes for a key of 10 characters).
TABLE_ENTRY_BYTES = 90
# A compiled matcher measured 2.2 to 4.4 KB.
MATCHER_BYTES = 5_120
# The small result object of an analysis; under 0.001% of any budget.
RESULT_BYTES = 1_024
# Reading the source once: the readers hold at most 8 MiB of batch (a CSV batch
# is closed by size); the worst measured peak is 19 MB (60,000 rows of texts
# up to 8,000 characters), 7 to 8 MB for the other files.
PARSER_RESERVE_BYTES = 24 * 1024 * 1024

# Budgets --------------------------------------------------------------------

# What a selection may never exceed, whoever asked for it (MEM-06). Same
# figure as the budget of the samples (`limits.max_sample_memory`).
DEFAULT_MEMORY_BUDGET_BYTES = 512 * 1024 * 1024
# What an automatic choice may take. A Report that adds a second pass stays
# well under the memory of the first pass (715 MB with workers, 177 MB for the
# main process, on the 1 M x 34 baseline).
DEFAULT_AUTOMATIC_MEMORY_BYTES = 128 * 1024 * 1024
# Cells of the shared reading up to which an automatic choice is made: the
# limit of the CPU class ``moderate`` below.
DEFAULT_MAX_CELLS = 100_000_000
# Cells of the common reading up to which it is classed ``very_low``, ``low``
# and ``moderate``; above, ``high``. The first pass reads about 8.5 million
# cells a second and analyzes about 1.7 million in one process (baseline of
# lot 0: 34 million cells in 4.0 s and 20.6 s), so 100 million cells is about
# 12 s of reading and under a minute of work: a low cost.
CELL_CLASS_LIMITS = (1_000_000, 10_000_000, 100_000_000)
# The share of the reading phase of the first pass that a second reading
# costs at least: reading and parsing without the work the first pass adds to
# it (baseline: `csv-read` 1.9 s for the 4.0 s of `run.timings.reading`, plus
# the hash that guards the source). Other formats are parsers of their own and
# get 1.0.
READING_LOW_SHARE = 0.6
READING_CELLS_PER_SECOND = 8_500_000
# Seconds, on the upper bound of the estimate, from which a forced second pass
# asks before starting: "several minutes" (R1).
DEFAULT_CONFIRM_SECONDS = 120.0

# CPU ------------------------------------------------------------------------

# Nanoseconds a cell adds to the shared reading, per kind of work, on values
# already parsed. Measured as proxies (`planner_costs.py cpu`, loop overhead
# removed, rounded up: 15, 22, 43, 42, 35, 127 to 154 and 98), the executor of
# lot 7a replaces them with its own measures.
NS_PER_CELL = {
    "dense_counter": 20,
    "length_counter": 30,
    "table": 50,
    "bin": 50,
    "period": 50,
    "distinct_set": 150,
    "matcher": 100,
}
# Upper limits of ``very_low``, ``low`` and ``moderate`` in nanoseconds a cell.
CPU_NS_LIMITS = (50, 200, 800)
# The nanoseconds a cell that a class stands for when only the class is known:
# the top of its range. ``high`` has no top; four times the one below is a
# stated assumption, not a measure.
CLASS_NS = {
    **dict(zip(CPU_ORDER, CPU_NS_LIMITS, strict=False)),
    "high": 4 * CPU_NS_LIMITS[-1],
}




def cpu_class_for(nanoseconds: int) -> CpuClass:
    """The CPU class of an analysis that adds ``nanoseconds`` to each cell."""
    for limit, name in zip(CPU_NS_LIMITS, CPU_ORDER, strict=False):
        if nanoseconds <= limit:
            return name
    return "high"


def cell_class(cells: int) -> CpuClass:
    """The CPU class of reading ``cells`` cells once."""
    for limit, name in zip(CELL_CLASS_LIMITS, CPU_ORDER, strict=False):
        if cells <= limit:
            return name
    return "high"
