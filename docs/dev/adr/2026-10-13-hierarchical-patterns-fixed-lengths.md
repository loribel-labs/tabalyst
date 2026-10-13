# Patterns are discovered as families of fixed-length patterns with a tree of specializations

Status: accepted on 2026-10-13 (maintainer, Porte 0 of the Patterns plan, then lot P1).

## Context

The inference of lot 4a (design 18.12, version 1) returns a flat list of at most 8 exclusive candidates: structures
with ranges of lengths (`9{3,5}`), a generalization ladder, `overlaps`. Probes of 2026-10-12 show what it cannot do: ten
prefixes of two letters give only `XX-9999`; a prefix that covers 99.8% of the values disappears once one other value
exists; the constant `A` of `AK`, `AB`, `AZ` is not found; the occurrences of the sample are ignored; every text column is
inferred and an integer column never is. The maintainer wants a hierarchy (a general structure, then the variants that the
data really use), exact counts of the whole file and a restraint that does not show 30 branches of the same weight.

## Decision

- **A family is a structure, a pattern has a fixed length.** The values are grouped by structure key, merged only at the
  edge of a block (E2). A family has no range rendering: it lists its patterns, one for each combination of lengths that
  the data show (`'INV'-999`, `'INV'-9999`, `'INV'-99999`). The discovery never writes `{m,n}`, `{a|b}` or `?`; those
  belong to written patterns (DEC-032, DEC-034).
- **A tree of specializations plus tables.** Below the patterns, content facets (heads, tails, whole token) become nodes when they
  save more bits than they cost, on distinct values and on occurrences (DEC-023, DEC-029 to DEC-031). A facet that does not
  depend on its parent is a table of the family and not a node (DEC-024). Each value counts for the deepest node; the
  families are disjoint, so `overlaps` goes away. Depth 3 by default, 4 at most.
- **Eligibility first.** A score, reasons and one of four states per field decide whether a tree is built (integers
  admitted, cardinality never a cause of exclusion). A field that is not eligible costs only that.
- **The discovery stays in the `derived` post-pass of the Scan**, so a Scan and a Report show patterns without a second
  reading (OPEN-001).
- **The validation recognizes each value once**, in its family, and counts the node and its ancestors by sums, with tables
  bounded by a byte budget, so the cost per cell does not grow with the number of variants (TR-002). It counts new
  variants of length and of segment while PAT-11 (no new structures) stays. `invalid` is reserved and never written.
- **No compatibility with the flat list.** `derived.patterns` moves to grammar 2 and the Scan format to revision 4 for the
  whole plan; the second-pass document gets one revision. Nothing is migrated (beta).

## Consequences

- `models.py`, `config.py`, `patterninfer.py`, `validation.py`, `schema.py`, the second-pass executor and analyzer, the
  Report views and the documentation change over lots P2 to P8. Consumers of the flat list (`PatternCoder`, `PrefixCoder`,
  `minority_pattern`, the smart sample) are adapted at P7.
- `max_patterns` changes meaning (128 patterns and nodes published for a field instead of 8 candidates).
- The positional structure of characters (FR-016) is out of the V1; the whole prefix, the fixed lengths and the profile of
  the characters cover the need.
- The thresholds of the score (`kappa` 2, `alpha` 1e-6, 0.10, 90%) are calibrated on the reference corpus and belong to the
  version of the algorithm, which enters the cache key.
- Reversing the fixed length per pattern (back to ranges) or the post-pass placement would change the format and needs a
  new ADR.

## Refinements of the lot P4 (2026-10-13)

The content facets, the score and the tree (design 18.12) added choices that the corpus decided; none reverses the above.

- **One facet per token.** A token is read through its heads, its tails or its whole value, whichever saves most bits and is
  published. A tail is read only on a token longer than the three-character chain (a shorter one is read in full by its
  heads; its last letter would be chance, RC-12). The whole value is read for a token of at most four characters that is not
  almost unique (the year of RC-05), so no complete number is published.
- **A whole value is tested alone.** The G test over all the possible tokens has too few expected counts when four digits
  make 10,000 symbols (it did not see the year of RC-05 at 200 and 200 of 400); a value is kept when its binomial tail,
  bounded by Chernoff and multiplied by the number of possible values, is under `alpha`.
- **Composition is the primary facet of a pattern that has it.** A content facet is nested under a structure only if it
  depends on it, as under any node; otherwise it is a table of the family.
- **A table of content is a facet no node reads.** Its cells and its rest add up to the family; the table of lengths still
  completes the patterns to the family.
- **A folded constant keeps at most three characters** of a token that varies; a node folds nothing its pattern did not.
- **`max_depth` counts the pattern as the first level**, so the default of 3 allows the pattern, the nodes that read the
  first or last characters of a token, and the nodes that depend on them.

## Refinements of the lot P6 (2026-10-13)

The validation of the hierarchy (design 20.9) made the following choices; none reverses the above.

- **A node is read by the text it fixes.** `PatternNode.value` is that text (the structure for a node of composition), found in the
  dictionary of the children of its parent, so the work of a value does not grow with the nodes. A node whose only child
  covers 95% of it is merged into that child, which then fixes two things: `PatternNode.also` publishes what the merged nodes
  fixed, and the reader checks it. A reader that looked only at `facet` and `value` read the year of `2022-05` as the month
  of the node `2026-0` (the demo `insurance-customers` caught it).
- **The reader checks the entry against the samples.** It recognizes again the population the discovery read and refuses
  (`scan_mismatch`) an entry whose families, patterns and nodes do not hold the distinct values it publishes. The Report and
  the second pass never validate an entry that was not made from the samples they hold.
- **A new variant of segment is a value the sample never showed, in a facet it showed closed.** It is not a value that is
  merely no cell: a value in the `others` of a node of the discovery was seen, and is `known` (OPEN-012). A facet is closed
  when every value of the sample was a cell (RC-14: eight prefixes, all cells); on an open facet (the digits of a date, the
  tail of a code) a value that is no cell is not remarkable, and the first version of the rule called 22% of the birth dates
  of the demo new when the sample held a hundred of 2,994. It is a new variant of the family, counted in the rest of its
  pattern and in the table of its facet; the lengths a family never showed are a new variant of length, counted in the
  family only.
- **Every facet has a table in the result**, whether nodes or a table of the discovery read it, bounded in bytes
  (`deep.patterns.table_bytes`, 128 bytes a cell); the distinct values of a field are a set bounded in bytes
  (`deep.patterns.distinct_bytes`), and a bucket that did not hold a value says `at_least`.
- **The cost is that of the facets.** A value is tokenized by the regular expression of its structure (ASCII) or by the token
  loop and is read once whatever the nodes; each facet adds a lookup. The model has a cost for the family and one for each facet
  (`NS_PER_CELL`), and the hierarchy costs 1.1 to 2.2 times the flat validation of the lot 7c on the realistic file
  (`benchmarks.md`). Counting the tables by batch would reduce it and is left for later.
