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

COST_MODEL_VERSION = 4

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
# A set under 50,000 entries grows to four times its fill, so right after a
# growth its table weighs up to 107 bytes an entry (above, twice its fill:
# 53). The firm bound adds the difference for the first 50,000 entries.
SET_SMALL_ENTRIES = 50_000
SET_SMALL_EXTRA_BYTES = 27
# A table of counts: dictionary entry and count, plus the key text (measured 98
# to 101 bytes for a key of 10 characters).
TABLE_ENTRY_BYTES = 90
# The key of the table of frequencies is a tuple of the native type and the
# analytical text: 56 bytes more than the text alone.
FREQUENCY_KEY_BYTES = 56
# Prefix of the key of the state of an exact set: the plan writes it, the
# executor reads the grant of a field from it.
EXACT_SET_STATE_PREFIX = "exact_set:"
# What the empty containers of an exact set cost (three sets and up to 18
# sets of digits of one length, 216 bytes each), however few values it holds.
EXACT_SET_FIXED_BYTES = 4_096
# A compiled matcher measured 2.2 to 4.4 KB.
MATCHER_BYTES = 5_120
# The small result object of an analysis; under 0.001% of any budget.
RESULT_BYTES = 1_024
# Reading the source once: the readers hold at most 8 MiB of batch (a CSV batch
# is closed by size); the worst measured peak is 19 MB (60,000 rows of texts
# up to 8,000 characters), 7 to 8 MB for the other files.
PARSER_RESERVE_BYTES = 24 * 1024 * 1024
# The second pass remembers the cell of this many raw strings per field it
# reads (`secondpass/routing.py`), at about REPLAY_ENTRY_BYTES each: the string,
# its cell and the slot of the dictionary.
REPLAY_MEMO_ENTRIES = 1_024
REPLAY_ENTRY_BYTES = 250
# A column of dates has few distinct strings (a day a value, a few thousand of
# them over a span of years) that repeat from one batch to the next, so the
# period counter remembers many more and reads each date once for the whole
# file; the entry also holds what the date detector made of the string (measured
# 380 to 410 bytes, `planner_costs.py executor`).
PERIOD_MEMO_ENTRIES = 16_384
PERIOD_ENTRY_BYTES = 420
# An exact edge of a bin (a fraction of two integers) and its float, in the
# lists of the bins of a histogram.
EDGE_BYTES = 280

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

# Nanoseconds a cell adds to the shared reading, per kind of work.
#
# The three analyses of lot 7a are measured on the executor
# (`planner_costs.py executor`, insurance-combined.csv, 1 million rows: 841 for
# a counter of integers, 1,661 for a bin, 207 for a length, rounded up). They
# include what the executor does to a cell before it counts it, which is what
# the first pass did: the normalization and the number detector, once per
# distinct string of a batch. A length needs no number, and a field of few
# distinct values costs less than one of decimals.
#
# Lot 7b measures the two exact analyses on the executor too (`planner_costs.py
# executor`, 1 million rows): 373 ns a cell for the exact set of four identifiers
# of one million values (317 on another file), 108 for the table of frequencies
# of four fields of 300 to 900 values, rounded up. The set pays the classifier of
# the first pass on a batch of distinct strings and one key per value; the table
# pays the analytical text of each distinct string of a batch.
#
# Lot 7c measures the last two on the executor (`planner_costs.py executor
# --max-samples`, 1 million rows). A pattern validation costs about 800 ns a cell
# for the field (its distinct strings are read, checked for content and tried
# against the first candidate) and 100 more for each other candidate: a compiled
# possessive regular expression reads an ASCII value in about 150 ns, the token
# loop is kept for the rest. A period counter pays the date detector on the
# analytical text of each distinct string, once for the whole file since it
# remembers the strings of a column of dates (`PERIOD_MEMO_ENTRIES`): 670 ns a
# cell on the five date fields of the baseline, against 1,700 to 2,900 when it
# remembered 1,024 strings and read the same dates again in every batch. Both
# measures include the reading of the cell, and the machine was 30 to 50% slower
# than at lot 7a (counters of integers 1,142 to 1,252 ns for 841): they are
# rounded up, not scaled down.
NS_PER_CELL = {
    "dense_counter": 900,
    "length_counter": 250,
    "table": 120,
    "bin": 1_800,
    "period": 800,
    "distinct_set": 400,
    "matcher_base": 800,
    "matcher": 100,
}
# Upper limits of ``very_low``, ``low`` and ``moderate`` in nanoseconds a cell.
# The first pass spends about 600 ns on a cell of the baseline (20.6 s for 34
# million cells): ``low`` is an analysis that costs no more than that,
# ``moderate`` one that costs up to four times as much.
CPU_NS_LIMITS = (100, 600, 2_400)
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
