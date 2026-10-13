# The character map is computed from the samples, and exactly by a second-pass analyzer

Status: accepted on 2026-10-13 (maintainer, "tout par défaut" on the plan of lot C2 of the Patterns plan).

## Context

C1 counts the classes of the characters in the first pass, which is under guard rails (at most +20% of time, +35% on the
worst width, +10% of memory; the memory margin was already thin). C2 adds what the characters are (the most frequent
ones, their Unicode families, the case of the ends, title case, emoji). Ranking characters needs a table of all of
them, which the first pass cannot afford for every text field.

## Decision

- **Nothing new in the first pass.** The map is a derived analysis, `derived.characters`, computed after the scan from the
  stored samples, each distinct value weighted by its count. It says `basis` `exact` when the samples list every distinct
  value and `sample` otherwise.
- **The second pass makes it exact** with an analyzer `character_profile` that uses the same census on every string. It
  is below the automatic threshold (utility 40) and is not needed (`satisfied`) when the Scan's map is already exact.
- **Bounded and all or nothing** like the tables of C1: a field with more than 65,536 distinct characters or 10,000
  emoji sequences is `limited` and lists nothing.
- **Emoji by a table of ranges in the code**, not a Unicode data file or a dependency.
- **Exposure**: a masked or hidden field has no map; there is no aggregate-only map for it in this lot.

## Consequences

- The first pass costs exactly what it did after C1; the post-pass `derived` takes a fraction of a millisecond a field.
- A forced second pass has one more analysis a text field, answered by the Scan in the common case of a complete sample.
- The emoji table is an approximation and is revised when the standard grows.
- Aggregates (case of the ends, title case) of a masked field from the second pass are left for later.
