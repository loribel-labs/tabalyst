# The exact distinct count keeps one set per kind of key, in the original domain

Status: accepted on 2026-10-09 (maintainer, lot 7b of the Scan and JSON work).

## Context

The Scan counts the distinct original values of a field exactly only up to
`max_distinct_per_field` (100,000 by default). Past it, the cardinality is an
estimate, and the identifier-like fields of a large file are the ones that need
the exact number: it is what tells an identifier (every value distinct) from a
column that only looks like one. The second pass can count them in one more
reading, but the sets must fit in a memory budget the plan can state in advance,
and a limit met on the way must never read as a count.

The specification asks for an inline key or an injective encoding (EXACT-01 to
EXACT-05). In Python without an array library the choices are narrow. Measured
on one million distinct identifiers (`tabalyst-lab/benchmarks/planner_costs.py`, lot 7b):

| Representation | Bytes an entry | Cost of a distinct value |
| --- | ---: | ---: |
| set of strings of 12 characters | 87 | 69 ns |
| set of integers, one set per length (digit strings) | 66 | 237 ns |
| set of integers, ASCII packed with a sentinel | 74 | 241 ns |
| open-addressing table in two `array('Q')` (128 bits) | 36 at rest, 70 at the peak | about 15,000 ns |

## Decision

- The count is taken in the original domain (design section 21), as the
  cardinality of the Scan is: the raw string for a content cell, and
  `(native type, value)` for the native types of JSON. It does not use the
  analytical text, nor the number detector.
- A value goes to one set, chosen by the value alone. A string of 1 to 18 ASCII
  digits is an integer in the set of its length; any other string is itself in
  the generic set; JSON integers, numbers (canonical text) and booleans have
  their own. Nothing is converted when a value does not fit the compact key, so
  nothing can be merged or lost (EXACT-04, EXACT-05). Packed ASCII integers and
  open-addressing tables are not used: the first saves 15% of memory for 170 ns
  a value, the second is two hundred times slower; only the digit strings, the
  most frequent identifiers, get a compact key (25% less).
- The plan charges each field the firm bound of a text at the largest slot, plus
  a supplement for a small set and 4 KB of containers; the executor shares the
  sum of those bounds between the sets of the run. A set that makes the pool
  exceed its total is stopped and freed. Its result is `limited`, reason
  `memory_budget`, with the values read and a proven lower bound, never the
  count (D08). The other analyses and the digest check go on.
- `exact_frequencies` is always a table keyed by `(native type, analytical
  text)`. Counters of integers would merge `7`, `007` and the integer 7, and a
  field of at most 1,000 values makes a table smaller than any dense array. The
  planner drops the `dense_counts` method for it.

## Consequences

- The memory model of the exact set is measured: the bytes the executor charges
  are the bytes the sets hold (65.6 for a digit string, 82.6 to 86.6 for 8 to 12
  characters).
- A value the plan cannot see, whose raw text is much longer than its analytical
  text (blanks around it), can exhaust the bound of its field. The result says
  so; it does not undercount.
- Revisit the encodings if Tabalyst gains a dependency on an array library: a
  sorted run of fixed-width keys would hold an identifier in 8 to 16 bytes.
