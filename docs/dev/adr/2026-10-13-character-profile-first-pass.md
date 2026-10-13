# The character profile is counted exactly in the first pass, with bounded tables that are never partial

Status: accepted on 2026-10-13 (maintainer, "tout par défaut" on the plan of lot C1 of the Patterns plan).

## Context

`string_characteristics` held nine counters. The Patterns work needs more of what the characters of a text are
(classes, composition, tabulations, non-breaking and invisible characters, the replacement character, which punctuation and
symbols occur, how many distinct characters), exact for the whole file and without a second reading. The first pass is under
guard rails (at most +20% of time on the realistic file, +35% on the worst width, +10% of memory), and the profile runs once
for every distinct value of every text field.

## Decision

- **Extend the block, keep its nine names.** The new counters count occurrences of values (weighted, once per distinct
  value) on the raw value; `characters`, `distinct_characters` and `special_characters` complete them.
- **Bounded tables are all or nothing.** The inventory of special characters (256) and the set of distinct characters (1,024)
  are exact up to their bound; beyond it the measure is `limited` with the reason `character_limit` and lists nothing. A
  partial list would depend on the order of the values and would differ between a complete table and a streamed field
  (design 13), and could be read as the whole.
- **A masked or hidden field keeps the counters and loses the distributions** (`disabled`): the decision of design 12.8 for
  characteristics stays, the new distributions of characters are values by another name.
- **The calculation works on shapes.** Each ASCII value is translated by `bytes.translate` to the string of the bits of its
  character classes; values of one shape have the same counters, so a batch pays for its distinct shapes through `Counter`
  and C-level `map`, not for a Python loop. Only values with a special character are read a second time, and the distinct
  characters of a batch are found by deleting the ones already seen. Non-ASCII values take a cached per-character class.

## Consequences

- The cost measured against the base commit is within the guard rails (design 18.8, `docs/dev/scan/benchmarks.md`).
- The report prints the counters and the inventory (at most 20 entries) on the column page; the other consumers ignore the
  new members.
- C2 adds the most frequent characters and the Unicode families on top of the same classes.
- The classes follow Python (`str.isalpha`, `isdigit`, `isalnum`, `isspace`, the Unicode category) and the script of a
  non-ASCII letter follows its Unicode name; a different standard library may classify a rare character differently.
