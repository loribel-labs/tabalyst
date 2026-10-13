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

COST_MODEL_VERSION = 13

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
# A pair of numeric columns (lot 8a): the co-moments of a pair are six numbers
# and a count, the batch of floats of a column is shared by every pair that
# uses it (``PAIR_FEED_ROWS`` rows, a float object and its slot, 32 bytes).
PAIR_STATE_BYTES = 512
PAIR_FEED_ROWS = 4_096
PAIR_FEED_ENTRY_BYTES = 32
# A cell of the grid of ranks of a pair (lot 16): one counter of a list, the
# integer it points to (28 bytes once it leaves the cache of small integers).
RANK_CELL_BYTES = 40
# A table of a category against a feature (lot 8b): a counter of a cell is a
# dictionary entry keyed by a pair of codes, an example of an exception holds a
# record number and a value of up to 64 characters; the batch of codes of a
# column is shared by every table that uses it (``PAIR_FEED_ROWS`` rows, a code,
# the string it came from and the record number).
TABLE_CELL_BYTES = 150
TABLE_EXAMPLE_BYTES = 250
CODE_FEED_ENTRY_BYTES = 56
# What the coder of a column keeps: the dictionary of its classes, and the code
# of the raw strings it remembered (``REPLAY_MEMO_ENTRIES``, about as large as a
# remembered cell).
CODER_BYTES = 8_192
# The numbers of a column by category (lot 16c): a category keeps its moments, its
# extremes, the partial sums and the counters of its bins (``RANK_CELL_BYTES``
# each); the batch of floats of the numeric column and the codes of the category
# are shared with the pairs and the tables that read them.
STATS_GROUP_BYTES = 1_024
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
# The values with a unit (lot 14) repeat like dates (prices, sizes): the
# extraction remembers as many strings, and an entry also holds what the
# detector made of the string, as for the dates.
MEASURE_MEMO_ENTRIES = 16_384
MEASURE_MEMO_ENTRY_BYTES = 450
# An exact pair of a marker and a number in the table of its group: the slot,
# the count and the key (measured 61 to 85 bytes for an int key, 134 to 170 for
# a Decimal, peak of a growing table included, 10,000 and 100,000 entries), and
# the entry of the table of the whole field merged from the groups at the end.
MEASURE_ENTRY_BYTES = 200
MEASURE_MERGE_BYTES = 100
# A group of the extraction: its numeric accumulator, its dictionaries and the
# entry of its marker (measured 3,048 bytes with a grid of 100 bins), and a bin
# of its grid (a key, a count and its slot).
MEASURE_GROUP_BYTES = 1_536
GRID_BIN_BYTES = 80
# A value kept by the residual tables (lot 15): the slot of the dictionary, the
# list of its count and first record, and the key text (to be added); a text
# remembered with the reading a replayed detector made of it.
RESIDUAL_ENTRY_BYTES = 200
RESIDUAL_MEMO_ENTRY_BYTES = 250
# A distinct value held as a digest by the search for repeated values (lot 15):
# the key, the integer of its record and flag and the slot of the dictionary, in
# the three scenarios (minimum, expected, firm bound); measured 121 to 123 bytes
# an entry for one million identifiers (peak included).
DUPLICATE_ENTRY_BYTES = (110, 140, 200)
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
    # A pair of numeric columns (lot 8a): the nanoseconds a cell of either
    # column adds, the reading of the cell included. Calibrated below. Lot 16
    # measured 2,340 ns on columns of one million distinct decimals (the number
    # detector runs on every string) and the grid of ranks adds 30 to 150 ns; the
    # figure is left as lot 8a set it, since it decides the class of the pair
    # (``moderate``) and so whether a Report picks it, until the matrix of the
    # benchmarks is replayed (lot 20).
    "pearson": 1_500,
    # A table (lot 8b): the nanoseconds a cell of either column of a table adds
    # (the category and the column of the feature), the reading of the cell
    # included, for each feature. Measured on the executor (`planner_costs.py
    # executor`, 1 million rows, tables that share their columns): 445, 412 and
    # 230 ns for each cell handed, 312, 330 and 161 for each cell of each table.
    # The model charges every table both its columns, so it is an upper bound
    # for tables that share one; rounded up, on a machine 10 to 20% slower than
    # at lot 7a.
    "crosstab_pattern": 600,
    "crosstab_length": 500,
    "crosstab_prefix": 300,
    # The values of a column as the classes of a table (lot 16), coded like a
    # category: measured 117 ns for each cell of either column on the executor
    # (`lot16/measure_costs.py`, 1 million rows, one process), like the other
    # features; rounded up as the length, which reads the same analytical text.
    "crosstab_value": 500,
    # The numbers of the values with a unit (lot 14), measured on the executor
    # (1 million rows, one process, the reading of the cell included). The
    # detector runs once for each distinct string the route remembers
    # (`MEASURE_MEMO_ENTRIES`) and once for each distinct string of a batch
    # beyond, so the cost follows the distinct values of the field: 151 ns a cell
    # for about 20 of them, 500 for 1,400 to 1,700, 1,235 for 9,000 and 4,963 for
    # one million (the grid, every value distinct). Rounded up by tier
    # (`measure_tier`).
    "measure_few": 300,
    "measure": 1_500,
    "measure_wide": 5_000,
    # The values that patterns and detectors leave out (lot 15), measured on the
    # executor (`lot15/measure_costs.py`, 1 million rows, one process, the reading of
    # the cell included; the cost follows the distinct values of the field, as for
    # the values with a unit). A pattern with the distinct values of each candidate:
    # 217 ns for 400 distinct values, 501 for 5,000, 844 to 1,749 for one million.
    # The replay of a detector: 357 for 1,500 distinct dates, 831 for 8,000 numbers,
    # 2,051 for 40,000 dates, 1,729 for one million numbers. Rounded up by tier
    # (`residual_tier`); a field with both pays the larger and 30% of the other.
    "residual_pattern_few": 300,
    "residual_pattern": 700,
    "residual_pattern_wide": 2_000,
    "residual_few": 300,
    "residual": 900,
    "residual_wide": 2_500,
    # The search for repeated values (lot 15), measured as above: 897 and 959 ns for
    # a column of one million distinct identifiers (a digest and a dictionary entry
    # for each), and 702 to 734 for each cell of a combination of two columns.
    "duplicates": 1_100,
    "duplicates_key": 1_000,
    # The numbers of a column by category (lot 16c), measured on the executor
    # (`lot16/measure_stats.py`, 1 million rows, one process, the reading of the
    # cell included): 909 to 954 ns for a cell of a category and of an amount of
    # 2 decimals, 1,431 for a column of 4 decimals nearly all distinct, 1,758 for 3
    # decimals, 1,864 for three pairs that share their category; the same session
    # measured 2,520 for a pair of correlated columns. The number detector
    # dominates, as for the pairs. Rounded up to one figure, ``moderate``.
    "category_stats": 2_000,
    # The shape of the numbers of a column (lot 17), measured on the executor
    # (`lot17/measure_costs.py`, 1 million rows, one process, the reading of the
    # cell included) by tier of distinct values as the values with a unit
    # (`shape_tier`): 106 ns for 30 distinct numbers (a histogram: 93), 2,326 for
    # 6,000 (histogram 1,409) and 3,990 to 4,317 for 150,000 to one million
    # (histogram 2,270 to 2,393, the number detector runs on every string). The
    # grid costs as much as the table. The two upper tiers are declared at the
    # top of ``moderate`` (2,400), not at the measure: the class decides whether
    # a forced second pass has to ask (``cpu_over_automatic``), and a class
    # above would make `--deep` ask on any file with a numeric column of a few
    # thousand different numbers, whatever its size. The time estimate is
    # therefore low for such columns, by what the number detector costs that the
    # histogram of the column pays too.
    "shape_few": 300,
    "shape": 2_400,
    "shape_wide": 2_400,
    # The parts of the dates (lot 17), measured as above by tier of distinct
    # strings (`parts_tier`): 213 ns for 730 distinct dates (the distribution over
    # time: 172), 3,019 for 8,640 datetimes (2,772) and 3,717 for one million
    # (3,494: the date detector dominates, as for the periods) and 250 for a
    # column of 672 ambiguous texts (165), whose readings are remembered. The two
    # upper tiers are declared at the top of ``moderate`` for the reason given
    # for the shape.
    "parts_few": 600,
    "parts": 2_400,
    "parts_wide": 2_400,
    # A column followed by position (lot 19), measured on the executor
    # (`lot19/measure_costs.py`, 1 million rows, one process, the reading of the cell
    # included): whether a record has a value, and so only the content test and the
    # count of a slice, 121 ns for 5,000 distinct strings, 136 for numbers and 200 for
    # one million distinct identifiers; and the value itself for a column the scan
    # lists whole, 101 to 106 ns for 10 to 30 values. Rounded up to one figure.
    "drift_presence": 300,
    "drift_values": 200,
    # The columns that miss a value together (lot 19): the nanoseconds a cell of a
    # column of the matrix adds, the test of the cell and its share of the counting
    # of the pairs included, measured the same way on 300,000 rows: 82 ns for 4 and
    # 20 columns, 105 for 100 (4,950 pairs). Rounded up to one figure.
    "matrix": 200,
    # What JSON adds (lot 18), measured on the executor (`lot18/measure_costs.py`, 300,000
    # records of 4, 16 and 44 fields, one process, the sweep of the source included).
    # The lengths of the arrays: 4,028 ns an array on 4 fields and 10,349 on 44, the
    # cost of any route on JSON (a histogram of a number: 4,814 and 8,731) since the
    # router meets every observation of the record, so the count itself adds
    # next to nothing and 300 stands for it. The sets of keys of the objects: one sweep of
    # the observations of each record for the dataset, 296 to 365 ns an observation
    # for the root (every key is marked) and 180 to 323 for an object of a few keys, so
    # an object costs 400 plus 350 for each field of the dataset, declared at the top
    # of ``moderate`` at most (as the shape): the estimate is low for a dataset of
    # more than six fields, and a sweep is shared by the objects of a dataset.
    "array_profile": 300,
    "structure": 400,
    "structure_field": 350,
    # The long texts (lot 18), 150,000 rows, one process: the profile costs 2,266 ns
    # for texts of 230 characters, 3,136 for 260 and 7,055 for 1,000, so about 400
    # plus 7 ns a character; the fingerprints 801, 1,035 and 2,241 for the same texts
    # (550 plus 1.7 ns a character, the digest dominating). Both are declared at the top
    # of ``moderate`` at most, so the estimate is low for texts above 300 characters.
    "text_base": 400,
    "fingerprint": 550,
    # The masks of a sensitive column (lot 18), 500,000 rows: 693 to 957 ns for an
    # email (the analytical text and the mask), 2,493 for an address and 3,737 for a
    # phone number once the detector classifies them and the class is read (the dotted
    # addresses took 6,591 before their own path). Declared at the top of ``moderate``
    # at most, so the estimate is low for a phone number.
    "forms": 1_000,
    "forms_class": 2_800,
}
# The counters of the lengths of the arrays of a field: a dictionary entry per
# length (a key, a count and the slot).
ARRAY_BYTES = 8 * 1024
ARRAY_ENTRY_BYTES = 120
# The sets of keys of an object: the names of the keys it can have and a set (an
# integer with a bit per key, its count and the slot of the dictionary).
STRUCTURE_BYTES = 16 * 1024
STRUCTURE_KEY_BYTES = 200
STRUCTURE_VARIANT_BYTES = 180
# What a character of a text adds to the cost of reading it (nanoseconds), for the
# profile and for the fingerprint.
TEXT_NS_PER_CHAR = 7.0
FINGERPRINT_NS_PER_CHAR = 1.7
# The counters of the words, lines and digits of the texts of a field.
TEXT_BYTES = 4 * 1024
# A distinct value held as a fingerprint by the table of the texts (lot 18): a
# 16-byte key, its count and the slot of the dictionary, in the three scenarios
# (minimum, expected, firm bound); provisional until measured.
FINGERPRINT_ENTRY_BYTES = (100, 130, 180)
# The masks of a sensitive field: the counters, and what an entry adds to the text
# of its mask (a tuple of the native type and the mask, and the count).
FORMS_BYTES = 16 * 1024
FORMS_ENTRY_BYTES = 120
# The counters of a column followed by position: ten slices, and what a tracked
# value adds (a dictionary entry keyed by a tuple, a list of ten counters).
DRIFT_BYTES = 8 * 1024
DRIFT_VALUE_BYTES = 560
# The columns that miss a value together: the flags of a column of a batch
# (``PAIR_FEED_ROWS`` rows, a list of booleans) and its bit set, and a counter for
# each pair of columns (a dictionary entry keyed by a tuple of two numbers, and the
# count; measured 114 bytes for 4,950 pairs).
MATRIX_BYTES = 64 * 1024
MATRIX_COLUMN_BYTES = 2_048
MATRIX_PAIR_BYTES = 160
# The counters of the parts of the dates: weekdays, hours and the readings of
# the ambiguous dates, and what a month of dates adds (a dictionary entry).
PARTS_BYTES = 32 * 1024
PARTS_MONTH_BYTES = 100
# Pairs of a number and its count that the shape buffers before merging the
# float moments of its grid, at 64 bytes each.
SHAPE_BUFFER_BYTES = 8_192 * 64
# Distinct values up to which an extraction is in the tier ``measure_few``, and
# then ``measure`` up to the strings the route remembers.
MEASURE_FEW_DISTINCT = 1_000
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
