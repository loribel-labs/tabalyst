# Tabalyst Scan design

Phase 0 contract, accepted at gate 0 on 2026-09-26. This document turns the
functional specification of Tabalyst Scan into the contract that the
implementation lots follow. The
specification is maintained privately (`tabalyst-gb`,
`drafts/2026-09-26-scan/Tabalyst-Scan-Cahier-des-charges.md`); its identifiers
(`Dxx`, `EFxx`, `ETxx`, `CAxx`, `Oxx`) are reused here for traceability.

Sections 18 to 21 (2026-10-06) add the contract of the Scan and JSON work:
bottom-k samplers, the shared Scan and Report document, the second pass and the
original value domain. They are Proposed until the maintainer accepts the
baselines of lot 0.

The phase plan, sessions and models are kept in the private maintainer
repository. The contract
tests that make this document executable are in `tests/scan/`.

## 1. Status of decisions

| Label | Meaning |
| --- | --- |
| **Accepted** | Validated by the maintainer. |
| **Proposed** | Phase 0 decision. It becomes Accepted at the phase 0 gate or is amended there. |
| **Deferred** | Deliberately left to a named lot, which must settle it before implementing the affected behavior. |

Changing a Proposed or Accepted rule later is allowed during the alpha, but the
change must update this document and the affected contract tests in the same
lot, with the reason recorded in section 17.

### Decision register

| ID | Topic | Decision | Status | Section |
| --- | --- | --- | --- | --- |
| A1 | Models | Pydantic for finalized results and configuration; plain slotted classes for mutable accumulators. | Accepted 2026-09-26 | 3, 15 |
| A2 | JSON streaming | `ijson` becomes a runtime dependency. Its pure-Python backend guarantees availability; the C backend is used when installed. | Accepted 2026-09-26 | 6 |
| A3 | Migration | New engine in `tabalyst.scanner`, beside the current engine. The report moves onto it in phase 5, then the pandas engine and dependency are removed. | Accepted 2026-09-26 | 3 |
| A4 | CSV errors | `strict` by default (current behavior); `tolerant` is opt-in. | Accepted 2026-09-26 | 14 |
| A5 | Location | Design documents live in `docs/dev/scan/`. | Accepted 2026-09-26 | - |
| O01 | Result schema | Section 16, plus the envelopes of section 8. | Accepted 2026-09-26 | 8, 16 |
| O02 | Paths and identities | Canonical segment lists, documented reversible display syntax, positional CSV identities. | Accepted 2026-09-26 | 4 |
| O03 | JSON datasets and denominators | Collection rules of section 5; denominators from parent container occurrences. | Accepted 2026-09-26 | 5, 7 |
| O04 | Null, empty, blank, markers | Disjoint categories; missing is a derived, configurable sum. | Accepted 2026-09-26 | 7 |
| O05 | Numeric conventions | Exact integer and decimal accumulation; population variance; float64 output. | Accepted 2026-09-26 | 9.4 |
| O06 | Ambiguity | The scan never resolves ambiguity from field evidence; it exposes evidence. Only explicit configuration resolves. | Accepted 2026-09-26 | 12.6 |
| O07 | Error policy | Strict and tolerant behaviors of section 14. | Accepted 2026-09-26 | 14 |
| O08 | Unicode normalization | Normalization version 1 of section 10. | Accepted 2026-09-26 | 10 |
| O09 | Limits | Initial defaults and hard caps of section 11; values revisited after phase 6 benchmarks. | Accepted 2026-09-26 | 11 |
| O10 | Sensitive values | Sensitive fields expose masked shapes by default, through one exposure gate. | Accepted 2026-09-26 | 12.8 |
| O11 | Declarative patterns | Validated Python regular expressions with length caps. | Accepted 2026-09-26 | 12.7 |
| O12 | Reuse and staleness | The report reuses a scan document; a source beside it with another size, or another content (its SHA-256, whatever its modification time), and configured scan settings that differ from the document's are stale and fail; a missing source is accepted with a warning. A document of another engine version is reported with a warning. Amended 2026-09-30 (lot JI-2, inspect design DP-D, 10.2). | Accepted 2026-09-28 (lot 5c); amended 2026-09-30 | 16.6 |
| O13 | Configuration merge | Objects merge, lists replace, unknown keys fail. | Accepted 2026-09-26 | 15 |
| O14 | Detector catalogue | Each detector gets a short specification in [detectors.md](detectors.md) before it is implemented. | Accepted 2026-09-26, file created in lot 3b | 12 |
| O15 | Empty inputs | Zero counts and `not_applicable` measures; never a division by zero. | Accepted 2026-09-26 | 9.9 |
| O16 | Report | The report is a consumer of the scan: it presents technical types, interpretations and evidence, never resolves ambiguity, and masks like the scan. | Accepted 2026-09-27 (lot 5a) | 16.4 |
| O17 | Output writing | Atomic temporary file plus replace; `--force` for existing outputs. | Accepted 2026-09-26 | 16.3 |
| O18 | Migration | See A3. | Accepted | - |
| O19 | Performance targets | Baseline recorded in `benchmarks.md`; targets decided in phase 6. | Deferred to 6 | 13 |
| O20 | Costly exact measures, external storage | Out of the first phases; exact medians only when derivable. | Deferred to 7 | 9.4 |
| O21 | Dynamic plugins | Internal registry only; no external loading. | Deferred to 7 | 12.1 |
| O22 | Approximations | Outside the contract. Any approximation requires a new explicit decision. Amended by O26: approximations are admitted when named. | Accepted (specification); amended 2026-10-06 | 8, 18.1 |
| O23 | Adaptive detection | Adaptive detectors that react to none of the first `detection.warmup_values` distinct values of a field (default 10,000) skip its later values, except probes; skipped values are `not_tested`, never guessed. `number` and `date` are never skipped. Sensitive detectors are skipped like the others for now (open point in section 13). | Accepted 2026-09-28 (lot 6) | 12.2, 13 |
| O24 | Rare detectors | Adaptive detectors that react to at most `detection.rare_share` of the warm-up values (default 0.001) and to none of its second half are skipped too; a rare sensitive detector without a match never is. Probes that react more often than the warm-up allowed raise `detector_skipped_reacted`. | Proposed 2026-09-28 (lot 6) | 12.3, 13 |
| O25 | Batch and parallel execution | Distinct values are processed in batches, detector by detector; CSV records arrive as batches of rows read column by column; large sources hand the values of each field to one worker process. Results never depend on batches or workers (principle 6). | Proposed 2026-09-28 (lot 6) | 6, 13 |
| O26 | Named approximations | An estimate (KMV cardinality, quantiles rebuilt from bins) may be published when it carries `accuracy: "estimated"`, its method and its parameters. It never uses the status `complete`. Principle 1 is amended accordingly. | Proposed 2026-10-06 (Scan and JSON lot 0) | 2, 18.1 |
| O27 | Report with a reduced sample | The Scan keeps the complete bottom-k sample of each field; the Report keeps fewer values (default 100, the smallest priorities, so an exact subset of the Scan's) with the same exact counters, and declares `kept` and `of`. A Report is not a valid input to replan an analysis. Amends the rule that the Report is a strict superset of the Scan. | Proposed 2026-10-06 | 19.4 |
| O28 | Tracking limit and sample size | The exact tracking limit T (`limits.max_distinct_per_field`, default unchanged at 100,000) and the bottom-k size K (`limits.max_samples`, default 10,000, at most T) are separate settings. Amended 2026-10-07: the first version set T = K = 10,000. | Proposed 2026-10-06, amended 2026-10-07 | 18.2 |
| O29 | Report as a document family | `format: "tabalyst.report"` is a superset of the Scan: the base keeps its paths, a common loader reads the base from a Scan or a Report, and the Report adds `report` and `analyses`. | Proposed 2026-10-06 | 19 |
| O30 | One format revision per release | The unpublished revision in progress absorbs the format changes of the work; each lot updates the changelog; the revision increases once, at the release. | Proposed 2026-10-06 | 19.6 |
| O31 | Second pass | `tabalyst scan --deep` forces a second pass written to a separate `<stem>.deep.json`; `tabalyst report` lets the planner decide under deterministic budgets; `tabalyst scan` never starts it. | Proposed 2026-10-06 | 20 |
| O32 | Original value domain | Bottom-k, patterns and smart sampling rest on original values; detectors and listings keep the analytical value, with the domain named in each block. | Proposed 2026-10-06 | 21 |
| O33 | Run block | `run` (start, duration, timings, workers, peak memory) holds what varies between runs on the same source; it replaces `started_at` and `duration_seconds` at the root. | Accepted (in the code since format revision 2) | 16.1 |
| O43 | Targets and the plan of a smart sample | The plan of a smart sample is a document of its own, `SamplingPlan` (`scanner/smart/`), not a member of `AnalysisPlan`: it reads a Scan and, when it is current, the second-pass document, and has its own `plan_id`. It lists the targets of one dataset by family (low cardinality, structured strings, numeric, dates, quality, relations), each with a predicate named by reference into the Scan (never a value of the data), a frequency with its accuracy, a weight and an obligation. The weight is `min(cap, base * (1 + gain * rarity))`, monotone in the share and in the base, capped, configurable (`smart.weights`) and versioned; mandatory targets are the values of an exhaustive enumeration and the confirmed issues. A reserve of ordinary rows (20 % by default) gives way to mandatory targets. The plan announces the readings of the source (scan, second pass, selection) and never merges them; it never runs a second pass by itself. The `smart` settings are a top-level object of the configuration file. | Accepted 2026-10-09 (maintainer, lot 10a) | 15 of the specification, 20.15 |
| O45 | Final integration: stability in the ranking of tables, mirrored pairs, the page of a smart sample, the contract of Explore | A table whose counts are too low to trust (`stable` false) ranks after every stable one in the exploration and so in the automatic choice, and stays listed with its caution (`planner/crosstabs.py`). A pair of columns that is listed in both directions prints its weaker direction right after the stronger one, collapsed (`RelationGroup.mirror`); the document is unchanged. `tabalyst sample --sample-method smart` also writes `<stem>.sample.html`, rendered from the `tabalyst.sample` document alone (`sample_page.py`, `--no-html`, `generate_samples(html=)`), and the page is not part of the format. What Explore consumes of a Scan or a Report is a contract of its own (20.17). The final matrix of 17.2 is measured by `tabalyst-lab/benchmarks/final_matrix.py`. | Accepted 2026-10-09 (maintainer, lot 11; the points were left open at lots 8b and 10b) | 19.3 and 17.2 of the specification, 20.13, 20.16, 20.17 |
| O46 | Lot 12: memory of the first pass and overhead of the Report | Workers load the modules they use and not the whole package (`tabalyst` and `tabalyst.scanner` resolve their public names on first use, PEP 562): 15 MB less in each worker. The first pass starts at most 6 workers (8 before): on the realistic file the time is the one of 8 and the sum of the peaks falls from 900 to 769 MB. The routes of the fields of a CSV file in the second pass run in worker processes (20.18); the document does not depend on their number. `--workers` applies to both passes. The format does not change. | Accepted 2026-10-10 | 13, 20.7, 20.18 |
| O47 | Insight lot 13: gaps closed without reading the source | `numeric.coverage` (`of`, `share`) says which part of `values.count` the numeric block describes; a field that a code detector (`postal_code`, `phone`, `uuid`, `ip_address`) reads for at least half of its eligible values and for at least as many values as the numeric block holds gets `numeric` `not_applicable` with the reason `code_interpretation` (constants `CODE_DETECTORS`, `CODE_MIN_SHARE` in `values.py`). The observation `minority_length` (rules version 2) reads the exact length histogram. The report derives lengths quartiles, frequency tail, dominant unit or marker and decades from existing blocks at render time (`report_measures.py`), without a new member. Scan and Report move to format revision 3 (rule P3: one revision per release). | Accepted 2026-10-11 | 18.13, 18.14, 9.4 |
| O49 | Insight lot 15: the values that patterns and detectors leave out | The analyzer `residual_values` keeps, per field, the values no candidate pattern reads and the values of up to three replayable detectors (`replayable()`: value scope, strings only) that are `invalid` or `not_matched`, with exact counts (a value is tracked from its first appearance, up to `deep.residuals.max_tracked`), the reasons of the invalid ones and, when the source is read, the record of the first occurrence. Each candidate pattern gets an example, its first record and its distinct values over every occurrence (an `ExactSet` of the run's pool). When the Scan holds every distinct value with its exact count the result follows from them, without records (D1); `deep.residuals.records` reads the source anyway. The detector counts are checked against the coverage of the Scan. The record number is handed to the routes (`strings(column, start)`, `string(value, record)`). Second-pass document revision 2 (same release). | Accepted 2026-10-11 (maintainer, lot 15: D1 to D4) | 20.20, 20.5, 20.7 |
| O50 | Insight lot 15: the repeated values of identifiers and keys | The analyzer `duplicates_report` lists the values found more than once in a column of almost all different values (a proven unique column is `already_satisfied`), with exact counts and, when the source is read, the first record. Values are 128-bit BLAKE2b digests with the record of their first occurrence, charged to the pool of the exact sets; a search the pool stops is `duplicates_limited`. A combination of two columns is searched on request only (`AnalysisRequest(partner=)`): `DuplicatesReport` is also a `PairAnalyzer` with `per_field`. `deep.duplicates` holds `max_listed`, `max_tracked`, `records`. | Accepted 2026-10-11 (maintainer, lot 15: D1 to D4) | 20.21, 20.5 |
| O59 | Insight lot 19: a column followed by position in the file | The analyzer `position_drift` cuts the records of a dataset in ten slices of the same size, in file order (`p * 10 // records`), and counts for each the records, the values and the missing ones (`records - values`: a cell the Scan counts as content is a value, so an empty, blank or marker cell, a null and an absent key are records without a value), exactly. `missing_association` is Cramér's V (corrected) of the slice against the presence of a value. When the Scan lists every distinct value with its exact count and there are 2 to `deep.drift.max_tracked` (1,000) of them, `followed` counts each value in each slice, lists the `max_listed` (12) most frequent with their counts per slice and the first slice where they appear, sums up the others and gives Cramér's V of the slice against the value; the table is checked entry by entry against the frequencies of the Scan. It needs 100 records, leaves out a field repeated in a record and, when the Scan left records out (the numbers of the source then have gaps), every field. A column that misses nothing and cannot be followed is `nothing_to_follow`. Utility 40, never automatic. `DriftSettings`, `PositionDriftResult`, `COST_MODEL_VERSION` 12. | Accepted 2026-10-12 (maintainer: "Porte E validée, lot 19") | 20.30 |
| O60 | Insight lot 19: the columns that miss a value together | The analyzer `missing_matrix` counts, for every pair of columns of a dataset that have a value somewhere and lack one somewhere (`matrix_members`: not repeated in a record, values not withheld by exposure), the records where both lack a value, from one bit set a column and a batch (`(a & b).bit_count()`), in the second pass and not in the first. A candidate for each column, a single counting for the dataset (the state `matrix:<dataset>` is shared, so the plan counts it once); the result of a column lists the `max_listed` (10) partners that lack a value most with it, by the share of the records that lack one in either column where both do (Jaccard), exact for every pair. A dataset where more than `deep.missing.max_columns` (100) columns qualify is `too_many_columns`, one with fewer than two has no candidate. Checked against the Scan: the records, and the records without a value of each column. Utility 40, never automatic. `MissingSettings`, `MissingMatrixResult`. | Accepted 2026-10-12 (maintainer: "Porte E validée, lot 19") | 20.31 |
| O61 | Insight lot 18, Q9: counts of a sensitive field without a value (`deep.sensitive`, off by default) | The second pass may count a field whose exposure is `mask` or `hide`, under four rules: **(1)** a closed vocabulary: numbers, masks that the exposure gate already produces and classes of a fixed list (`ip_address`: version and range, `phone`: the zone `fr_01` to `fr_09`, `nanp_geographic`, `nanp_toll_free`, `nanp_premium`, never an area code), never a string derived from a raw value, and no digest or fingerprint for a sensitive field (a hash of a phone number is found by brute force); **(2)** a floor `deep.sensitive.min_count` (5): a mask or a class that fewer values take is summed up (`other_forms`, `other_values`, `other`), and so is the least frequent one listed when what is summed up would hold fewer values than the floor (complementary suppression), so no published figure is about fewer than 5 values; **(3)** nothing per record: no position, no row, no other column, so the drift, the matrix, the pairs, the tables, the repeated values and the texts stay out of a sensitive field; **(4)** never automatic (utility 40), and `hide` gets `exact_distinct` only. `exact_distinct` is the one existing analysis that stops being blocked (its result is two numbers; the plan parameter `exposure` is part of the key). Risks weighed: the exact distinct count and the masks with their counts are already in the Scan (`values.cardinality` is raw and exact, `frequencies` lists masks), so they add an exact count where the Scan has a bound, and the tail of the masks; a differencing attack on a count is the same as on the Scan's; the zone of a French number is a region, which the floor protects. **The setting is off by default** (maintainer, 2026-10-12: "mettre à off la règle des données sensibles"): off, `blocked()` and the plans are what they were, and `sensitive_forms` is relevant to no field. `SensitiveSettings`, `FormsResult`, `COST_MODEL_VERSION` 13. | Accepted 2026-10-12 (maintainer, Q9: "Accepter avec garde-fous", then "off par défaut") | 20.35 |
| O62 | Insight lot 18: the lengths of the arrays and the sets of keys of JSON | `array_profile` counts every length of the arrays of a field exactly (a dictionary length to count, at most `deep.arrays.max_lengths` (10,000) different lengths: the Scan's range decides, a wider one is `array_lengths_too_wide`, equal minimum and maximum is already answered, `lengths_constant`), with the exact quantiles of the histogram. `structure_variants` counts the sets of keys of the objects at a path, as integers with a bit per key the Scan named below it, in one sweep of the observations of each record for the dataset (`StructureAccumulator`, `Router(structures=)`); the sets are tracked up to `deep.structure.max_variants` (1,000) each exactly from its first object, the others summed up and `complete` false. The records themselves are the field `$` of the plan, which the Scan holds as no field (`root_facts`, `Analyzer.roots`, `_root_field`). Checked against the Scan: the arrays, empty arrays, items, shortest and longest; the objects and, for each key, the parents that hold it (`presence.present`). Left out: a dataset whose paths the Scan stopped naming (`untracked_paths`), one object, no key, every key in every object (`uniform_keys`), a table. Utility 40, never automatic. | Accepted 2026-10-12 (maintainer: lot 18, B7) | 20.33 |
| O63 | Insight lot 18: long texts | `text_profile` counts the words (`str.split`), the lines (`str.splitlines`) and the decimal digits of the original texts with constant counters (powers of two for words and lines, tenths for the digits), for a field whose longest value has `deep.texts.min_length` (80) characters or whose values the Scan sampled as long texts. `fingerprint_distinct` counts the distinct values of a field too long for the exact set by the 128-bit BLAKE2b digest the Scan gives its long texts (`fingerprint_based`, never `exact`), lists the `deep.texts.max_listed` (10) most repeated by digest, within the pool of the exact sets (`distinct_limited` with `memory_budget` beyond it), and is answered by the Scan when every value is distinct. Both stay blocked for a sensitive field. Utility 40, never automatic. | Accepted 2026-10-12 (maintainer: lot 18, B8) | 20.34 |
| O64 | Insight lot 18: the Report prints the new cards | The families `structure`, `texts` and `forms`, the accuracy `fingerprint`, the card of the records in the dataset panel only. A card of masks is printed only when each mask is a fixed point of the mask (`mask(form) == form`) and each class belongs to the closed list, whatever the exposure says, and never for `hide`; the digests of a hidden column are not listed. No format changes (second pass revision 2, Report 3). | Accepted 2026-10-12 (maintainer: lot 18) | 20.36 |
| O65 | Patterns lot P1: hierarchical discovery and validation of patterns | The discovery stays in the `derived` post-pass behind an eligibility (score, reasons, four states); `derived.patterns` moves to grammar 2: families (structure keys, merged at the edge of a block) that list patterns of fixed length (DEC-034), nodes by content facets scored in bits on `d` and `o`, tables of facets, budgets `max_values`, `max_families`, `max_patterns_per_family`, `max_patterns`, `max_depth`; the notation of DEC-032; no compatibility with the flat list. The validation recognizes each value once in its family, counts its ancestors by sums, bounds the tables by bytes, counts new variants of length and of segment (PAT-11 kept for structures), writes five outcomes with `invalid` reserved and never written, and keys its cache on the versions of the grammar and of the algorithm and on the settings. Positional structure of characters is not in the V1. Scan format revision 4 for the whole plan. | Accepted 2026-10-13 (maintainer: Porte 0, "tout par defaut") | 18.12, 20.9 |
| O67 | Patterns lot P5: declared keys of the detectors | The `email`, `phone` and `postal_code` detectors (version 2) publish `details.keys`: keys whose meaning they establish (extension and domain read from the right, region and area code or zone, first character and area), counted exactly in the first pass as occurrences and kept by floors (0.5 % then 2 % of the parent, 5 occurrences, budgets 32 and 16, coverage 95 %), with no test against chance. They stay exposed on a masked or hidden field (DEC-027) with no example, profile or row of the sample; `exposure.detector_keys` set to `mask` withholds them. The `domains` block stays masked. | Accepted 2026-10-13 (maintainer, "ok pour tout") | 18.12 |
| O66 | Patterns lot C1: character profile of the strings | `string_characteristics` keeps its nine counters and adds, in the first pass and on raw values, counters of presence by class (ASCII lower and upper case letters, other Latin letters, other letters, ASCII digits, other digits), of the start (upper or lower case), of tabulations, non-breaking spaces, invisible characters and the replacement character, of composition (ASCII only, letters only, digits only, alphanumeric only, letters and digits), the total of characters, the exact count of distinct characters (`distinct_characters`, bound `limits.max_distinct_characters`, 1,024) and the inventory of special characters (`special_characters`, bound `limits.max_special_characters`, 256, 0 turns it off). A bounded table that overflows is `limited` with the reason `character_limit` and no list. A masked or hidden field keeps the counters and the total and has both distributions `disabled`. Format revision 4. | Accepted 2026-10-13 (maintainer: "tout par defaut") | 9.2, 12.8 |
| O68 | Cases lot K1: cases of the observed rules | `values.samples.cases` keeps, for the classes `leading`, `trailing` and `repeated` of whitespace and for each analytical length of a field with a minority length, the exact number of cells and a bottom-k of `max_cases_per_class` (5) original texts with their exact counts, chosen by the hash of 18.3, bounded by `max_case_lengths` (32) and by an eighth of the sample budget, exposure as the samples; the Report reads them in place of the sample; mixed types follow in K2 if the cost allows. | Accepted 2026-10-18 | 18.15 |
| O58 | Insight lot 20: the Report reads the later analyses with the accuracy of each figure | The Report prints, from the document alone, one insight card for each result of the values with a unit, the shape of the numbers, the parts of the dates, the values left out, the repeated values and the numbers by category, and the measures derived from the Scan, each fact, distribution and table with its own kind (exact, estimated, sample, at least). A section Insights (before the Second pass) and a section of the column page hold them; the Dates section says how many ambiguous dates the evidence read. No format changes. The cost model is reviewed with the matrix: the ceiling of the tiers of 17a and 17b, `pearson` and the utility 40 stay; `automatic_stats` goes from 8 to 2 (the second pass of the realistic file: 15.4 s to 11.8 s). Lots 18 and 19 are reported after the milestone. | Accepted 2026-10-12 (maintainer, lot 20; Porte E pending) | 20.29, 20.17, 18.14 |
| O57 | Insight lot 17d.2b: values with a unit read by the evidence of the column | The second pass reads the ambiguous numbers of the values with a unit (`1,250 Kg`, `$4,825`, `12,5 %`) in the convention that the unambiguous values of the same detector (`currency`, `percentage` or `quantity`) prove, by the rule of O56 (`min_evidence`, none proving the other, `ambiguous_convention` wins, `infer_convention`), and under `comma` reads `1.250 Kg` as 1250. The plan decides it from `details.ambiguity.evidence` of the detector in the Scan (`MeasureFacts.convention`) and writes the parameter `number_convention` (part of the key) and the reason `ambiguous_numbers_read_by_evidence`; the reader of the extraction applies it (`CellReader.cells(measure=, convention=)`), the check against the Scan becomes read plus resolved ambiguous equal the coverage, and the result names it (`resolved`, `resolution`). The Scan and the settings are those of 17d.2a; no analyzer other than `measure_extraction` changes. | Accepted 2026-10-12 (maintainer, plan of the session) | 20.28, 20.27, 20.19 |
| O56 | Insight lot 17d.2a: ambiguous numbers read by the evidence of the column | The Scan reads the ambiguous numbers (`1,234`) in the convention that the unambiguous numbers of the column prove, at least `detectors.number.min_evidence` (3) of them and none proving the other, and counts them in `numeric`; under a `comma` proof the strict decimals `d.ddd` (`1.250`) are thousands. The proof comes from the values only: `ambiguous_convention` wins and regroups nothing; spaces prove nothing alone. Decided at the finalization of the field from integers N kept during the Scan (scenario B5 of 17d.1), named in `details.ambiguity.resolution` (`source: evidence`, `resolved`); `coverage` and `formats` still describe the writing. Every later reading (second pass, smart sample, explorations) reads the field in the convention the Scan wrote and never decides again. One rule module, `scanner/convention_rule.py`, shared with the dates. Numbers with a unit: lot 17d.2b. | Accepted 2026-10-12 (maintainer, gate N) | 20.27, 12.6, 9.4 |
| O55 | Insight lot 17c: ambiguous dates read by the evidence of the column | In the second pass the ambiguous dates (`03/04/2020`) are read in the order that the unambiguous dates of the column prove when only one of `DMY` and `MDY` occurs, whatever the separators and the year-first dates, and counted with the others (`DateResolution`, plan parameter `date_order`, `deep.datetime.infer_order`, `deep.datetime.min_evidence`, 3 proofs at least); with both orders or none they stay ambiguous; `ambiguous_order` of the configuration wins. It reverses, for the second pass only, the rule of 12.6 that the evidence is exposed and never applied. | Accepted 2026-10-12 (maintainer) | 20.26, 12.6, 20.10 |
| O54 | Insight lot 17b: the parts of the dates | The analyzer `datetime_parts` counts the dates by year-month (the years and the months of the year are sums of it), day of the week and hour (datetimes and times), counts those after an explicit `deep.datetime.as_of` (never the date of the day), reads the ambiguous dates again under each order (`DMY`, `MDY`: year-months and weekdays) and counts the invalid ones by reason. It reads the classification of the date detector that `temporal_distribution` reads, so the two share one reading. The empty periods and the longest gap are not stored: they follow from the periods or the years of the Scan at render time. `DatetimeSettings` (`as_of` only), `COST_MODEL_VERSION` 11. | Accepted 2026-10-11 (maintainer: "ok avec propositions", R2 to R5), then the bins of equal width replaced by the year-months on 2026-10-12 | 20.25, 20.10 |
| O53 | Insight lot 17a: the shape of the numbers | The analyzer `numeric_shape` counts the distinct numbers of a column in a table up to `deep.shape.max_values` (100,000), then in a grid of bins whose width is a power of two (the grid of 20.19). It gives the skewness and the excess kurtosis (centered float64 sums merged by batch), the outliers of Tukey (exact quartiles and counts with the table, quartiles with certain bounds and counts bracketed by `certain` and `possible` with the grid), the places a number is written with and two views of the spread whose counts are exact: bins at equal ratios (`log`, positive numbers only) and bins at the quantiles of the Scan's samples (`equal_count`). The third bounded reading that the plan imagined to refine the quantiles is given up: the table is exact in one reading. `ShapeSettings`, `COST_MODEL_VERSION` 11. | Accepted 2026-10-11 (maintainer: "ok avec propositions", R1) | 20.24, 20.7, 20.19 |
| O52 | Insight lot 16c: the numbers of a column by category | The analyzer `category_stats` (a `PairAnalyzer`, directed: the category is the `field`, the numeric column the `partner`) describes a number for each value of a category over every row: count, extremes, sum, mean, population standard deviation, signs and a histogram in bins common to all the categories, with quantiles estimated from them with certain bounds. The arithmetic is float64 (the numbers are read as the correlations read them, `ColumnFeed`), the counts exact. A pair is rated by the square root of the corrected correlation ratio (epsilon squared, Kelley) on the row sample, chosen by itself from 0.45 (`deep.stats.automatic_stats`, 8). `Relations.stats`, `Budgets.automatic_stats`, `deep.stats`, `COST_MODEL_VERSION` 10. | Accepted 2026-10-11 (maintainer: "ok avec propositions", S1 to S6) | 20.23, 20.12, 20.13 |
| O51 | Insight lot 16 (16a and 16b): the line and the rank of a pair, tables of a category against the values of another, exceptions bounded, rules a user gives | `pearson_correlation` (version 2) gives `slope`, `intercept` and `r_squared` from the co-moments and, with `deep.pearson.rank_bins` (64, 0 off), a `rank` member: the Spearman coefficient estimated from a grid of bins cut at quantiles of what the Scan kept, with certain bounds (the deviation of the true centered ranks from the mid-ranks is orthogonal to them and bounded by the sum of n(n^2-1)/12 over the bins, so the angle between the rank vectors moves by at most the sum of two arctangents). The exploration rates a pair by the larger of the scores of the linear and the rank coefficient of the sample. `category_crosstab` has a fourth feature, `value` (the most frequent values of the column, coded like a category), read in one direction by the exploration (the column with fewer distinct values is the row axis); `deep.crosstab.max_exception_cells` bounds the listed exceptions and `exceptions.complete` says whether all are listed; `AnalysisRequest.rules` gives rules to check, each in `provided_rules` with its counter-examples (provenance `provided`). The analyzer `category_stats` is O52. | Accepted 2026-10-11 (maintainer: "ok avec propositions", Q1 to Q5) | 20.22, 20.12, 20.13 |
| O48 | Insight lot 14: numbers of the values with a unit | The analyzer `measure_extraction` (second pass only, Q7) reads the values of a field that the `currency`, `percentage` or `quantity` detector reads for at least half of its values, with that detector of the Scan's configuration, and gives three levels: the metrics of a numeric field (the members of `numeric`, a histogram and its quantiles) for every parsed value, the same for each marker or unit (`max_groups`, the rest in `other`), and the markers as an enumeration. Nothing is converted. Numbers are counted exactly per marker up to `deep.measures.max_values` distinct pairs, then every group goes on in bins whose width is a power of two (exact counts and moments, estimated quantiles; the width depends on the range only). Counts are checked against the detector of the Scan, exactly when it tested every value, bounded by `not_tested` otherwise. The second-pass document moves to revision 2. | Accepted 2026-10-11 | 20.19, 20.5, 20.7 |
| O44 | Selection of the rows of a smart sample and its report | The selection reads the source once, with the configuration the Scan recorded, and tests each row against the targets of the plan through tests resolved from the Scan before the reading (`scanner/smart/evaluate.py`); a target that cannot be resolved is left out with a reason, never guessed. It keeps a bounded pool of whole candidate rows (at most `candidates_per_target` for each target, the best by a seeded hash of the position, one copy of a row whatever the targets it holds) and a bottom-k reserve of ordinary rows, in a byte budget; a row the budget turns away is counted and never shortened. A greedy cover then chooses the rows: the mandatory targets first, then the weight not yet covered; what is left of the size goes to ordinary rows. The rows are written in the order of the source after the digest of the reading agrees with the Scan's. The report is a document of its own, `tabalyst.sample` (0.2.0 revision 1), with the plan, the selection and the coverage of the catalog of targets by family and weighted, the missed targets with their reason, and a verification of every exact count of the plan against the rows found. The time of the selection is estimated apart from the plan and asks for a confirmation as a second pass does. | Accepted 2026-10-09 (maintainer, lot 10b) | 15 of the specification, 20.16 |
| O42 | Help with stratification | The plan can carry advice on stratified sampling (`AnalysisPlan.stratification`, from `Stratify`), computed from the Scan alone and never read from the source: for each column whether it is a key (not an identifier, not nearly unique, 2 to 50 strata, no exposure), its strata (distinct original values plus one for the missing values) with their basis (`exact`, `estimate`, `bound`), the rarest and largest shares, the sample size from which the rarest stratum cannot get zero, and with a sample size the strata the classic allocation leaves without a row; for each combination asked for a saturating bound of the product of the strata, capped by the records, an estimate apart and labelled, the combinations the row sample holds (exact when it holds every row), a risk and suggestions. The classic `stratified` mode keeps its meaning (STRAT-01): proportional, no minimum of one row, the same rounding, now in `scanner/stratify.py`; it gains several fields (tuple keys), a ceiling of 100,000 strata that stops the scan with an error (STRAT-08) and a balance of known, sampled and uncovered strata (STRAT-02). The advice takes no part in the choice of the analyses and is not written in the second-pass document. | Accepted 2026-10-09 (maintainer, lot 9) | 14 of the specification, 20.5, 20.14 |
| O41 | Tables of a category against a feature | A table is a candidate of `category_crosstab`: the category is its `field`, the column of the feature its `partner`, the feature (`pattern`, `length`, `prefix`) a parameter, and the order matters (`>` in the id). The classes come from the Scan alone, at the plan and at the run, and end with the explicit class `other`, so nothing creates an axis while the source streams (REL-12). Rows left out are counted by cause and `rows = counted + excluded` is checked. The planner ranks by the bias-corrected Cramér's V on the row sample, picks by itself the best feature of two columns (`redundant_feature` for the others) and at most eight tables; the result gives the counts with their margins, the coverage and the purity of each category in both directions, the exceptions with exact counts and their first rows, Cramér's V (never 0 for lack of data, `stable` or not) and candidate rules. A `PairAnalyzer` replaces the special case of the correlation in the planner. The report prints one block per pair of columns in a Relationships section. | Accepted 2026-10-09 (maintainer, lot 8b) | 18.14, 20.2, 20.5, 20.12, 20.13 |
| O40 | Pairs of numeric columns | A pair is a candidate with a `partner` and an `exploration`, the score the row sample gives it. The planner scores all the pairs of the eligible columns on the sample when it makes the plan (no change to the Scan, no cost to the first pass), bounded by columns and by pairs times rows compared (COST-05), lists the best (`max_candidates`) and describes what it did in `relations`. `pearson_correlation` counts the common rows of a pair over the whole source with stable co-moments merged by batch, `pairwise_complete`, and gives an undefined result with its reason, never 0, when the rows or the variance are not enough (REL-07 to REL-09). A complete sample of a CSV file answers without reading. Pairs are ranked by the lower end of a 95% interval and the planner picks eight at most by itself. | Accepted 2026-10-09 (maintainer, lot 8a) | 20.2, 20.4, 20.5, 20.12 |
| O39 | Patterns, dates and the second pass of the Report | `pattern_validation` counts every occurrence of the original domain against the candidates of the Scan with the matcher of the inference (a possessive regular expression for an ASCII value, the token loop for the rest), exclusively by the most specific reader, and reconciles `matched + other + excluded = values`; it reads no source when the Scan holds every distinct value with its exact count. `temporal_distribution` counts the dates the first pass parsed per calendar day, month or year, by the date as written (no conversion of the offset), ambiguous values counted apart and never placed. `tabalyst report` runs the second pass by itself on the planner's decision (`--deep` forces it, `--yes` and exit code 3 as for `scan --deep`, `deep.mode` for scripts), and embeds the result under `analyses`, with what it left out and why; a Report of a scan document reads no source unless forced. | Accepted 2026-10-09 (maintainer, lot 7c) | 18.12, 20.1, 20.2, 20.4, 20.5, 20.9, 20.10, 20.11 |
| O38 | Exact distinct and exact frequencies | `exact_distinct` counts the distinct values of the original domain (section 21) exactly, with the values read (V) and the redundant occurrences (V minus D). Each value goes to one set chosen by the value alone: strings of up to 18 ASCII digits as integers in a set per length (so `00123` and `123` stay apart), any other string as itself, and the native types of JSON in sets of their own. A value outside the compact key is not converted, it is in the generic set. The sets share the bytes the plan gave them and the field stops, with a lower bound that is never presented as the count, when they cannot hold it (D08). `exact_frequencies` keeps a table keyed by native type and analytical text, always a table: counters of integers would merge `7`, `007` and the integer 7, and a field of at most 1,000 values makes a table smaller than any dense array. Both are `available`; `EXECUTABLE` is derived from the registry. | Accepted 2026-10-09 (maintainer, lot 7b) | 20.2, 20.4, 20.5, 20.6, 20.8 |
| O37 | Executor of the second pass and its document | `scanner/secondpass/` reads the source once, with the configuration the Scan recorded, replays the first pass's reading of each cell (same normalizer, classifier and number detector) and counts for the two analyzers that have an executor: `numeric_histogram` (exact counters of a small integer domain, or bins with exact edges) and `length_distribution`. Each result is checked against the counts of the Scan and fails alone on a disagreement; nothing is published before the digest of the reading is compared with the Scan's. The result is the separate document `tabalyst.scan.deep` (`<stem>.deep.json`, `deep.json` beside the shared scan), keyed by what each analysis depends on and reused in part. Its settings (`deep.bins`, `deep.bin_strategy`) are outside `ScanConfig`, so changing them never makes a Scan stale. The Python entry is `run_second_pass` and `generate_deep`, not `tabalyst.scan(..., deep=True)`, which would change the return type of the first pass. | Accepted 2026-10-09 (maintainer, lot 7a) | 20.1, 20.2, 20.4, 20.7 |
| O36 | Costs, budgets and confirmation | The cost model is calibrated on measures (`tabalyst-lab/benchmarks/planner_costs.py`, the baselines of lot 0) and versioned (`cost_model_version`). Two memory levels: an automatic choice stays within 128 MiB, a request or a forced plan up to a hard budget of 512 MiB that nothing lifts (MEM-06). A selection beyond an automatic limit, or whose estimated time may reach 120 s on its upper bound, requires a confirmation; the time is an estimate kept out of the plan. Before a second reading the plan must belong to the Scan, the source must be readable and of the recorded size, and its digest is compared at the end of the reading. | Accepted 2026-10-08 (maintainer, lot 6b) | 20.2, 20.3, 20.6 |
| O35 | Analyzers and planner | `scanner/planner/` holds a registry of analyzers and a planner that reads a Scan (never a Report, never the source) and returns a deterministic plan: candidates with applicability, costs (memory in three scenarios, CPU class), utility and a decision (`selected`, `already_satisfied`, `rejected`) with a reason code; selection under a firm memory budget; shared states counted once. The planner chooses on merit; `available` says whether an executor exists. Costs and thresholds were provisional until lot 6b (O36). | Accepted 2026-10-08 (maintainer, lot 6a) | 20.5 |
| O34 | Observations and adaptive normalization | `observations` sits beside `derived` in the base: observations of versioned rules (`informational`, `candidate_anomaly`, `confirmed_issue`) apart from the limits of the scan, with `has_observations`, `has_quality_issues` and `has_limits`. A normalization stage that changed nothing takes the count of its input (`equals`), even after the table was released. | Accepted 2026-10-08 (maintainer, lot 4b) | 10, 18.13 |

## 2. Principles

1. **Complete and exact, or explicitly limited or estimated.** Every record in
   the analyzed scope is read. A measure is either exact for its declared
   population (`complete`) or carries another status. An estimate is never
   presented as an exact value: it is published only with `accuracy:
   "estimated"`, its method and its parameters (O26).
2. **Facts, not verdicts.** The scan records observations, interpretations and
   their evidence. Quality judgments, issues and presentation choices belong to
   consumers such as the report.
3. **Raw values are never modified.** Normalization produces analytical forms
   and counters only.
4. **One engine, several readers.** Readers understand formats; the engine and
   detectors never test the source format.
5. **Bounded state.** Memory depends on configured limits and the number of
   tracked fields, not on the number of records.
6. **Same results whatever the internal strategy.** Execution modes and caches
   (section 13) change speed, never results.
7. **Smart by default, explicit when costly.** An automatic mode runs an extra
   operation only when its benefit is established and its cost is low, under
   deterministic budgets (section 20.2). Forcing a costly operation shows its
   estimate and asks first. The API never prompts. No long operation runs
   silently.

## 3. Package, public API and models

The engine lives in the `tabalyst.scanner` package. The name avoids a
`tabalyst.scan` module that would be shadowed by a future top-level
`tabalyst.scan()` function.

```python
from tabalyst.scanner import ScanConfig, ScanResult, scan

result: ScanResult = scan("customers.json", config=ScanConfig())
document = result.model_dump(mode="json")
```

`scan(source, *, config=None, registry=None, on_progress=None,
on_record=None)` reads one source and returns a finalized `ScanResult`. It
writes nothing. `registry` replaces the default detector registry (section
12.1). `on_record` receives each analyzed `Record` (section 6), in reading
order, before the engine, so a consumer gets record-level facts in the same
pass; it must not modify the record (lot 5a). Since lot 5c the report reads
record facts from the `records` block of each dataset (section 9.10) instead. Phase 4 adds
file output, batches and the top-level alias `tabalyst.scan`: since lot 4, `tabalyst.scan`,
`tabalyst.ScanConfig` and `tabalyst.ScanResult` are exported by the package,
with `tabalyst.generate_scans()` (section 16.3).

Proposed layout, free to adapt as long as the boundaries hold:

```text
src/tabalyst/scanner/
|-- __init__.py        scan(), ScanConfig, ScanResult
|-- api.py             orchestration: reader selection, engine, timing
|-- config.py          ScanConfig, defaults and hard caps
|-- paths.py           segments, FieldPath, display and parsing
|-- observations.py    Observation, Record and reader stream items
|-- readers/           base protocol, csv_reader.py, json_reader.py
|-- engine.py          ScanEngine: datasets, dispatch, finalization
|-- structure.py       per-dataset path registry, presence, structural limits
|-- field.py           FieldScanner: counters, value tables, execution modes
|-- values.py          frequency tables, samples, first/last values, budgets
|-- measures.py        numeric, string and boolean accumulators
|-- normalization.py   normalization version 1
|-- diagnostics.py     diagnostic collector
|-- exposure.py        sensitive value gate
|-- technical.py       technical type inference
|-- workers.py         worker processes of parallel scans (lot 6)
|-- planner/           registry of analyzers and plan of the second pass (lot 6a, 20.5)
|-- detectors/         base, registry, shape classifier, built-ins, patterns
`-- models.py          Pydantic result models
```

Rules:

- No pandas import anywhere in `tabalyst.scanner` (ET04).
- Accumulators are mutable, slotted Python classes. `finalize()` turns them into
  immutable Pydantic models (D08). Nothing mutates a model after finalization.
- Result models use `extra="forbid"`, like `tabalyst.models`.
- Fatal problems raise the existing public exceptions: `InputError` for sources,
  `ConfigurationError` for configuration.

## 4. Paths and identities (D06, O02)

### 4.1 Canonical form

A path is a tuple of segments, relative to the record root:

| Segment | Meaning | JSON form |
| --- | --- | --- |
| key | Member of an object | `{"key": "orders"}` |
| items | Any element of an array; indices are not distinguished | `{"items": true}` |
| column | CSV column at a 1-based position | `{"column": 3}` |

The empty path is the record itself. The canonical JSON form of a path is the
list of its segments. It is the identity used to compare fields across results.

### 4.2 Display syntax

The display syntax is documented and reversible so it can also be used in
configuration and on the command line:

```text
absolute  := "$" segment*
relative  := ( identifier | quoted | "[]" ) segment*
segment   := "." identifier | quoted | "[]"
quoted    := "[" json-string "]"
identifier:= [A-Za-z_][A-Za-z0-9_]*
```

- Keys matching `identifier` are written bare; every other key is written as a
  JSON string in brackets, so `a.b`, `c[]` or an empty key never collide with
  nested paths.
- The record root displays as `$`. Dataset identifiers are absolute paths such
  as `$`, `$[]` or `$.customers[]`; field displays are relative, such as
  `orders[].amount`.
- CSV columns display as their header name when it is non-blank and unique in
  the header, otherwise as `name#position` (`name#3`, `#4` for a blank header).
  CSV displays are labels only; the column segment is the identity.

### 4.3 Field identifiers

`id` is unique within one dataset result. CSV fields use `column_<position>`,
as the current profile does. JSON fields use `f<n>` in order of first
discovery. Identifiers are local to one result; use `path` across results.

## 5. Sources, datasets and records (D07, D11, O03)

| Concept | Definition |
| --- | --- |
| Source | One input file, with its format and identity. |
| Dataset | A collection of records within a source. |
| Record | One member of a dataset: a CSV data row, or one element of a JSON collection. |
| Field | A path relative to the record root, with everything observed at it. |
| Value | One occurrence at a field, with its native type. |

### 5.1 CSV

A CSV source has exactly one dataset, `rows`, of kind `table`. The first record
is the header. Each data record is represented as an object whose members are
the column segments, so presence rules are shared with JSON.

### 5.2 JSON

Automatic mode (default):

| Root | Datasets |
| --- | --- |
| Array | One dataset `$[]` of kind `collection`, whose records are the array elements. |
| Object | One dataset `$` of kind `document` with one record, the root object. Every array reachable from the root through objects only, at depth `json.discovery_max_depth` or less (default 3), also becomes a `collection` dataset. |
| Scalar | One dataset `$` of kind `document` with one record, the scalar. |

- In the document dataset, a promoted array is a field of native type `array`
  whose `collection` names the dataset holding its elements; its elements are
  not traversed again there.
- Arrays inside records are never promoted automatically: `orders[]` inside a
  customer stays a field of the customer dataset (EF07, CA04).
- Records may have any native type. Object members are fields; array elements
  are the `[]` field of the record; scalar records are analyzed at the root
  field `$`. The root field (empty path) is listed only when at least one
  record of the dataset is not an object; `record_types` always gives the
  native types of the records.
- An empty collection is a dataset with zero records.
- The document dataset has `collection_path: null`; its promoted arrays are
  listed after it, in document order.
- Promotion needs the array to be analyzed in the document: an array deeper
  than `limits.max_depth` is truncated there and never promoted.

Explicit mode: `json.collections` lists absolute paths, which may cross arrays
(`$.customers[].orders[]` gathers every order into one dataset). Only the
selected collections are analyzed; the rest of the document is outside the
requested scope, which the result states (EF05). Overlapping selections (one
path extending another), equivalent spellings of one path and an empty list are
configuration errors. Dataset identifiers and `scope.collections.requested`
use the canonical spelling (`$["a"][]` becomes `$.a[]`). Every requested
dataset is listed, in requested order;
when no array exists at its path, it has zero records and a
`json_collection_not_found` warning.

Every value of a JSON source is read; a source is UTF-8, optionally preceded
by a byte order mark, which RFC 8259 lets parsers ignore (`source.encoding` is
then `utf-8-sig`). An object with a duplicate key makes its record malformed:
which value applies is ambiguous and presence would exceed its parent count.
Under `strict` it is fatal; under `tolerant` the record is excluded with
reason `duplicate_key` (section 14). A string or key holding a lone
surrogate escape, such as `"\ud800"`, is not valid Unicode (I-JSON, RFC
7493): the source is invalid. The pure-Python backend of `ijson` keeps such
surrogates, and Tabalyst rejects them; the compiled backend rejects lone low
surrogates itself but replaces a lone high surrogate with `?` before
Tabalyst sees it, a known limitation of that backend.

The compiled backend of `ijson` crashes the process (access violation) on an
integer longer than `sys.int_max_str_digits` (4,300 digits by default) in some
parser states. Before parsing, the reader looks for a run of more digits than
that limit, at memory speed; when one exists, even inside a string, the file
is parsed by the pure-Python backend, which reports an `InputError`. A number
whose exponent `Decimal` cannot represent is an `InputError` too. Parser
messages quoted in errors are cut at 200 characters.

The JSON reader tracks its own path stack. It must not use `ijson` prefix
strings as identities, because they join keys with dots and would merge `a.b`
with `a` > `b` (specification scenario 4).

At most two passes over a JSON source are allowed; the target is one.

### 5.3 JSONL (lot JI-4)

A source ending in `.jsonl` or `.ndjson` is one dataset `$[]` of kind
`collection` whose records are its object lines (`source.format` `jsonl`). The
reader parses each line on its own and gives each record the observations it
would have as an element of a JSON array, with the same flatten and depth rules.
Its rules, exclusion reasons and policy are in inspect design section 9;
`limits.max_line_bytes` bounds a line. Locations are `{record, line}`. The
source is read once, hashed while reading.

## 6. Reader to engine contract (D04, D05, ET01, ET02)

Readers are synchronous iterators. They yield three kinds of items:

```python
@dataclass(frozen=True, slots=True)
class DatasetOpened:
    dataset: str                 # "rows", "$", "$[]", "$.customers[]"
    kind: Literal["table", "document", "collection"]
    collection_path: FieldPath | None
    fields: tuple[DeclaredField, ...] = ()   # known before any record
    container: tuple[str, FieldPath] | None = None   # ("$", customers): field
                                 # whose arrays hold the records (field.collection)

@dataclass(frozen=True, slots=True)
class DeclaredField:
    path: FieldPath
    name: str                    # CSV header name
    display: str                 # CSV label: "name", "name#3", "#4"

@dataclass(slots=True)
class Record:
    dataset: str
    index: int                   # 1-based within its dataset
    location: Location           # CSV physical lines, JSON element index
    observations: list[Observation]
    depth_truncated: int = 0     # observations below limits.max_depth, not emitted

@dataclass(frozen=True, slots=True)
class Notice:                    # technical event forwarded as a diagnostic
    code: str                    # "json_collection_not_found"
    level: Literal["error", "warning"]
    message: str
    dataset: str | None = None
    location: Location | None = None

@dataclass(frozen=True, slots=True)
class RecordExcluded:
    dataset: str
    index: int                   # counts every record read, excluded or not
    location: Location
    reason: str                  # "width_mismatch", "record_too_large"
    code: str                    # diagnostic code, "csv_width_mismatch"
    message: str                 # diagnostic message, same for every record
```

```python
class Observation(NamedTuple):   # immutable; a named tuple is cheap to build (lot 6)
    path: FieldPath              # relative to the record root
    type: NativeType             # null, boolean, integer, number, string, object, array
    value: object                # str, int, Decimal, bool or None; array length for arrays

@dataclass(slots=True)
class RecordBatch:               # lot 6: records of a table with declared fields
    dataset: str
    start: int                   # index of the first record; the others follow
    rows: list[list[str]]        # one string per declared field, in order
    lines: list[int]             # first physical line of each record
```

A reader of a dataset with declared fields may stream its records as
`RecordBatch` items instead of `Record` items: each row stands for a record
that observes its root as an object, then each declared field once, as a
string, so the engine reads the batch column by column with the same results.
The CSV reader does (lot 6). `scan(on_record=...)` still receives one
`Record` per record, built from the batch. A reader that builds paths should
reuse one path object per logical path (the JSON reader does): the engine and
record digests look paths up by identity first.

- Every record starts with an observation at the empty path describing the
  record itself. CSV records use type `object`.
- Observations appear in document order; a container is observed before its
  children. Every object and array occurrence is observed, including empty ones.
- A reader never emits absence observations; absences are derived (section 7).
- Native types follow the source's lexical form: in JSON, `1` is `integer`,
  `1.0` and `1e3` are `number` (read as `Decimal`), `"1"` is `string`. Every CSV
  value is a `string`.
- After iteration, `reader.summary()` returns the source description completed
  during reading: bytes read, SHA-256 computed while streaming, encoding, CSV
  header and delimiter.
- A CSV location is the record index and the first physical line of the
  record; a JSON location is the record index and the 0-based element index in
  its array (none for the document record).
- Records of different datasets may interleave: the JSON reader yields each
  collection element as soon as it ends and the document record last.
- A reader raises `InputError` for fatal problems (section 14). Readers
  receive the configuration and apply the error policy themselves: under
  `strict` they raise a format-specific `InputError`; under `tolerant` they
  yield `RecordExcluded`, whose `code` and `message` become the diagnostic, so
  the engine never tests the source format.
- Declared fields are registered before any record, in order, so a CSV with
  only a header still lists its columns, with the header names and labels
  that only the reader knows. Other fields are discovered from observations.
- Records are materialized one at a time. `limits.max_record_observations`
  protects against a single huge record; it counts the observations the reader
  emits, so content truncated by `limits.max_depth` does not count. Readers
  apply both limits, so they never build paths deeper than `max_depth`; the
  engine applies `max_fields`.

## 7. Presence and value categories (D12, D13, EF06-EF10, O04)

For a field at path `P` with parent path `parent(P)`:

| Counter | Definition |
| --- | --- |
| `occurrences` | Observations at `P`, whatever their native type. |
| `presence.parent_type` | `object` for key and column segments, `array` for items segments, `record` for the root field. |
| `presence.parent_count` | Objects observed at `parent(P)` for keys and columns; arrays observed at `parent(P)` for items; analyzed records for the root field. |
| `presence.present` | Equal to `occurrences`. |
| `presence.absent` | `parent_count - present` for keys, columns and the root field; `null` for items. |
| `native_types` | Occurrences per native type; only types seen are listed. |
| `first_record` | Index of the first record with an occurrence, or `null`. |

A key is absent only where its parent was an object that could have contained
it. When `address` is `null` or missing, `address.city` is neither present nor
absent in that record; the situation is visible at `address`. This keeps
presence exact for fields that appear late, without emitting absence events
(CA03).

String occurrences fall into exactly one category:

| Category | Rule, evaluated in this order |
| --- | --- |
| `empty` | The raw string is `""`. |
| `blank` | The raw string contains only whitespace (`str.isspace()`). |
| `marker` | The raw string stripped of whitespace equals a configured `values.null_markers` entry, case-sensitively unless configured otherwise. |
| `content` | Every other string. |

Invariants, checked by the contract tests:

- `sum(native_types.values()) == occurrences`
- `strings.empty + strings.blank + strings.marker + strings.content == strings.count == native_types["string"]`
- `values.count == strings.content + integer + number + boolean`

`values` is the population of analyzable scalar values used by frequencies,
normalization, detectors and statistics.

`missing.count` is a derived sum over the categories named in
`values.missing` (default `absent`, `null`, `empty`, `blank`, `marker`). The
result always lists every component and the definition used, so consumers can
recompute another definition. The default reproduces the current report,
where whitespace-only cells are missing.

Arrays add an `arrays` block to their field: `count`, `empty`, `min_length`,
`max_length` and `total_items`.

## 8. Measure envelopes (EF19, specification 7.4)

Plain counters that can never be limited (presence, native types, string
categories, normalization change counters) are plain integers. Every measure
that can be limited, disabled, inapplicable or failed is wrapped:

```json
{"status": "complete", "value": 42}
{"status": "limited", "reason": "distinct_limit", "limit": 10000, "lower_bound": 10001}
{"status": "not_applicable", "reason": "no_values"}
{"status": "disabled"}
{"status": "failed", "reason": "detector_error", "diagnostic": 3}
```

| Status | Meaning | Fields |
| --- | --- | --- |
| `complete` | Exact for the declared population. | `value` |
| `limited` | Stopped or not stored because of a limit. | `reason`, `limit`, optional `lower_bound` |
| `not_applicable` | Meaningless here, for example no values. | `reason` |
| `disabled` | Turned off by configuration. | none |
| `failed` | A technical failure prevented the measure. | `reason`, `diagnostic` (index in `diagnostics`) |

`disabled` is distinct from `not_applicable`, as the specification requires.

**Proven bound rule (ET10, CA08, CA09).** `lower_bound` is published only when
it is proven by observation: `L + 1` after `L + 1` genuinely distinct stored
values, or the stored distinct count plus one when a value too long to store
was seen (such a value differs from every stored one). Truncated values or
hashes are never used as identity proofs.

A scan can reach the end of its scope with limited measures and still have
status `complete`; scan status and measure status are independent.

## 9. Measures per field

Each block below names its population, its lot and whether it is plain or an
envelope. The JSON layout is summarized in section 16.

### 9.1 Values and frequencies (lot 2a)

`values.count` is a plain counter provided from lot 1a; the other members of
`values` arrive in lot 2a.

- The raw frequency table stores each distinct value as `(native type,
  canonical text)`, so the string `"123"` and the integer `123` are distinct
  (EF10, CA05). Canonical text is the raw string for strings, `true`/`false`
  for booleans and `str()` of the parsed value for JSON numbers. `ijson` does
  not keep the source text, so it matches the source except for the exponent
  spelling (`1e3` becomes `1E+3`) and the integer `-0`, which becomes `0`.
- Values are output as `{value, type, ...}`, where `value` is always the
  canonical text of the analytical value (a JSON string) and `type` its native
  type.
- `values.cardinality`: envelope, exact distinct count of the original values
  (raw, decoded, before any normalization stage: section 21). It carries
  qualifiers (lot 1a): `complete` has `accuracy` (`exact`), `domain`
  (`original`) and `identity_accuracy` (`exact`: values are compared whole).
  `limited` has `domain`, `identity_accuracy`, `upper_bound` (the certain
  maximum, `values.count`) and, for the reason `distinct_limit` only,
  `threshold_reached_at_record` (the record of the T-th distinct value) and
  `overflow_detected_at_record` (the record of the (T + 1)th, which proves the
  overflow). Records are numbered like `first_record`: a record with several
  occurrences of the field counts once, and the number does not depend on the
  reader (batches of CSV columns or one value at a time) or on the workers. A
  member that is unknown is absent, never `null`. `estimate` (lot 2b) is the
  KMV estimate of 18.5, published for a `limited` count when the samples saw the
  whole field (the values and, since lot 2c, the long texts). The other envelopes keep their members; a
  `complete` envelope without `accuracy` is exact for its declared population.
- `values.frequencies`: envelope whose value is `{distinct, listed, truncated}`.
  `distinct` counts distinct analytical values (`(type, analytical text)`),
  which may be fewer than the raw cardinality. `listed` holds the
  `limits.max_listed_frequencies` most frequent analytical values as
  `{value, type, count}`, ordered by count (descending), then value, then
  native type (`string`, `integer`, `number`, `boolean`). Output truncation is
  not a limitation of the measure: `truncated` says the listing is shorter than
  `distinct`. When the table is released, the envelope is `limited` without
  `lower_bound`: raw distinct values do not prove analytical ones.
- `values.samples` (lot 2b): a plain object `{selection, kept, of, listed}`
  (and `k`, `hash`, `threshold` for `bottom_k`, section 18.9) with up to
  `limits.max_samples` (K, 10,000 by default, section 18.2) distinct **original**
  values (section 21), not analytical ones. `selection` is `all` (every
  distinct value, in first-seen order, no hash) or `bottom_k` (the K of smallest
  priority, ascending). An entry is `{id, value, type, count, count_accuracy,
  identity_accuracy}`. Counts are exact in every selection. Values longer than
  `limits.max_stored_value_length` are not in the listing: they have their own
  small sample, the `long_texts` member (section 18.6), and `selection` and `of`
  describe the listed values only. `kept` listed values out of the `of` the
  scan sampled (section 19.4); exposure can make them differ (18.9). The size
  K can be smaller than the configured one when the memory budget cut it
  (`requested_k`, `reason`, section 18.10). Samples are examples, not
  statistics. The selections `uniform_distinct` and `first_seen` of the first
  revision are gone.
- `values.first` and `values.last`: `{value, type, record}` for the first and
  last analytical values (EF21), `null` without values. They keep the whole
  value, even beyond `limits.max_stored_value_length`.
- Shares and confidences are rounded to four decimals; counts are never
  rounded.

### 9.2 String characteristics (lot 2a, extended in lot C1)

Over `content` strings, on raw values, before normalization. Every counter is a
number of occurrences of values, computed once per distinct value and weighted by
its count; a value with no character (an empty string) has none of them. Shares
are not stored.

Lot 2a counters, always present:

| Counter | Rule |
| --- | --- |
| `non_ascii` | A character above U+007F. |
| `with_line_breaks` | A line boundary of `str.splitlines` (`
`, `
`, ``, ``, U+001C to U+001E, U+0085, U+2028, U+2029). |
| `with_control_characters` | A character of category `Cc` other than the tabulation and line breaks. |
| `with_surrounding_whitespace` | `value != value.strip()`. |
| `with_repeated_whitespace` | Two consecutive whitespace characters in `value.strip()`. |
| `uppercase`, `lowercase` | `str.isupper()`, `str.islower()`. |
| `mixed_case` | Cased characters, but neither `isupper()` nor `islower()`. |
| `no_letters` | No character with `str.isalpha()`. |

Case counters are exclusive; letters without case (such as CJK) count in none
of them.

Lot C1 counters. Each character has one class symbol: an ASCII lower or upper case
letter; a letter of the Latin script outside ASCII (its Unicode name starts with
`LATIN` or `FULLWIDTH LATIN`); another letter (`str.isalpha`); an ASCII digit; another
digit (`str.isdigit`); another alphanumeric character (`str.isalnum`, such as `½`); a
tabulation; a non-breaking space (U+00A0, U+2007, U+202F); another whitespace
character; a control or format character (category `Cc` or `Cf`); an invisible
character (U+200B to U+200D, U+FEFF, U+2060); the replacement character U+FFFD;
or a special character (any other).

| Counter | Rule |
| --- | --- |
| `with_ascii_lowercase`, `with_ascii_uppercase` | At least one such letter. |
| `with_other_latin_letters`, `with_non_latin_letters` | At least one letter of that class. |
| `with_ascii_digits`, `with_other_digits` | At least one such digit. |
| `starts_uppercase`, `starts_lowercase` | `value[0].isupper()`, `value[0].islower()` on the raw value (a leading space is not a letter). |
| `with_tabs`, `with_non_breaking_spaces` | At least one tabulation, one non-breaking space. |
| `with_invisible_characters`, `with_replacement_character` | At least one invisible character, one U+FFFD. |
| `ascii_only` | `value.isascii()`. |
| `letters_only`, `digits_only`, `alphanumeric_only` | Every character is a letter, a digit, a letter or digit or `isalnum`. |
| `letters_and_digits` | `alphanumeric_only`, with at least one letter and one digit. |

The block also holds:

- `characters`: the characters of the raw values, each value weighted by its count.
- `distinct_characters`: a `measure(int)`, the exact number of distinct characters
  of the field. It is `limited` (reason `character_limit`, `limit`, `lower_bound`
  `limit + 1`) when the field has more than `limits.max_distinct_characters` (1,024)
  of them.
- `special_characters`: a `measure` of `{distinct, value_count_accuracy, listed}`, the inventory of the
  special characters, which are neither alphanumeric, nor whitespace, nor
  control or format characters (so punctuation, symbols, combining marks and U+FFFD).
  Each listed entry has `char`, `codepoint`, `value_count` (distinct values with the
  character) and `occurrence_count` (occurrences of values with it), by
  descending `occurrence_count` then code point. `value_count` is `exact` while the
  table of distinct values is complete; once the field is streamed a value that
  returns in a later batch is counted again, and `value_count_accuracy` is
  `upper_bound` (the one measure of 9.2 that cannot be identical in both modes of 13,
  as it counts distinct values; the contract tests ignore it).
  Characters of category `Cc`, `Cf` and `Cs` (a lone surrogate) are never special. It is `limited` with the same
  reason, and no list, above `limits.max_special_characters` (256) distinct special
  characters, and `disabled` when that limit is 0. A bound never depends on the
  order of the values, so the complete table and the streamed field agree (13).

A field with no string has `characters` 0 and `not_applicable` (`no_values`)
distributions. Under `mask` and `hide` (12.8) the counters and `characters` stay and
both distributions are `disabled`.

Calculation: a bytes translation of the ASCII values (a cached translation of the
others) gives the set of class symbols of a value, from which every presence and
composition counter follows by a cached table; a second translation, only for a
value with a special character, extracts them. The distinct characters are
collected per batch.

### 9.2b Character map (lot C2)

`derived.characters` holds, for each field, the character map of its strings: the
characters of the stored samples, counted after the scan from its samples alone
(`charactermap.py`), like the patterns of 18.12. Each entry is a measure envelope
(`complete`, `limited`, `not_applicable`, `disabled`, `failed`) of a `CharacterMap`:

| Member | Rule |
| --- | --- |
| `basis` | `exact` when the samples list every distinct value with its count (`selection` `all`, no long text), `sample` otherwise. |
| `values`, `characters`, `distinct` | The strings read (empty ones included), their characters, the distinct characters. |
| `top` | The `limits.max_top_characters` (20) most frequent characters, letters and digits included, by descending occurrences then code point: `char`, `codepoint`, `occurrence_count`. Case counts apart (`A`, `a`). |
| `scripts` | The script of each letter (category `L*`): the first word of its Unicode name, after `FULLWIDTH` or `HALFWIDTH` (`LATIN`, `CYRILLIC`, `CJK`, `HANGUL`...), `UNKNOWN` without a name. Every script met. |
| `categories` | The Unicode general category (`Lu`, `Nd`, `Po`...) of every character; adds up to `characters`. |
| `ends_uppercase`, `ends_lowercase` | Occurrences of values whose last character is `isupper()`, `islower()`. |
| `title_case` | Occurrences of values with `str.istitle()` (a capital after each uncased character, lowercase elsewhere; at least one cased letter). |
| `with_emoji`, `emoji_sequences`, `emoji` | Occurrences of values with an emoji, the sequences in them, and the `limits.max_top_characters` most frequent sequences. |

An emoji sequence is a flag (two regional indicators), a keycap, a tag sequence, or an
emoji with its skin tone, variation selector and zero-width-joiner chain. The emoji are
recognized by a table of ranges in the code, with no dependency on a Unicode data file:
the pictographs from U+1F300 and a few symbols below are emoji by default, the other
symbols (arrows, card suits, the heart) only with U+FE0F. The table is an approximation of
`Extended_Pictographic`, and a standard that adds emoji needs the table updated.

The tables are all or nothing, as in 9.2: above 65,536 distinct characters or 10,000
distinct emoji sequences the entry is `limited` (reason `character_limit`) and lists
nothing. A masked or hidden field is `disabled`, a field whose samples exposure
withheld is `not_applicable` (`samples_withheld`), a field with no string
`not_applicable` (`no_values`). `limits.max_top_characters` 0 turns the block off. The
first pass is not touched. Cost: one `Counter` of the joined strings and three C-level
`map`s over the distinct stored values, a fraction of a millisecond a field.

`check_scan` checks one entry per field in the order of the fields, the descending
order of `top`, the code points, that `categories` adds up to `characters`, that no
case counter passes `values` and that `with_emoji` agrees with the sequences.

### 9.3 String lengths (lot 2a)

Envelope over analytical `content` strings, in code points: `count`,
`min_length`, `max_length`, `mean_length`, `median_length` and
`length_histogram` (`[{length, count}]`, ordered by length). The mean and the
median (mean of the two middle lengths for an even count) follow the numeric
output rule of 9.4. The length histogram is independent of the frequency
table, so string lengths and their median stay exact when the table is
limited.

### 9.4 Numbers (lot 2a, extended in 3a) (EF15, O05)

Population: native `integer` and `number` values, plus strings whose
analytical value the number detector (12.10) matches, including ambiguous
values resolved by configuration or by the evidence of the column (20.27),
under which the strict decimals `d.ddd` of a column that proves `comma` are
thousands. Its strict rule (optional sign, digits,
optional dot decimal, optional exponent, no leading zeros for integers) is
the rule of lot 2a; its decimal conventions extend it.

Envelope value: `count`, `native_count`, `text_count`, `min`, `max`, `sum`,
`mean`, `population_variance`, `population_std`, `positive`, `negative`, `zero`,
`integral_decimals` (decimal representations with an integral value, such as
`1.0` or `1e3`) and `median` (nested envelope).

- Integers accumulate as Python `int`; decimals as `Decimal` in an exact
  context of 200 significant digits with exponents between -1,000 and 1,000,
  trapping `Inexact`. If an operation would round or leave that range, the
  envelope becomes `limited` with reason `precision` and limit `200`. So does
  a number beyond the range of `decimal` (`1e9999999999999999999999`); a zero
  is exact whatever its exponent (`0e-5000`).
- Variance uses the complete population (divide by `n`), from exact sums.
- Output: integral results below 10^200 are JSON integers; other results are
  float64. A result that is not a finite float64 makes the envelope `limited`
  with reason `precision`.
- `median` (mean of the two middle values for an even count) is exact when
  derived from a complete frequency table. Otherwise it is `limited` with the
  reason and limit of the table (`distinct_limit`, `global_budget` or
  `value_too_long`, section 11). Other quantiles are deferred (EF22, O20).
- Values that are not finite in text (`NaN`, `inf`) are not numbers.

### 9.5 Booleans (lot 2a)

Envelope of native booleans: `{"true": n, "false": m}`, `not_applicable`
without native booleans. Textual booleans are the `boolean` detector
(12.10), which counts them in its `details`.

### 9.6 Temporal values (lot 3a) (EF16)

Produced by the date detector (12.10) from its matched values, including
ambiguous values resolved by configuration. Envelope value: `count`,
`ambiguous` (unresolved ambiguous values, excluded) and `kinds`, one entry per
kind seen, in order `date`, `datetime_naive`, `datetime_aware`, `time`:
`{kind, count, min, max, years}`. `min` and `max` are ISO strings (Python
`isoformat()`); aware values compare as instants, ties broken by their text,
and naive and aware values are never compared. `years` lists `{year, count}`
by year for dates and date-times, which is always bounded (years 1 to 9999),
and is `null` for times.

- `not_applicable` (`no_values`) without temporal or ambiguous values, or
  when the date detector has no eligible value; `disabled` when the date
  detector is disabled or absent from the registry; `failed` with the
  diagnostic of the date detector when it failed on the field.

### 9.7 Technical type (lot 3a)

A port of the current inference so the report keeps its meaning: candidate
families are tried in order `integer`, `number`, `date`, `boolean`, `text`, and
the first whose accepted share reaches `types.minimum_confidence` wins;
otherwise `mixed`; `empty` without values. Native JSON types count directly.
Output: `{type, confidence, counts, outside_count}`.

- Each value of the `values` population belongs to one family, a pure
  function of the value. Native integers, numbers and booleans are their own
  family. A string is, in this order: `date` when the date detector matches
  it as a calendar date (not a date-time or a time) or finds it ambiguous;
  `boolean` when it is `true` or `false` ignoring case (the current rule;
  other boolean words are only the `boolean` detector's); `integer` when the
  number detector matches it with an integer format, `number` when it
  matches another format or is ambiguous; otherwise `text`.
- Accepted counts: `integer` counts integers, `number` integers and numbers,
  the others their own family. Shares compare exactly with the decimal value
  of the threshold.
- `counts` lists the families seen, in family order. `confidence` is the
  accepted share of the winning family, or the largest share for `mixed`,
  rounded to four decimals, and `null` for `empty`. `outside_count` is the
  number of values outside the winning family, `null` for `mixed` and 0 for
  `empty`.
- Families depend on the number and date detectors and their settings, as
  the current date family depended on `date_detection`: a disabled or failed
  detector contributes no family. Differences with the pandas engine, adopted
  by the report in lot 5a (section 16.4): decimal conventions and month names are accepted, ambiguity is
  never resolved from evidence, and a date column with several formats or
  ambiguous values is `date`, where the current engine says `mixed`.

### 9.8 Normalization

See section 10.

### 9.9 Empty inputs (O15)

- A CSV with only a header gives a `rows` dataset with zero records and one
  field per column; counts are zero and value measures are
  `not_applicable` with reason `no_values`.
- An empty JSON array gives a dataset with zero records and no fields.
- A field without values gives `not_applicable` value measures.
- `not_applicable` measures of lot 2a use the reason `no_values`: the
  population of the measure is empty.
- An empty file is fatal: a CSV needs a header, and an empty file is not JSON.
- Percentages are left to consumers; the scan publishes counts and
  denominators, so no division by zero can occur in the scan.

### 9.10 Records (lot 5c)

Each dataset has a `records` block of record-level facts (section 16.2):

```json
{"with_missing": {"count": 2, "records": [2, 5]},
 "empty": {"count": 1, "records": [5]},
 "duplicates": {"count": {"status": "complete", "value": 1}, "records": [3]}}
```

- The values of a record are its scalar observations (strings, numbers,
  booleans, nulls). An absent field is not a value of its record.
- `with_missing`: records with at least one value missing under
  `values.missing`; `empty`: records with values, all missing. A record
  without values is neither.
- `duplicates`: records equal to an earlier record of the same dataset,
  beyond the first occurrence. Records compare every observation (path,
  native type, raw value) through a 128-bit BLAKE2b digest, one per distinct
  record: exact up to a negligible collision probability. A record of a
  table is its values alone, hashed joined by NUL characters when none holds
  one (CSV values never do), otherwise with their lengths, each form with its
  own personalization (lot 6). The digests of the
  whole scan are bounded by `limits.max_tracked_records`: once it is reached,
  new digests are not stored but records are still compared with the stored
  ones, so every counted duplicate is proven, and the count of a dataset with
  an untracked record is `limited` with reason `record_budget` and the count
  as `lower_bound`. `disabled` when `records.duplicates` is `false`.
- `records` lists the first record indices, up to
  `limits.max_listed_records`.
- `sample`: the row sample (section 18.11), a start, a bottom-k of the interior
  and an end of whole rows, values per field id as canonical text (section 9.1),
  in observation order for items paths; a JSON null is `null`; untracked paths
  and absent fields have no key. The exposure gate applies at finalization
  (12.8): `content` strings, numbers and booleans of a sensitive field are
  masked, or their cell is `null` under `hide`; nulls and non-content strings
  stay as read. The `preview` of the first records, which lots 5c to 3b kept
  beside it, was removed at lot 5: the start of the sample holds the same cells.

### 9.11 Rates of the report (A03)

The report derives four rates per column from scan counters, with
`percent(count, total) = round(100 * count / total, 2)`, and `0.0` when the
total is zero. They are views, not collectors: nothing is recomputed from the
source. Report rates are percentages from 0 to 100; scan shares
(`share_eligible`, `share_tested`, `confidence`) are fractions from 0 to 1.

`value_slots` of a field is `occurrences + presence.absent` (`absent` counts
as 0 where it is null): the records of the dataset for a CSV column, plus the
parent objects where a JSON member is absent, so a null and an absent member
both occupy a slot.

| Rate | Count | Denominator | Notes |
| --- | --- | --- | --- |
| `missing_percent` (column) | `missing.count` | `value_slots` | Missing under `values.missing`: absent, null, empty, blank and markers by default. |
| `missing_percent` (dataset summary) | sum of `missing.count` | `cell_count`, the sum of the `value_slots` of the columns | N x C for a CSV. |
| `type_error_percent` | `technical_type.outside_count` | `values.count` | The typed population: missing values are not in it. `null` when the column is `mixed`. |
| `trim_percent` | `changed` of the `trim` stage | `value_slots` | `changed` counts `content` strings only, over every slot, so empty and null cells lower the rate: it understates the share among content strings. Kept as it is. |
| `collapse_internal_whitespace_percent` | `changed` of `collapse_whitespace` | `value_slots` | Same remark; `changed` is counted after the trim stage. |

Their meaning and units are a contract: a change needs a new name or a
declared revision. `tests/scan/test_contract_scan_json.py` (A03) pins them.

## 10. Normalization version 1 (D15, D16, EF33-EF38, O08)

Normalization applies to `content` strings only, never to the source. Stages
run in this order; each can be disabled:

| Stage | Definition | Default |
| --- | --- | --- |
| `nfc` | Unicode canonical composition (NFC). Compatibility forms (NFKC) are not applied. | on |
| `trim` | `str.strip()`: removes leading and trailing characters for which `str.isspace()` is true, including no-break spaces. | on |
| `collapse_whitespace` | Replaces every run of whitespace other than line breaks (`[^\S\r\n\v\f\x1c-\x1e\x85]+`) with one U+0020 space. | on |
| `casefold` | `str.casefold()`. | on |
| `strip_accents` | NFD, removal of combining marks (category `Mn`), then NFC. | on |

- The **analytical value** is the output of the enabled `nfc`, `trim` and
  `collapse_whitespace` stages. Frequencies listings, samples, lengths,
  detectors and statistics use it.
- The **comparison key** is the output of every enabled stage. It groups
  variants.
- Per stage, the result lists `{stage, enabled, changed, cardinality}`:
  `changed` counts occurrences modified by that stage given the output of the
  previous enabled stage; `cardinality` is the distinct count after the stage.
  A disabled stage passes its input through, has `changed` and `cardinality`
  set to `null` and influences nothing (CA16). The first entry is `raw`, with
  `changed` set to `null` and the raw cardinality, the same envelope as
  `values.cardinality`.
- `changed` counts `content` strings only. `cardinality` covers the whole
  `values` population by `(native type, text)`: integers, numbers and booleans
  pass through every stage unchanged, so the `raw` entry equals the raw
  cardinality.
- `changed` counters are exact streaming counters: they continue when tables
  are limited (ET09, CA17). Stage cardinalities are envelopes derived from the
  raw table: when it is released they become `limited` with the table's reason
  and limit and no `lower_bound`, since raw distinct values do not prove
  normalized ones. Without values they are `not_applicable` (`no_values`) and
  `changed` is 0.
- **Adaptive stage count (lot 4b, NORM-03, NORM-05, NORM-06, D13).** A stage
  whose `changed` is 0 modified no occurrence, so it is the identity on the
  distinct values: its `cardinality` is that of the previous enabled stage
  (`raw` for the first), complete or limited with the same reason, limit and
  bound, and `equals` names that stage. The test is the exact counter, which
  covers the whole scan and not the part read before the table was released.
  A stage with `changed > 0` after the release keeps a `limited` count with no
  bound and no `equals`: its distinct values cannot be rebuilt from a table
  that was dropped, and a later stage that changed nothing takes that count.
  Nothing is written as unchanged because no effect was seen early. A stage
  never carries the estimate or the upper bound of the raw count: they are in
  `values.cardinality`. A numeric column falls under the same rule (NORM-04):
  no text stage changes its values. No calculation is skipped by it, since the
  stages run at finalization only.
- `variant_groups`: envelope over `content` strings whose value is
  `{groups, listed, truncated}`. `groups` counts the comparison keys with at
  least two distinct raw variants; `listed` holds the
  `limits.max_variant_groups` largest as `{key, count, distinct, variants,
  truncated}`, ordered by `count` (occurrences of every variant, descending)
  then key. `variants` holds the `limits.max_variants_per_group` most frequent
  raw strings of the group as `{value, count}`, ordered by count (descending)
  then value; `distinct` counts every raw variant and `truncated` says the
  listing is shorter. Both limits truncate output only, like
  `max_listed_frequencies`. The envelope is `limited` like stage
  cardinalities when the table is released, and `not_applicable`
  (`no_values`) without `content` strings. When no enabled stage changed any
  string, it is exact and empty even after the release: every comparison key
  is its own raw string, so no key has two variants.
- A group is an analytical equivalence under these rules, not proof of business
  identity.
- `normalization.version` is `1`. Any change to these definitions increments it.

## 11. Limits and degradation (ET05-ET11, O09)

| Setting | Default | Hard cap | Effect when reached |
| --- | --- | --- | --- |
| `max_fields` | 10,000 per dataset | 1,000,000 | New paths are not tracked; `structure.paths` becomes limited; observations counted in `structure.untracked_observations`; warning `field_limit`. |
| `max_depth` | 64 | 1,000 | Deeper content is not traversed; counted in `structure.depth_truncated_observations`; warning `depth_limit`. |
| `max_record_observations` | 100,000 | 100,000,000 | Record excluded (tolerant) or fatal (strict); `record_too_large`. |
| `max_distinct_per_field` | 100,000 | 50,000,000 | The raw table is released; cardinality, frequencies, stage cardinalities, variant groups and derived medians become limited with reason `distinct_limit`. |
| `max_tracked_values` | 2,000,000 per scan | 500,000,000 | Global budget: the largest table is released first (ties: most recently discovered field); reason `global_budget`; warning `global_budget`. |
| `max_stored_value_length` | 1,000 characters | 1,000,000 | Longer values are counted but not stored: the first one releases the raw table, and table-based measures of that field become limited with reason `value_too_long`. A small sample of them keeps a preview and a digest (18.6). |
| `max_listed_frequencies` | 100 | 100,000 | Output truncation only. |
| `max_samples` | 10,000 (100 before lot 1a), as the size K of the sample, section 18.2 | 100,000 (10,000 before lot 1a) | Output size only. |
| `max_long_samples` | 100 (0 keeps none) | 10,000 | Size of the sample of long texts per field (18.6); the memory budget can grant less. |
| `long_preview_chars` | 200 | 1,000,000 | Characters of a long text kept as a preview; never above `max_stored_value_length`. |
| `max_sample_memory` | 512 MiB | 1 TiB | Bytes, by the cost model of 18.10, that the samples of the whole scan may reserve; a sample is cut to fit, with reason `memory_budget`. |
| `max_variant_groups` | 100 | 100,000 | Output truncation only. |
| `max_variants_per_group` | 20 | 10,000 | Output truncation only. |
| `max_evidence_examples` | 10 | 1,000 | Detector evidence size only. |
| `max_tracked_records` | 2,000,000 per scan | 500,000,000 | Duplicate digests stop being stored (about 80 bytes each); later records are still compared; duplicate counts of datasets with untracked records become limited with reason `record_budget`; warning `record_budget`. |
| `max_listed_records` | 10 | 10,000 | Output truncation of the record listings only. |

- Defaults are starting values, not validated budgets. Phase 6 revisits them
  with measurements. In the Scan and JSON work, `max_distinct_per_field`
  keeps its default and `max_samples` is the size K of the sample, default
  10,000 since lot 1a (O28, section 18.2).
- Degradation is one measure at a time; counters, normalization change counts,
  numeric and string statistics and detector coverage continue after a table is
  released (ET08).
- Hard caps are the protected core configuration: a user value above a cap is
  rejected before the scan starts (CA13).
- `max_distinct_per_field` must not exceed `max_tracked_values`, and an
  explicit `max_samples` must not exceed `max_distinct_per_field`. A
  `max_samples` that is not set takes the lower of its default and
  `max_distinct_per_field`; the document records the value in force, and so
  does `config_sha256`.
- Discovery order for budget ties is the order in which fields are registered
  across the datasets of the scan (declared CSV columns in header order), not
  the order of their first values.
- Proven lower bounds of a released table: `L + 1` for `distinct_limit`, the
  stored distinct count for `global_budget`, and the stored distinct count plus
  one for `value_too_long`, the long value being longer than every stored one.
  Canonical text lengths are compared.
- The global budget counts stored distinct values of every field of the scan.
  Finding the largest table scans the fields with a table; lot 6 may make it
  cheaper for wide sources.
- `max_fields` and `structure.paths` count field paths other than the record
  root, including declared CSV columns. The lower bound published when
  `max_fields` is reached is `max_fields + 1`: untracked paths are not
  remembered, so state stays bounded and no larger count is proven. The
  `field_limit` warning locates the first record with an untracked
  observation.
- `max_depth` is relative to the record root (`orders[].amount` has depth 3).
  An observation deeper than the limit is not emitted; every value of the
  truncated subtree counts in `depth_truncated_observations`. Array lengths
  still count truncated elements. `max_depth_seen` is the deepest analyzed
  observation, tracked or not, so it never exceeds `max_depth`. The
  `depth_limit` warning locates the first truncated record.
- A CSV header with more than `max_record_observations - 1` columns is fatal
  in both policies: every record would be too large.

## 12. Detectors (EF24-EF32, D09, D14)

### 12.1 Contract

```python
class Detector:
    id: ClassVar[str]                     # "date", "email", "pattern:customer_number"
    version: ClassVar[int] = 1
    family: ClassVar[str]                 # "number", "temporal", "contact", ...
    accepts: ClassVar[frozenset[str]] = frozenset({"string"})   # native types
    sensitive: ClassVar[bool] = False
    max_input_length: ClassVar[int | None] = None   # longer values: not_tested
    scope: ClassVar[Literal["value", "field"]] = "value"
    shapes: re.Pattern[str] | None = None            # section 12.5

    def __init__(self, settings: Mapping[str, object]) -> None: ...
    def classify(self, value: str) -> Classification | None: ...
    def classify_many(self, values: Sequence[str]) -> list[Classification | None]: ...
    def accumulator(self) -> DetectorAccumulator: ...

class DetectorAccumulator:
    def add(self, value: str, classification: Classification | None, count: int) -> None: ...
    def details(self, gate: ExposureGate) -> dict[str, object]: ...
    def field_matches(self) -> bool: ...          # field-level detectors only
    def rejects_field(self) -> bool: ...          # field-level detectors only
```

- `classify_many` (lot 6) classifies a batch of distinct values and must
  return exactly `classify` of each value, in order; the default maps
  `classify`. Built-in detectors override it to reject most values by an
  exact cheap check, without a call per value. If it raises, the engine
  classifies each value alone to locate the failure.
- `rejects_field` (lot 6) lets a field-level detector say that the field can
  no longer match whatever values follow, and that `add` no longer changes
  `details`: later values count as not matched without being classified.
  Only for detectors whose `classify` never returns `ambiguous` or
  `invalid`; `enumeration` rejects a field once it holds
  `maximum_distinct + 1` values.
- `Classification` is an immutable named tuple since lot 6, built about twice
  as fast as a frozen dataclass.

- `classify` is pure and deterministic: the same value always gives the same
  result. `None` means not matched. This makes memoization and per-distinct
  execution exact (section 13).
- `Classification` carries `state` (`matched`, `ambiguous`, `invalid`), an
  optional `format`, `candidates` for ambiguous values, an optional `reason`
  for invalid values and an optional parsed value for statistics. `invalid`
  means the value has the detector's shape but fails validation, such as
  `2026-02-30`. A `matched` value with `candidates` was ambiguous and was
  resolved by configuration. `convention` names the reading of an
  unambiguous value when several readings exist (date order, decimal
  convention); it feeds the ambiguity evidence (12.6).
- `classify` receives the analytical value of strings and the canonical text
  (9.1) of other accepted native types. Built-in detectors accept strings
  only: native values are already typed.
- The engine keeps coverage, formats (the `format` of matched values) and
  evidence for every detector. The accumulator receives
  `(value, classification, count)` for every tested value, `None` meaning not
  matched, and produces the detector-specific `details`, such as email
  domains. In both execution modes it sees the same distinct values, first
  seen first, with the same total counts. `details` receives the exposure
  gate of the field (12.8): any value it carries must go through it.
- A detector with `scope = "field"` decides at the end, through
  `field_matches()`, whether all its values match or none does; when none
  does, matched values count as `not_matched` and it has no formats.
- Any exception raised by a detector's code (`classify`, `accumulator`,
  `add`, `details`, `field_matches`) or a `classify` result that is not a
  `Classification` fails the detector on that field only (section 14). The
  `detector_failed` diagnostic names the detector, the field and the
  exception type, never its message, which could quote a value.
- `DetectorRegistry` holds detector classes by `id`, in registration order.
  `default_registry()` returns a fresh registry with the built-ins `number`,
  `date`, `boolean`, `enumeration`, `email`, `url`, `phone`, `postal_code`,
  `currency`, `percentage`, `quantity`, `uuid` and `ip_address`;
  `register(cls)` adds one and rejects
  a duplicate id. External plugin loading is deferred (O21). Declarative
  patterns (12.7) follow the registry's detectors, in configuration order.
- Configuration: `detectors.<id>` holds `enabled` and detector parameters
  (D14). Complex logic stays in code. Detectors registered without a
  configuration section receive empty settings and are enabled.
- Every field lists every registered detector, in registry order. The
  result of an enabled detector is `complete`, `not_applicable` (reason
  `no_values`, when the field has no eligible value) or `failed`; a disabled
  detector is `{"id", "version", "status": "disabled"}`.
  `engine.detectors` gives the version of each enabled detector.

### 12.2 Coverage (EF26, CA11)

For each detector and field:

- `eligible`: analyzable values of an accepted native type.
- `tested = eligible - not_tested`
- `tested = matched + ambiguous + invalid + not_matched`
- `share_tested = matched / tested` and `share_eligible = matched / eligible`,
  both published with their denominators.

`not_tested` is non-zero only for values longer than a detector's input cap
and for values skipped by adaptive detection (section 13), whose count the
result publishes in `adaptive`. With `detection.warmup_values` set to 0,
detection is exhaustive.

### 12.3 Result

```json
{
  "id": "date",
  "version": 1,
  "status": "complete",
  "coverage": {"eligible": 3, "tested": 3, "matched": 2, "ambiguous": 0,
               "invalid": 0, "not_matched": 1, "not_tested": 0,
               "share_tested": 0.6667, "share_eligible": 0.6667},
  "formats": [{"format": "YYYY-MM-DD", "count": 1}, {"format": "DD/MM/YYYY", "count": 1}],
  "evidence": {"matched": ["2026-09-26"], "invalid": [], "not_matched": ["x"]},
  "details": {},
  "adaptive": null
}
```

`adaptive` is `null` unless adaptive detection skipped the detector on the
field (section 13); it is then
`{"skipped_after": 10000, "warmup_reactions": 0, "not_tested": 1200, "diagnostic": null}`:
the warm-up size, the distinct warm-up values the detector reacted to (0, or
at most `detection.rare_share` of them for a rare detector, scan format
revision 4), the occurrences skipped (included in `coverage.not_tested`) and
the index of the `detector_skipped_reacted` warning when probes reacted more
often than the warm-up allowed, else `null`.

A failed detector has `status: "failed"`, `reason: "detector_error"`, a
`diagnostic` index and no `coverage`: a failure is never reported as values
that did not match (CA19).

- `share_tested` and `share_eligible` are rounded to four decimals;
  `share_tested` is `null` when no value was tested.
- `formats` are ordered by count (descending), then format.
- `evidence` has the keys `matched`, `ambiguous`, `invalid` and
  `not_matched`: the first distinct analytical values of each state, at most
  `limits.max_evidence_examples` each, without values longer than
  `limits.max_stored_value_length`. They go through the exposure gate
  (12.8).

### 12.4 Interpretations (EF24, EF27, CA12)

The technical type (9.7) and semantic interpretations are separate axes.
`interpretations.candidates` lists every detector whose `share_eligible`
reaches `detection.minimum_share` (default 0.95), ordered by matched count
then detector id, as `{detector, matched, share_eligible}`; a detector
without matched values never qualifies. `interpretations.primary` is the id
of the only candidate when exactly one qualifies, else `null`. Overlaps are
kept: `12345` may be an integer and a ZIP code; both are listed (CA10).

### 12.5 Shape classifier (EF30)

Each value gets a cheap shape signature (digits as `9`, letters as `A` or `a`,
other characters kept, runs compressed). Detectors may declare the shapes they
can match so others are rejected without running their full logic. Rejection
by shape is an exact `not_matched`, not `not_tested`.

- ASCII digits become `9`, uppercase letters `A`, other letters (including
  uncased ones) `a`: `2026-09-26` is `9-9-9`, `Québec` is `Aa`.
- `Detector.shapes` is a pattern the signature must fully match; it must
  accept the signature of every value `classify` can match. The signature is
  computed at most once per value, only when a detector declares shapes.
- Built-in detectors declare none: their exact first-character or
  character-set checks are cheaper than a signature. Shapes serve costlier
  detectors (catalogue, patterns).

### 12.6 Ambiguity (O06, specification 12.1)

An ambiguous value, such as `01/02/2026` when both `DD/MM/YYYY` and
`MM/DD/YYYY` are allowed, stays ambiguous. The date detector publishes, in its
`details`:

```json
"ambiguity": {"count": 1, "candidates": [{"formats": ["DD/MM/YYYY", "MM/DD/YYYY"], "count": 1}],
              "evidence": {"DMY": 1, "MDY": 0}, "resolution": null}
```

- `evidence` counts unambiguous values per order in the same field. It is
  exposed by the scan and by the report (section 16.4); the scan applies it to
  numbers (below, 20.27) and the second pass to dates (20.26).
- Only configuration resolves ambiguity (`detectors.date.ambiguous_order`),
  and then `resolution` is `{"order": "DMY", "source": "config"}` and resolved
  values count as matched.
- `count` and `candidates` cover every value ambiguous under the enabled
  readings, resolved or not, so a configured resolution shows what it
  decided; `coverage.ambiguous` counts the values the configuration did not
  resolve. Candidates
  list their formats sorted, and are ordered by count (descending), then
  formats.
- `evidence` lists `DMY` and `MDY` when both orders are enabled, and is
  empty otherwise.
- Ambiguous values never enter statistics that need one interpretation,
  unless a resolution gives them one.

The same rule applies to numbers such as `1,234`, ambiguous between a US
thousands separator and a French decimal comma: the number detector
publishes the same `ambiguity` block, with `evidence` for `comma` and `dot`
when both conventions are enabled (empty otherwise) and `resolution`
`{"convention": "comma", "source": "config"}` from
`detectors.number.ambiguous_convention`.

Numbers differ from dates in one way (O56, 20.27): without a configured
convention, the scan reads them by the evidence of the column. When at least
`detectors.number.min_evidence` unambiguous numbers prove one convention and none
proves the other, the ambiguous numbers enter `numeric` in it, and `resolution`
is `{"convention": "comma", "source": "evidence", "evidence": {"comma": 490,
"dot": 0}, "resolved": 110}`. They stay `ambiguous` in `coverage`: the detector
describes the writing, the `numeric` block the numbers.

### 12.7 Declarative patterns (EF29, O11)

`patterns` entries become detectors with id `pattern:<id>`:

```json
{"id": "customer_number", "regex": "C-\\d{4}", "description": "Customer number",
 "accepts": ["string"], "sensitive": false, "max_input_length": 256}
```

- The regex is compiled at configuration validation and matched with
  `fullmatch`. Invalid expressions are configuration errors.
- Hard caps: 200 patterns, 1,000 characters per expression, 10,000 characters
  per tested value. Values above `max_input_length` are `not_tested`.
- Python `re` has no timeout. Catastrophic backtracking remains possible with
  hostile expressions; the documentation must say that patterns are trusted
  configuration. A safer engine is a later option.
- Pattern identifiers must be unique. The `pattern:` prefix keeps them apart
  from built-in ids; a registered detector whose id equals a pattern's
  detector id is a `ConfigurationError` when the scan starts.
- Configured patterns are detectors and are not the patterns inferred from the
  samples (18.12), which are written apart in `derived.patterns`.
- Pattern detectors have family `pattern`, no formats and no `details`; they
  follow the registry's detectors in configuration order. Values of other
  accepted native types are matched on their canonical text (9.1). Their
  specification is in [detectors.md](detectors.md).

### 12.8 Sensitive values and exposure (ET17, O10, CA20)

- A field is sensitive when a sensitive detector matched at least one of its
  values, or failed on one of them: a failure cannot prove that nothing
  matched. This is deliberately conservative.
- `exposure.sensitive_values` is `mask` (default), `hide` or `show`.
- Every value-bearing block of a sensitive field (frequencies, samples, first
  and last values, variant groups, detector evidence and value-bearing
  `details`) passes through one exposure gate at finalization, once every
  value has been tallied, in both execution modes.
- `mask` replaces each uppercase letter (`str.isupper`) with `A`, every other
  letter with `a` and each digit (`str.isdigit`) with `9`, keeps other
  characters and does not compress runs, then merges equal masks before
  listings are selected: frequencies, samples and variant groups describe the
  masked values. `frequencies.distinct` counts distinct masks; ranking and
  sampling apply to masks. Variant groups with equal masked keys merge, as do
  equal masked variants of a group; `groups` and `distinct` count masked
  entries. Evidence lists distinct masks in first-seen order.
  `values.cardinality` and stage cardinalities stay raw counts.
- `hide` removes the values and keeps counts: listings of frequencies,
  samples, variant groups and evidence are empty (`truncated` is `true` when
  something was hidden), `first` and `last` are `null`.
- `show` exposes values unchanged.
- Statistics that are values themselves, such as a minimum or a date range,
  cannot be masked: under `mask` and `hide`, the `numeric` and `temporal`
  blocks of a sensitive field are `disabled`. Counts, lengths,
  characteristics and coverage stay, except the distributions of characters of
  `string_characteristics` (`distinct_characters`, `special_characters`), which are
  `disabled` (9.2).
- The effective configuration is not a value-bearing block.
- The field records `sensitive` and `exposure`, the mode applied (`null` when
  the field is not sensitive).
- The second pass leaves such a field out of every analysis, except, when
  `deep.sensitive.enabled` is set (off by default, decision O61, 20.35), the exact distinct
  count and the masks and classes without a value or a figure under a floor.

### 12.9 Catalogue

The catalogue and its priorities come from the specification. Lot 3a ports the
current rules (numbers, dates, booleans, enumeration candidates); lot 3b starts
the priority 1 catalogue. Each detector gets a short entry in `detectors.md`
before implementation: accepted formats, normalization, validation level,
overlaps, sensitivity and test values (O14). Detectors check syntax, never
real-world existence (EF32).

### 12.10 Built-in detectors (lot 3a)

The specifications of `number`, `date`, `boolean` and `enumeration` moved to
[detectors.md](detectors.md) in lot 3b, unchanged.

## 13. Execution strategy and performance (EF30, EF31, ET12)

Every per-value computation (normalization stages, number parsing, detector
classification, shapes) is a pure function of the value. The engine exploits
this without changing results:

1. While a field's raw frequency table is complete, per-value work runs once
   per distinct value, weighted by its count, at finalization.
2. When the table is released, the engine first processes the stored distinct
   values with their counts, then switches the field to streaming mode: new
   occurrences are gathered in a batch of distinct values with their counts
   (at most `values.BATCH_SIZE`, 4,096), processed whenever it is full and at
   the end. The batch is the memoization of lot 6; it replaced a cache that
   unique values emptied constantly.
3. Both modes produce identical results. A contract test compares a scan with
   `max_distinct_per_field=1` and a scan with the default for every
   non-table measure.
4. Adaptive detection (lot 6, O23). The first `detection.warmup_values`
   distinct values of a field, in first-seen order, go through every
   detector. The next distinct value ends the warm-up: each adaptive detector
   that reacted to none of them (no `matched`, `ambiguous` or `invalid` value,
   no failure) is skipped for the rest of the field. Later values are
   classified by the other detectors only, and count as `not_tested` for the
   skipped ones, except:
   - warm-up values, at every occurrence: a streamed field keeps its warm-up
     values (at most `warmup_values` per field) to recognize them;
   - probes: values whose CRC-32 (of the raw string, or of `type:canonical`
     for other native types) is a multiple of `detection.probe_interval`,
     about one distinct value in `probe_interval`, go through every detector.
     A skipped detector that reacts on a probe keeps counting it, and the
     field gets a `detector_skipped_reacted` warning: its counts are
     incomplete, and a scan with `warmup_values` 0 gives them exactly.

   A skipped detector is never re-enabled: a re-enabled detector would count
   the later occurrences of an earlier value differently in streaming mode,
   which cannot recognize them. Every rule above depends only on the
   first-seen order of distinct values and on each value, so both execution
   modes keep identical results. `number` and `date` are never skipped: they
   give every value its technical type family (9.7). A field with at most
   `warmup_values` distinct values stays exhaustive, so small files are never
   affected.

   With `warmup_values` 10,000, a detector reacting on at least 0.05% of the
   distinct values of a field, spread through the file, is skipped by
   mistake with a probability below 1% (`e^(-p × warmup)`); interpretations
   need 95%, so they never change. Sorted files remain the risk the probes
   cover.

   Rare detectors (lot 6, O24): a detector is also skipped when it reacted to
   at most `detection.rare_share` of the warm-up values (default 0.001, so 10
   values of 10,000) and to none of the second half of the warm-up, whose
   values are those after the first `warmup_values // 2`: its reactions were
   rare and have stopped. A detector still reacting in the second half stays,
   as in a sorted column where matches become frequent (identifiers crossing
   from four to five digits make ZIP codes frequent right after 10,000). A
   rare sensitive detector that has not matched stays: the field might have
   values to mask. Reactions are counted once per distinct warm-up value,
   which a streamed field recognizes through its warm-up values, so both
   modes decide alike. After a rare skip, probes that react on at least
   `PROBE_REACTIONS` (10) occurrences, more than `rare_share` of the probed
   occurrences, raise `detector_skipped_reacted`; warm-up values met again by
   a streamed field are not probes. `rare_share` 0 gives the rule of the
   first version.

   Open point: sensitive detectors (`email`, `phone`, `ip_address`) are
   skipped like the others when they reacted to nothing. A sensitive value
   first met after the warm-up, outside a probe, is therefore not detected
   and the field is not masked (12.8). With the batches of item 5, keeping
   them would cost little: to be decided before a release that relies on
   masking.
5. Batches (lot 6, O25). Per-value work runs on batches of distinct values in
   first-seen order: strings are normalized in one pass (printable strings in
   NFC inline, with the same results as `Normalizer.run` and
   `characteristic_flags`), then each detector classifies the whole batch
   through `classify_many`, and its tally counts the unmatched values
   together. A skipped detector counts its values as not tested in one
   addition, and a field-level detector that rejects the field
   (`rejects_field`) counts them as not matched. Order-dependent outputs
   (evidence, samples, first-seen listings) follow the first-seen order of
   the batch.
6. Column batches (lot 6, O25). A `RecordBatch` (section 6) is read column by
   column: each column is counted into its table at C speed, and the strings
   that are not content are taken out again. A field's own limits
   (`max_distinct_per_field`, `max_stored_value_length`) apply to its new
   values in first-seen order, as if they were added one by one; a table
   released inside a batch already holds the later values of the batch,
   processed with their counts, which gives the same results as streaming
   them. The global budget depends on the order of values across fields: a
   batch is read column by column only when it cannot exceed the budget
   (stored values plus rows times growing columns), otherwise record by
   record, in reading order.

   Batches are also bounded by size (lot 2c): a CSV batch of rows closes when
   it has read `readers.csv_reader.BATCH_BYTES` (8 MiB) of the source, checked
   every 16 rows, and the streaming batch of a field closes when the heavy
   values it holds (more than `values.HEAVY_LENGTH`, 256 characters) reach
   `values.PENDING_CHARS` (8 Mi characters). Without it one batch of large
   cells would take rows times columns times the cell size. A record is never
   split: the working memory of a scan is at least that of its largest record
   (MEM-05). No result depends on where a batch ends.
7. Workers (lot 6, O25). Sources of at least 16 MiB are analyzed with worker
   processes (`scan(workers=...)`, `--workers`), one per spare processor, at
   most 6 (8 until lot 12; benchmarks.md, lot 12): the scan process reads, keeps tables, budgets and record facts,
   and hands the per-value work of each field to one worker: its released
   table, then its streaming batches in reading order, or its complete table
   at finalization, the largest first. A worker processes the values exactly
   as the scan process would, so results are identical. Workers return value
   blocks as plain data (generic models cannot be pickled), validated again,
   with placeholder diagnostic indices that the scan process replaces by
   reporting the diagnostics in field order. Workers are subprocesses of the
   running interpreter talking pickled messages over their standard streams,
   so starting them never imports the caller's main module; when they cannot
   start, the scan stays in one process. A custom `registry` always stays in
   one process. The number of workers is not part of the configuration and
   never appears in the result.

The pandas engine of the first releases was vectorized; a pure Python
streaming engine has a higher cost per cell. The per-distinct strategy,
batches and workers are the mitigation: since lot 6, the scan is faster than
the pandas baseline with bounded memory. Measurements are in
[benchmarks.md](benchmarks.md); targets remain to be decided (O19). The next
step is reading one source with several processes, which needs mergeable
states (lot 7).

## 14. Diagnostics and error policy (O07, specification 8)

Data observations (mixed types, missing values, duplicates) are results, not
diagnostics. Diagnostics describe technical events:

```json
{"code": "csv_width_mismatch", "level": "error", "message": "...", "count": 2,
 "dataset": "rows", "field": null, "detector": null,
 "locations": [{"record": 2, "line": 3}, {"record": 3, "line": 4}]}
```

Levels are `fatal`, `error` and `warning`. `locations` keeps at most
`errors.max_locations` entries; `count` is always complete. Lost records are
never guessed when corruption prevents delimiting them.

| Situation | `strict` (default) | `tolerant` |
| --- | --- | --- |
| Unreadable file, undecodable text, NUL characters | Fatal `InputError` | Fatal |
| CSV record of unexpected width, including blank lines | Fatal `InputError` naming record and line | Record excluded, `csv_width_mismatch` error, scan status `partial` |
| CSV quoting error (`csv.Error`) | Fatal | Fatal: resynchronization is uncertain |
| Invalid JSON syntax, empty JSON file, invalid UTF-8 | Fatal | Fatal |
| JSON string or key with a lone surrogate escape (`"\ud800"`) | Fatal `InputError` | Fatal |
| JSON object with a duplicate key | Fatal `InputError` naming record and key | Record excluded, `json_duplicate_key` error, reason `duplicate_key`, status `partial` |
| Explicit JSON collection without any array at its path | Warning `json_collection_not_found`, empty dataset | Same |
| Record above `max_record_observations` | Fatal | Record excluded, `record_too_large` error, status `partial` |
| CSV header wider than `max_record_observations - 1` columns | Fatal | Fatal |
| Structural limit (`max_fields`, `max_depth`) | Warning, scan continues | Same |
| Measure limit | Envelope status, plus one `measures_limited` warning per dataset: `count` is the number of fields, the message names at most 10 | Same |
| Global value budget | One `global_budget` warning per scan: `count` is the number of released tables | Same |
| Duplicate record budget | One `record_budget` warning per scan: `count` is the number of records whose digest was not stored | Same |
| Detector exception | Detector `failed` on that field, `detector_failed` error, other analyses continue | Same |
| Pattern inference exception (18.12) | `derived.patterns` entry `failed` on that field, `pattern_inference_failed` error, other analyses continue | Same |
| Observations exception (18.13) | `observations` absent, `observations_failed` error (the exception type only), scan complete | Same |
| Skipped detector reacting on a probe (section 13) | `detector_skipped_reacted` warning per field and detector: `count` is the number of occurrences that reacted; for a rare detector, only when probes reacted more often than its warm-up | Same |

- Scan `status` is `complete` when every record in the requested scope was
  analyzed, `partial` when records were excluded. Fatal problems raise and
  produce no result.
- `scope` reports `records_read`, `records_analyzed`, `records_excluded` and
  exclusions per reason (EF05). A dataset's `record_count` counts analyzed
  records only.
- CLI exit codes follow the existing commands: 2 configuration, 4 input,
  1 other failures, 0 success including `partial`, with a warning on standard
  error.

## 15. Configuration (EF28, EF40-EF42, O13)

`ScanConfig` is a strict Pydantic model. In phase 4 it becomes the `scan`
section of `tabalyst.json`; since lot 5a the report reads its analysis
settings from it (section 16.4).

```json
{
  "scan": {
    "csv": {"encoding": "utf-8-sig", "delimiter": ","},
    "json": {
      "collections": null, "discovery_max_depth": 3,
      "flatten": {"enabled": true, "separator": ".", "max_depth": null},
      "arrays": {"mode": "preserve"}
    },
    "errors": {"policy": null, "max_locations": 10},
    "values": {
      "null_markers": [],
      "null_markers_case_sensitive": true,
      "missing": ["absent", "null", "empty", "blank", "marker"]
    },
    "normalization": {
      "nfc": true, "trim": true, "collapse_whitespace": true,
      "casefold": true, "strip_accents": true
    },
    "limits": {
      "max_fields": 10000, "max_depth": 64, "max_record_observations": 100000,
      "max_distinct_per_field": 100000, "max_tracked_values": 2000000,
      "max_stored_value_length": 1000, "max_listed_frequencies": 100,
      "max_samples": 10000, "max_long_samples": 100, "long_preview_chars": 200,
      "max_sample_memory": 536870912, "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10,
      "max_tracked_records": 2000000, "max_listed_records": 10
    },
    "records": {
      "duplicates": true,
      "sample": {"rows": 1000, "edge": 50, "cell_chars": 200, "max_bytes": 16777216}
    },
    "types": {"minimum_confidence": 0.95},
    "detection": {"minimum_share": 0.95, "warmup_values": 10000, "probe_interval": 100,
                  "rare_share": 0.001},
    "detectors": {
      "number": {"enabled": true, "conventions": ["dot", "comma"],
                 "ambiguous_convention": null},
      "date": {"enabled": true, "orders": ["YMD", "MDY", "DMY"],
               "separators": ["-", "/", "."], "ambiguous_order": null,
               "month_languages": ["en", "fr"]},
      "boolean": {"enabled": true,
                  "pairs": [["true", "false"], ["yes", "no"], ["y", "n"],
                            ["oui", "non"], ["vrai", "faux"]]},
      "enumeration": {"enabled": true, "minimum_values": 500,
                      "maximum_distinct": 49, "case_sensitive": true},
      "email": {"enabled": true, "max_tracked_domains": 10000,
                "max_listed_domains": 20},
      "url": {"enabled": true, "schemes": ["http", "https", "ftp"],
              "www": true, "max_tracked_hosts": 10000, "max_listed_hosts": 20},
      "phone": {"enabled": true, "regions": ["nanp", "fr"]},
      "postal_code": {"enabled": true, "regions": ["ca", "us"]},
      "currency": {"enabled": true, "conventions": ["dot", "comma"],
                   "ambiguous_convention": null},
      "percentage": {"enabled": true, "conventions": ["dot", "comma"],
                     "ambiguous_convention": null},
      "quantity": {"enabled": true, "conventions": ["dot", "comma"],
                   "ambiguous_convention": null, "max_tracked_units": 10000,
                   "max_listed_units": 20},
      "uuid": {"enabled": true},
      "ip_address": {"enabled": true, "versions": ["ipv4", "ipv6"]}
    },
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "pattern_inference": {"enabled": true, "max_patterns": 8,
                          "max_value_length": 64, "min_distinct": 2},
    "observations": {"enabled": true, "max_items": 1000},
    "random_seed": 42
  }
}
```

Layers, from lowest to highest priority: hard caps (never overridden, only
enforced), built-in defaults, optional profile (phase 7), configuration files
(`--config` files in order), command-line options (`--delimiter`,
`--encoding`, `--collection`).

Configuration files (lot 4, maintainer decision):

- No file is discovered automatically: `tabalyst.json` is a conventional name
  passed with `--config`, so `report` and `sample` keep their behavior.
- One file serves every command: one object per tool (`scan`, `report`) and,
  at the top level, the `csv` settings of `sample`. The scan does not inherit
  the top-level `csv` settings.
- Every command validates each whole file, the `scan` object included, so a
  mistake in another command's section never passes silently. Errors name the
  file and the dotted key, such as `scan.limits.max_fields`.

Merge rules:

- Objects merge recursively, including `detectors.<id>`.
- Lists replace the previous list entirely (`null_markers`, `patterns`,
  `collections`).
- Unknown keys are errors.
- `null` is accepted only where the schema allows it and sets that value; there
  is no deletion syntax.

The result embeds the effective configuration and `config_sha256`, the SHA-256
of its canonical JSON (sorted keys, no whitespace, UTF-8) (EF42). Since format
revision 5 the embedded configuration is the one the scan applied:
`errors.policy: null` is resolved by the source format (`strict` for CSV and
JSON, `tolerant` for JSONL), unused flatten settings are normalized, and
collection paths are canonical (`resolve_config_defaults`, inspect design 5.5,
5.6, 10.3). `flatten` is applied by the JSON reader since lot
JI-3 (inspect design 7); `arrays.mode` has one value, `preserve`.

## 16. Result document (O01)

### 16.1 Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.2.0",
  "format_revision": 1,
  "engine": {"version": "0.6.1", "normalization_version": 1,
             "detectors": {"number": 1, "date": 1, "boolean": 1,
                           "enumeration": 1, "email": 1, "url": 1,
                           "phone": 1, "postal_code": 1, "currency": 1,
                           "percentage": 1, "quantity": 1, "uuid": 1,
                           "ip_address": 1}},
  "status": "complete",
  "run": {"started_at": "2026-10-06T12:00:00Z", "duration_seconds": 0.012,
          "timings": {"reading": 0.004, "analysis": 0.006, "finalize": 0.002,
                      "derived": 0.0, "other": 0.0},
          "workers": 1, "peak_memory_bytes": 52428800},
  "source": {"format": "json", "name": "orders.json", "size_bytes": 312,
             "modified_at": "2026-09-26T21:58:00Z", "sha256": "...",
             "encoding": "utf-8", "csv": null},
  "config": {},
  "config_sha256": "...",
  "scope": {"collections": {"mode": "auto", "requested": null},
            "records_read": 5, "records_analyzed": 5, "records_excluded": 0,
            "exclusions": {}},
  "datasets": [],
  "diagnostics": []
}
```

- `run` holds what varies between runs on the same source (O33): the
  `timings` (reading, analysis, finalize, derived analyses of 18.12 and the
  observations of 18.13, and other) add up to `duration_seconds`; `workers` is the number of processes
  that analyzed values; `peak_memory_bytes` is that of the main process, null
  when the platform does not report it; `counters` (lot 2c, 18.4) is written only
  when asked for. It is not part of the description of the data, so two scans
  of one source differ by it alone.
- `source.csv` is `{"delimiter": ",", "header": [...]}` for CSV sources and
  `null` otherwise; `source.size_bytes` is the number of bytes read and hashed.
- `scope.collections` describes JSON collection selection and is `null` for
  CSV sources, which have no collections to select.
- A `limited` envelope omits `lower_bound` when no bound is proven.
- Diagnostic `locations` list only the keys that apply: `{record, line}` for
  CSV, `{record, element}` for JSON.

The format follows the repository convention: `format_version` names the
experimental compatibility family and `format_revision` increases for each
meaningful change. Its
changelog is `docs/en/scan/format-changelog.md` (lot 4).

### 16.2 Datasets and fields

```json
{
  "id": "$.customers[]",
  "kind": "collection",
  "collection_path": [{"key": "customers"}, {"items": true}],
  "record_count": 4,
  "record_types": {"object": 4},
  "structure": {"paths": {"status": "complete", "value": 5},
                "untracked_observations": 0,
                "depth_truncated_observations": 0, "max_depth_seen": 3},
  "records": {"with_missing": {"count": 1, "records": [2]},
              "empty": {"count": 0, "records": []},
              "duplicates": {"count": {"status": "complete", "value": 0},
                             "records": []}},
  "fields": [
    {
      "id": "f4",
      "path": [{"key": "orders"}, {"items": true}, {"key": "amount"}],
      "display": "orders[].amount",
      "name": "amount",
      "parent": "f3",
      "collection": null,
      "first_record": 1,
      "occurrences": 4,
      "presence": {"parent_type": "object", "parent_count": 4, "present": 4, "absent": 0},
      "native_types": {"number": 1, "integer": 1, "null": 1, "string": 1},
      "strings": {"count": 1, "empty": 0, "blank": 0, "marker": 0, "content": 1},
      "missing": {"count": 1, "definition": ["absent", "null", "empty", "blank", "marker"],
                  "components": {"absent": 0, "null": 1, "empty": 0, "blank": 0, "marker": 0}},
      "arrays": null,
      "values": {"count": 3, "cardinality": {}, "frequencies": {}, "samples": {},
                 "first": {}, "last": {}},
      "string_characteristics": {},
      "string_lengths": {},
      "numeric": {},
      "booleans": {},
      "temporal": {},
      "normalization": {"version": 1, "stages": [], "variant_groups": {}},
      "technical_type": {},
      "detectors": [],
      "interpretations": {"primary": null, "candidates": []},
      "sensitive": false,
      "exposure": null
    }
  ]
}
```

Fields appear in order of discovery. Blocks introduced by later lots are
absent until their lot, then always present (with an envelope status when
they do not apply). For reuse (O12, section 16.6), the source block carries
size, modification time and SHA-256, and the result carries `config_sha256`.

### 16.3 Output files (lot 4, O17)

`tabalyst scan data.csv` stores the scan in the shared storage; since lot JI-7 so
does a JSON, JSONL or NDJSON source (it used to write `data.scan.json` beside
the source). `-o` and `-d` export `<stem>.scan.json` and follow the other commands. Writing uses a temporary file in the target
directory and an atomic replace, so an interrupted scan never leaves a partial
result. Existing outputs require `--force`; an output can never replace an
input.

Lot 4 details:

- `-o` must end in `.json`; `-d` names outputs `<stem>.scan.json`. Planning
  is shared with `report` and `sample` (`tabalyst/batch.py`): the whole batch
  is rejected before any scan on a name collision (`a.csv` and `a.json`), an
  output that would replace an input or a configuration file, or an existing
  output without `--force`.
- The temporary file is `.<name>.<random>.tmp` in the target directory,
  flushed and synchronized before `os.replace`, and removed on failure.
- A failed source does not stop the batch; exit codes are those of section
  14, the most general failure winning.
- The document is `model_dump(mode="json", by_alias=True)`, indented by two
  spaces, UTF-8 without escaping, with a final newline.
- Progress: `reading` events carry `bytes_read` and `bytes_total`, at most
  once per percent of the file and never more often than every MiB; then
  `writing`, and `complete` once the document is written.

### 16.4 Report built on Scan (lot 5a, O16)

`tabalyst report` scans the CSV with the `scan` configuration and builds the
report profile (revision 3) from the result (`report_profile.py`). Decided with
the maintainer in lot 5a:

- **One pass.** Record-level facts (preview until lot 5, duplicate rows, empty
  rows, rows with missing values) were collected through `scan(on_record=...)`;
  since lot 5c they are the `records` block of the scan (section 9.10),
  bounded by `limits.max_tracked_records`.
- **Configuration.** Every analysis setting of the report, CSV reading
  included, comes from `scan`. The `report` object keeps the presentation
  settings (`string_analysis`, `value_examples`; since lot 1c of the Scan and
  JSON work, they were at the top level before) and the top level `csv` serves
  `tabalyst sample`. Former report settings are rejected with their new
  location; a top-level `csv` value that differs from `scan.csv` is an error
  for the report, since the file would otherwise be read differently than
  written, unless the command line sets that value explicitly.
- **Types.** The report type is the technical type (9.7): a date column with
  several formats or ambiguous values is `date`. Unresolved ambiguous dates
  make the column `with_issues` and are counted by the `ambiguous_dates` issue.
- **Ambiguity (12.6).** The report never resolves ambiguity: it shows the
  ambiguous values, the evidence per order, and, when the evidence is
  one-sided, suggests `detectors.date.ambiguous_order`.
- **Semantic types.** `date` when the technical type is `date`, otherwise the
  primary interpretation (12.4), except `number` and `boolean`, which repeat
  the technical type.
- **Exposure (12.8).** The report applies the scan's exposure: masked or hidden
  values in examples, value profiles and the row sample of sensitive columns;
  distinct counts stay raw. Missing cells of the row sample stay as read.
- **Limits.** A limited distinct count or median is `null`, shown as
  `limited`, and the column is listed by the `limited_measures` issue. Records
  excluded under the `tolerant` policy are listed by the `excluded_records`
  issue. A CSV wider than `limits.max_fields` is a configuration error for
  the report, whose counts need every column.
- **Examples.** A complete value distribution comes from the frequency listing
  when it holds every value; otherwise examples are selected among the scan
  samples. Length examples come from the listing, then the samples.
- **Sources.** CSV and JSON sources since lot 5b (section 16.5).

The parity tests (`tests/scan/test_scan_report.py`) compare the report built
on Scan with the pandas engine on both demos, each known difference listed
explicitly.

### 16.5 JSON sources and detectors in the report (lot 5b)

Decided with the maintainer in lot 5b:

- **Datasets.** Profile revision 4 moves `summary`, `date_summary`,
  `columns`, `issues` and `preview` into `datasets`, one item per scan dataset
  (`id`, `kind`). A CSV source has its one dataset; a JSON dataset is listed
  when it has at least one column, so `$` disappears when every value lies in
  collections. `source` gains `format`; `delimiter` is `null` for JSON.
- **Columns.** Every CSV column. For JSON, the fields whose native types
  include a scalar or `null`, in discovery order, named by `display`
  (`orders[].amount`) with `position` their 1-based rank. Containers are
  structure, not columns; the structure section is not part of lot 5b.
  Missing counts and percentages use the value slots of the field,
  `occurrences + presence.absent`, the row count for CSV columns;
  `cell_count` sums them.
- **Record facts.** `RowFacts` dispatches records by dataset. A record's
  values are its scalar observations; it has missing values when one is null
  (under `values.missing`) or a missing string, and is empty when all are.
  An absent field is not a value of its record. Duplicate records compare a
  digest of every observation (path, type, value). The preview keeps the
  scalar values per path: an absent field is `null` with its position in
  `absent`, the values of an items path are joined with `, `, a JSON null is
  the text `null`, and a cell with any hidden value is `null`.
- **Excluded records.** Counted per dataset from the exclusion diagnostics
  (`csv_width_mismatch`, `record_too_large`, `json_duplicate_key`).
- **Detectors.** Each column lists the detectors that are `complete` with a
  match, an ambiguous or an invalid value, and the `failed` ones:
  `eligible_count`, `matched_count`, `matched_percent`, `ambiguous_count`,
  `invalid_count`, `formats` with percentages of the eligible values, and
  `primary` for the primary interpretation. The report shows them in a
  "Detectors and formats" section, one row per column and detector.
- **Outputs.** `tabalyst report data.json` writes `data.report.html` and
  `data.report.json`, so the profile never replaces the source; CSV names are
  unchanged.
- **HTML.** Several datasets render one view each, with a dataset selector in
  the navigation and element ids prefixed `d<N>-`; a single dataset keeps
  plain ids.

### 16.6 Report from a scan document (lot 5c, O12)

Decided with the maintainer in lot 5c:

- **Command.** `tabalyst report --scan INPUT...`: the inputs are scan
  documents. The report is built from the document alone (profile revision
  5): record facts come from its `records` blocks, so it equals the report
  of the source with the same scan settings, except `generated_at` and
  `processing_seconds`. Outputs are named after `source.name`
  (`report_name`), beside the scan document by default; the planning reads
  each document for that name and protects the source beside it from being
  replaced. The execution history names the source.
- **Documents.** `format`, `format_version` and `format_revision` must be
  those of the running version, otherwise `InputError` asking for a new
  scan; there is no migration. The document is validated as `ScanResult`.
- **Staleness.** The source is looked for beside the document under
  `source.name`. Missing: accepted, the document stands on its own, and
  the command warns that the source was not checked (scans written with `-d`
  elsewhere). Another size: stale. Otherwise its SHA-256 decides, whatever the
  modification time (amended in lot JI-2, DP-D): a touched file stays fresh, a
  file rewritten with the same size and time is stale. A document whose
  `engine.version` is not the running one is reported with a warning: it is a
  file the user chose, not a cache. Stale is an
  `InputError` (exit 4) naming the source and asking for a new scan.
- **Settings.** The document's `config` is the report's `scan`
  configuration. The `scan` settings of the configuration files, merged over
  the document's configuration, must leave its `config_sha256` unchanged,
  otherwise `ConfigurationError` (exit 2): settings the files do not give,
  such as a delimiter passed to `tabalyst scan`, are not compared.
  `--delimiter` and `--encoding` are rejected with `--scan`.
- **Batches.** A document that cannot be read while planning fails its own
  job only, its report named after the document file.
- **Timing.** `processing_seconds` of the profile is the time to read the
  document and build the profile.
- **Python.** `tabalyst.generate_reports(..., from_scan=True)` and
  `tabalyst.analyze_scan(path, config_path)`.

### 16.7 Normalization, limits and structure in the report (lot 5d)

Decided with the maintainer in lot 5d, for the sections deferred by lot 5b:

- **Profile.** Revision 6. The report carries the scan blocks without
  recomputing them.
- **Normalization.** Column `normalization` lists every stage of section 10,
  `raw` first, with `changed_count` (percent of the value slots, like the
  former trim and collapse counts) and `distinct_count` with its status, and
  the variant groups as the scan lists them, so already exposed (12.8). The
  "Transformations" section is extended rather than doubled: one column per
  stage, the analytical and compared distinct counts, the group count, then a
  table of the listed groups, whitespace shown as written. New info issue
  `variant_groups`.
- **Limits.** Each dataset has `limits`: every `limited` envelope of the
  dataset (`structure.paths`, `records.duplicates.count`) and of each field,
  containers included, found by walking the scan models and named by its
  location in the scan result (`values.cardinality`, `numeric.median`,
  `normalization.stages.casefold.cardinality`); the structural counters; and
  the diagnostics of the dataset and of the whole scan. A scan-wide diagnostic
  therefore appears in every dataset view. The "Limits and diagnostics"
  section is shown only when one of them is non-empty; the
  `limited_measures` and `excluded_records` issues link to it.
- **Structure.** JSON datasets only (a CSV is flat). `structure` lists every
  field, containers included, with depth (number of segments), parent,
  native types, presence per parent and array statistics; a promoted array
  names its collection. Presence of array items counts elements, so it has no
  percentage. Datasets without columns are still omitted (16.5): their
  structure is not shown.

### 16.8 The web page of a scan (lot 10b, O44)

Decided with the maintainer in lot 10b: an explicit `tabalyst scan` writes a web page, a scan that another command
makes by itself writes none.

- **Where.** `scan_page.scan_page_path`: beside the scan document with the extension `.html` (`x.scan.json` gives
  `x.scan.html`), or `<stem>.scan.html` beside the source when the scan is in the shared storage (no `-o`, no `-d`).
  `--no-html` skips it. It joins the outputs `validate_outputs` checks and cannot be an input. The page of a scan in the shared
  storage is replaced at every scan, like the scan; the page of a standalone scan (`-o`, `-d`) needs `--force` like its
  document.
- **What.** The report rendered from the Scan alone (`build_profile` with no analyses, then `render_report`): the page
  of `tabalyst report --scan` as it would be without a second pass. It reads no source and runs no analysis, so the
  scan writes no second-pass document because of it. With `--deep` the page is written again after the second pass,
  through `service._profile_from_scan`, so that it shows the stored results.
- **Who.** `generate_scans(html=True)` and `prepare_deep(html=True)`; the CLI passes `not no_html`. The Python API, the
  report, the plan and the sample leave it off (`html=False`), so their scans write no page.
- **Failure.** A page that cannot be built or written is a warning (`ScanSuccess.warnings`) and `ScanJob.page` becomes
  `None`: the scan document is already written and valid.
- **Cost.** Measured on `insurance-combined.csv`: `tabalyst scan` 18.1 s without the page, 20.0 s with it (+1.9 s,
  +10%); `insurance-ontario.csv` 3.9 s and 5.2 s. The rendering depends on the size of the document, not on the number
  of rows, and the first pass is not touched (`run.duration_seconds` is that of the scan).

## 17. Changes to this document

| Date | Lot | Change | Reason |
| --- | --- | --- | --- |
| 2026-09-26 | 0 | Initial contract. | Phase 0. |
| 2026-09-26 | 0 | Gate 0: every Proposed decision accepted without change. | Maintainer validation. |
| 2026-09-26 | 1a | Section 6: `DatasetOpened.fields` (declared fields), `RecordExcluded.code` and `message`, readers apply the error policy. | A header-only CSV must list its columns, and the engine must not know CSV diagnostic codes. |
| 2026-09-26 | 1a | Section 16.1: `source.csv` content, `scope.collections` null for CSV, `lower_bound` omitted when unproven, location keys per format. | Details the example did not settle. |
| 2026-09-26 | 1b | Section 6: `DatasetOpened.container`, `Record.depth_truncated`, `Notice` stream item; readers apply `max_depth` and `max_record_observations`; JSON element index is 0-based; records of datasets may interleave. | The engine links promoted arrays and reports truncation without knowing JSON; readers never build over-deep paths. |
| 2026-09-26 | 1b | Section 5.2: duplicate keys make a record malformed; UTF-8 byte order mark accepted; explicit selections listed in order, with `json_collection_not_found` when absent; overlapping, equivalent or empty selections rejected; document `collection_path` null. | Presence must stay exact; Windows tools write a byte order mark; a mistyped path must not pass silently. Maintainer decision. |
| 2026-09-26 | 1b | Section 11: `max_fields` lower bound is `max_fields + 1`; `max_fields` covers declared CSV columns; `max_depth` and `max_depth_seen` defined; CSV header above `max_record_observations` fatal. Section 14 rows added. | Counting every distinct untracked path would break bounded state (specification scenario 5). |
| 2026-09-26 | 2a | Sections 9.1 to 9.5: canonical text is `str()` of the parsed value; values output as canonical text; `frequencies.distinct` counts analytical values, limited frequencies have no bound; samples are a plain object in first-seen order; first and last values keep whole values; characteristic definitions; exact context of 200 digits and exponents within 1,000, integral output below 10^200; median limited with the table's reason and limit; booleans envelope. | `ijson` does not keep the source text; listings are analytical; a `limited` envelope needs a limit, and section 11 already named the table's reason. |
| 2026-09-26 | 2a | Section 11: the first value too long releases the table; proven lower bounds per reason. Section 14: `measures_limited` per dataset, `global_budget` per scan, lone surrogate escapes fatal. Section 9.9: `no_values` reason. Section 5.2: lone surrogates. | Details the contract did not settle; lone surrogates cannot be written as UTF-8 and the two `ijson` backends disagreed (lot 1b note). Maintainer decision. |
| 2026-09-26 | 2b | Section 10: `changed` counts content strings after the previous enabled stage; stage cardinalities cover the `values` population, are limited without bound after release and `not_applicable` without values; `variant_groups` value is `{groups, listed, truncated}`, groups carry `distinct` and `truncated`, orderings defined. Section 11: `max_variant_groups` and `max_variants_per_group` truncate output only. | Details the contract did not settle; a `limited` envelope has no value, so the literal rule would lose every group of a field with more than 100 of them. Maintainer decision. |
| 2026-09-26 | 3a | Sections 9.4 to 9.7: numeric population from the number detector; `temporal` layout; technical type families, `null` confidence for `empty`, `null` outside count for `mixed`. Section 12: the engine keeps coverage, formats and evidence, the accumulator produces `details`; `convention`, `scope`, `max_input_length` and `shapes`; failures keep the exception type only; every registered detector listed with its status; four evidence keys; candidate layout; shapes optional; ambiguity counts include resolved values; new 12.10 with the built-in detectors. Section 15: `detectors` settings. | Details the contract did not settle. The strict number rule keeps precedence so lot 2a results are unchanged; exception messages could leak sensitive values; the shape signature cost more than it saved for the built-ins. To validate at gate 3. |
| 2026-09-26 | 3b | Section 12.1: `details` receives the exposure gate; patterns follow the registry. Section 12.7: `pattern:` ids, collision with a registered detector, family, formats and details. Section 12.8: a failed sensitive detector makes the field sensitive; masks merge before listings are selected; `hide` empties listings and nulls `first` and `last`; `numeric` and `temporal` disabled under `mask` and `hide`; `exposure` field. Section 12.10 moved to `detectors.md`. | Details the contract did not settle: merging only the listed values would give wrong counts, a detector that failed cannot prove the field holds no sensitive value, and a minimum or a date range is a value (found in review). Maintainer decision. |
| 2026-09-26 | 3b | Sections 12.1, 15 and 16.1: built-in `email` and `url` detectors, enabled by default, with their settings; their specifications and the shared counted names block of `details` are in `detectors.md`. | Priority 1 catalogue, email and URL family. |
| 2026-09-26 | 3b | Sections 12.1, 15 and 16.1: built-in `phone` detector (regions `nanp` and `fr`), enabled by default, with its `regions` setting; its specification is in `detectors.md`. | Priority 1 catalogue, phone family. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `postal_code` detector (regions `ca` for Canadian postal codes and `us` for ZIP codes), enabled by default and not sensitive, with its `regions` setting; its specification is in `detectors.md`. | Priority 1 catalogue, postal code family. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `currency` (symbols and ISO 4217 codes), `percentage` and `quantity` (a number and any unit) detectors, enabled by default and not sensitive, with their own number conventions and ambiguity blocks, and bounded counted units for `quantity`; their specifications are in `detectors.md`. | Priority 1 catalogue, currency and percentage family, extended to generic quantities at the maintainer's request. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `uuid` (hyphenated, braced and URN forms, versions counted, not sensitive) and `ip_address` (versions `ipv4` and `ipv6`, sensitive) detectors, enabled by default, with the `versions` setting of `ip_address`; their specifications are in `detectors.md`. | Priority 1 catalogue, UUID and IP address family, the last of lot 3b. |
| 2026-09-27 | 4 | Section 15: no automatic `tabalyst.json`; one file for every command with a `scan` object, validated by every command; command-line layer. Section 16.3: output naming, shared planning, temporary file, batch failures, document serialization, byte progress. Section 5.2: integers above `sys.int_max_str_digits` parsed by the pure-Python backend, exponent overflow and long parser messages. Sections 3 and 16.1: top-level exports, format changelog page. | Maintainer decision on configuration files (report behavior unchanged); the compiled `ijson` backend crashed the process on long integers (lot 2a note). |
| 2026-09-27 | 5a | Section 3: `on_record` hook of `scan()`. Section 12.6: the report never applies ambiguity evidence. New section 16.4 and decision O16: report built on Scan, configuration in `scan`, technical types, primary interpretations as semantic types, scan exposure applied to the preview, limited measures and excluded records as issues. | Report migration; decisions of the maintainer in lot 5a (configuration, masking by default, `date` type with an `ambiguous_dates` issue, primary interpretations). |
| 2026-09-27 | 5b | Section 16.4: JSON sources accepted. New section 16.5: profile revision 4 with `datasets`, JSON columns as scalar fields named by path, value slots, record facts per dataset, preview of JSON records, detectors per column, `.report` output names for JSON sources, one HTML view per dataset. | Lot 5b; maintainer decisions (revision 4 with a dataset list, flattened paths, detectors section only). |
| 2026-09-28 | 5c | New section 9.10 and `records` block of datasets (format revision 2): records with missing values, empty records, duplicates under the new `limits.max_tracked_records` budget with reason `record_budget`, preview through the exposure gate; `records` settings and `max_listed_records`; section 14 `record_budget` warning. Section 16.4: record facts from the scan, `preview_rows` moved to `scan.records.preview`. New section 16.6 and O12 accepted: report from a scan document and the staleness rule. Pandas engine removed after gate 5. | Maintainer decisions of lot 5c: record facts in the scan so a report needs no source, stale scans fail, pandas removed at gate 5. |
| 2026-09-28 | 5d | New section 16.7: profile revision 6 with every normalization stage and the variant groups per column, limits and diagnostics per dataset, structure of JSON datasets; "Transformations" extended, "Limits and diagnostics" shown only when needed, "JSON structure" for JSON sources only. | Sections deferred by lot 5b; maintainer decisions of lot 5d. |
| 2026-09-28 | 6 | Decision O23 and section 13 item 4: adaptive detection after a warm-up of `detection.warmup_values` distinct values per field, with probes every `detection.probe_interval`; section 12.2: `not_tested` of skipped values; section 12.3: `adaptive` in detector results (scan format revision 3); section 14: `detector_skipped_reacted` warning; section 15: new `detection` settings. | Detection of high-cardinality fields dominated the scan time; exact `not_tested` counts keep the contract. Re-enabling a detector after a probe was dropped: it would break principle 6. |
| 2026-09-28 | 6 | Decisions O24 and O25 (Proposed). Section 13 items 2 and 4 to 7: streaming batches instead of the memoization cache, rare detectors, batches of distinct values, column batches, worker processes. Section 6: `RecordBatch`, `Observation` as a named tuple, shared path objects. Section 12.1: `classify_many`, `rejects_field`, `Classification` as a named tuple. Section 12.3: `adaptive.warmup_reactions` (scan format revision 4). Section 9.10: table digests joined by NUL. Section 14: warning of rare detectors. Section 15: `detection.rare_share`. | The maintainer asked for the most speed on large files, progressive learning that drops what became unlikely, and reading that uses the machine: per-call overhead dominated, not the rules. The rare rule keeps detectors reacting at the end of the warm-up, found on the sorted `id` column of the benchmark. |
| 2026-09-30 | JI-2 | Decision O12 amended and section 16.6: the SHA-256 always decides for a present source (no modification-time shortcut); another engine version warns. Section 15 and 16.1 (format revision 5): `json.flatten`, `json.arrays`, nullable `errors.policy`, the document records the resolved configuration, collection paths in canonical spelling. | Inspect design DP-D and DP-10 (scan identity), lot JI-2. |
| 2026-09-30 | JI-4 | Section 5.3: JSONL sources, read as the dataset `$[]`; `limits.max_line_bytes`; `source.format` `jsonl`. |
| 2026-10-01 | JI-7 | Section 16.3: with no `-o` or `-d`, the scan of a JSON, JSONL or NDJSON source goes to the shared storage like a CSV's. Sources of these formats are read with the configuration resolved by Inspect (inspect design 11). |
| 2026-10-06 | SJ-0 | Principles 1 and 7; decisions O22 (amended) and O26 to O33; section 9.11 (rates); section 16.1 (`run`); sections 18 to 21. | Scan and JSON work, lot 0: the contract and its tests before the code. Proposed until the maintainer accepts the baselines. |
| 2026-10-07 | SJ-0 | Section 19.4b: settings by tool, new Report setting `value_examples.kept_per_column` (default 100). | Keeps the Scan sample size K and the Report sample size apart in the configuration; keeps the examples of the Report unchanged. |
| 2026-10-07 | SJ-1a | Sections 9.1, 11, 15, 18.2, 18.9, new 19.7: qualified `values.cardinality` (`domain`, `accuracy`, `identity_accuracy`, `upper_bound`, records of the limit), K = `max_samples` at 10,000 with cap 100,000 and the K and T rule, reserved `bottom_k` members, JSON Schema and validator; the Report works on at most 100 sample values. | Lot 1a of the Scan and JSON work. Dedicated cardinality models keep the other envelopes unchanged (maintainer decision of 2026-10-07). |
| 2026-10-07 | SJ-1b | Sections 9.1, 19.1 to 19.7: `values.samples` has `kept` and `of`; the Report is a `tabalyst.report` document (revision 2) with the base at its paths, the `report` block (`generated_at`, `generator`, `processing_seconds`, `config`, `base_scan`, `datasets`), reduced samples declared, the loader `load_document` and `load_base`, `facts_sha256`, the Report JSON Schema. | Scan and JSON work, lot 1b: Report as a superset of the Scan and the common loader. |
| 2026-10-07 | SJ-1c | Sections 15, 19.3, 19.4, 19.4b: the `report` object of the configuration (`string_analysis`, `value_examples` moved from the top level), `report.value_examples.kept_per_column` (1 to 1,000, default 100) replaces `REPORT_SAMPLE_SIZE`, the pages read the base through `tabalyst.report_views` (`ColumnView` with the canonical `field`, `DatasetView`), `ScanFieldDetails` removed. | Scan and JSON work, lot 1c: projections and templates of the Report from the base. Maintainer decision of 2026-10-07 on the `report` object. |
| 2026-10-07 | SJ-0 | O28 amended and section 18.2: T and K are separate (`max_distinct_per_field` unchanged, `max_samples` becomes K); `BottomKSampler.from_exact` (18.3). | Lot 0 baselines: T = 10,000 saves memory, not time, and costs exact measures that a first pass alone never gets back. Maintainer decision. |
| 2026-10-07 | SJ-2a | Sections 18.3 and 18.8: `scanner/bottomk.py` (BLAKE2b 128 bits, `HASH_VERSION` 1, `update`, `retained`, `k`), the location of the sampler state (`ValueProcessor`, in the scan process or the worker of the field), the refusal measures. | Lot 2a of the Scan and JSON work: the sampler isolated from the product and the measured hash choice. |
| 2026-10-07 | SJ-2b | Sections 9.1, 18.2, 18.3, 18.9, 19.4, 21: the bottom-k in the engine (`scanner/valuesample.py`); `values.samples` of original values, `all` or `bottom_k` (`uniform_distinct` and `first_seen` removed), entries with `id`, `count_accuracy`, `identity_accuracy`, `k`, `hash`, `threshold`; `values.cardinality.estimate` (KMV, held within the certain bounds); exposure after the calculation with `kept < of`; the Report ranks an `all` sample by priority; `random_seed` in [0, 2**64). | Lot 2b of the Scan and JSON work. Maintainer decisions of 2026-10-07 (defaults accepted): `id` is the position in the Scan listing, `kept < of` declares withheld originals, the estimate is clamped with the raw value kept, the seed is bounded. |
| 2026-10-08 | SJ-2c | Sections 9.1, 11, 13, 16.1, 18.4, 18.6, 18.9, new 18.10: long texts sampled apart (`values.samples.long_texts`, `LongTextSampler`, digest identity `fingerprint_based`), the estimate adds the values and the long texts (`estimate.parts`), settings `max_long_samples`, `long_preview_chars` and `max_sample_memory`, the memory budget of the samples in bytes with requested and effective sizes (`requested_k`, `reason`) and the warning `sample_budget`, batches bounded by size, optional `run.counters`. | Lot 2c of the Scan and JSON work. Defaults of the plan accepted by the maintainer on 2026-10-08 (`selection` describes the listed values only, estimate in two parts, budget in bytes with no floor); the session chose 512 MiB instead of 256 so that a realistic 34-column scan is never cut, and added a fair share per field to first come first served. |
| 2026-10-08 | SJ-3a | Sections 18.1, 18.4, 18.7, 18.9, 18.10: samples by length (`values.samples.by_length`, `LengthStrataSampler`, `OtherLengths`), pool of values shared with the sample by `id`, `partial` accuracy, settings `max_samples_per_length` and `max_length_strata`, the sub-budget of an eighth, counters `strata_fields`, `strata_limited_fields` and `length_model_bytes`, priorities shared between the sample and its strata. | Lot 3a of the Scan and JSON work. Defaults of the plan accepted by the maintainer on 2026-10-08 (disposition `by_length` with shared ids and a pool, static reservation with `drop` as an API only, strata only for a `bottom_k` sample, every stored type, 100 values and 64 lengths, an eighth of the budget, Report without members). |
| 2026-10-08 | SJ-2c | Section 16.3: scan and report documents are written compact by default; the top-level `output.json_indent` setting indents them with each sample entry on one line (`json_text.dump_json`). `executions.json` and the Inspect file stay indented. | Weight of the Scan (24.9 MB indented, 10.4 MB compact, 13.5 MB indented with one line per entry on `insurance-ontario`); arrays `[value, count]` refused to keep the format self-describing. Maintainer decision of 2026-10-08. |
| 2026-10-08 | SJ-3b | Sections 9.10, 15 and new 18.11: the row sample (`records.sample`, `RowSampler`, `RowPriority`), first rows, a bottom-k of the interior by a priority of the position and last rows, cells of the same row for every projected field, settings `records.sample` (`rows`, `edge`, `cell_chars`, `max_bytes`), the byte budget, the Report keeping the header only. | Lot 3b of the Scan and JSON work: ROW-01 to ROW-11 and C01 to C06. |
| 2026-10-08 | SJ-4a | New section 18.12 and notes in 12.7, 18.6, 21, 15, 16.1: pattern inference from the samples (`scanner/patterninfer.py`), `derived.patterns` in the base model (`ScanResult.derived`, carried by the Report, left out of `facts_sha256`), grammar version 1, candidates with exclusive classification and overlaps, settings `scan.pattern_inference`, `run.timings.derived`, validator and schema, a `failed` entry per field with the `pattern_inference_failed` error. | Lot 4a of the Scan and JSON work: D08, PAT-01 to PAT-06, C07 to C10. Defaults of the plan accepted by the maintainer on 2026-10-08 (placement in `derived`, active by default, no pattern for exposed fields, no row sample estimate, quoted literals in the rendering, literal after 5 values). |
| 2026-10-08 | SJ-4b | New section 18.13 and decision O34, notes in 10, 12 (diagnostics), 15, 16.1, 19.2 and 19.7: `observations` in the base model beside `derived` (`scanner/quality.py`), observations of 13 versioned rules with a status (`informational`, `candidate_anomaly`, `confirmed_issue`), limits apart, summaries and the flags `has_observations`, `has_quality_issues`, `has_limits` for the scan and each dataset, settings `scan.observations` (`enabled`, `max_items`), left out of `facts_sha256` and carried by the Report; normalization stages gain `equals` (a stage that changed nothing takes the count of its input after the table was released) and `variant_groups` is exact and empty when no stage changed anything. | The exact `changed` counters prove what the dropped table cannot; QUAL-01 to QUAL-05 and D13. Maintainer decisions of lot 4b (flags at scan and dataset level, statuses of version 1, no severity, the stage keeps the envelope of its input without the estimate, thresholds as constants of the rule version, the Report keeps its issues until lot 5). |
| 2026-10-08 | SJ-5 | New section 18.14 and notes in 9.10, 16.4, 18.11, 18.13, 19.3, 19.4b: the report pages read the observations, limits, patterns and row sample of the base through `report_sections` and `report_labels`; the projections `issues`, `preview`, `limits`, `with_issues` and `with_issues_column_count` are removed; `records.preview` and `scan.records.preview` are removed (the start of the row sample replaces them); `report.row_sample` and the reduced row sample of the Report; accuracy vocabulary; display budgets; integers are never rounded by the report. | Lot 5 of the Scan and JSON work: D19, HTML-01 to HTML-09, F01 to F04 and F06. Maintainer decisions of 2026-10-08 (remove the preview, 10 rows per part, remove the stored projections with "not computed" when the block is missing, "Quality issues" in the sense of QUAL-03, light Scan rendering through `report --scan`). |
| 2026-10-08 | SJ-6a | New section 20.5 and decision O35, notes in 3 and 20.1: the registry of analyzers and the planner (`scanner/planner/`), six built-in analyzers with the rows of the decision tree, the plan (candidates, applicability, costs in three scenarios, utility, decision with a reason code, `already_satisfied` with its `satisfied_by`), selection under a firm memory budget with shared states and one common reading, `plan_analyses`, `plan_document`, `generate_plans` and `tabalyst scan --plan`; `facts_sha256` moves to `scanner/identity.py`. | Lot 6a of the Scan and JSON work: D11, PLAN-01 to PLAN-06, D01 to D03. Maintainer decisions of 2026-10-08 (placement in `scanner/planner/`, planning on merit with an `available` flag, `--plan` reuses or makes the first pass and never runs the second, provisional costs until lot 6b, public page now). |
| 2026-10-08 | SJ-6b | New decision O36, sections 20.2 and 20.3 rewritten, new 20.6, notes in 20.1 and 20.5: the calibrated cost model (`scanner/planner/costmodel.py`, `cost_model_version`), two memory levels (128 MiB automatic, 512 MiB hard), the forced plan (`plan_analyses(forced=)`, `scan --plan --deep`), `summary.beyond_automatic`, `costs.cell_ns`, `execution.on_limit`, the time estimate kept out of the plan, the confirmation (`plan_second_pass`, `combine_confirmations`, `cli/confirm.py`, exit code 3) and the source guard (`source_guard.py`). | Lot 6b of the Scan and JSON work: COST-01 to COST-05, PASS2-01, PASS2-06, D04, D05, D08, rule R1. Maintainer decisions of 2026-10-08 (two memory levels, forced mode lifts the automatic limits, 120 s on the upper bound, `--yes` and `--deep` execution at lot 7a, exit code 3, no column budget before lot 8a). |
| 2026-10-09 | SJ-7a | New decision O37, new section 20.7, sections 20.1, 20.3, 20.4 (rewritten), 20.5 and 20.6 updated, notes in 20.2: the executor of the second pass (`scanner/secondpass/`) with the replay of the first pass's reading of a cell, the agreement check with the Scan, exact counters and bins with exact edges, quantiles by one convention (exact or estimated with certain bounds), `deep.bins` and `deep.bin_strategy`, the document `tabalyst.scan.deep` with its key, partial reuse and schema, `tabalyst scan --deep` and `--yes`, exit code 3, the Python entries `run_second_pass`, `prepare_deep`, `execute_deep` and `generate_deep`, CPU classes remeasured on the executor (limits 100, 600 and 2,400 ns), the method `linear_bins` renamed `bins`. | Lot 7a of the Scan and JSON work: D02, D09, D10, D22, PASS2-01 to PASS2-05, HIST-01 to HIST-07, CACHE-01 to CACHE-05, A07, A12, A15, D03, D04, D05 (executor halves), D09 to D11. Maintainer decisions of 2026-10-09 ("oui a tout" to the plan: Python entries, planning for what can run, `deep` settings outside the identity of the Scan, exit code 3 for a refused or declined confirmation, location of the document, shared reader factory, two bound strategies). |
| 2026-10-09 | SJ-7b | New decision O38, new section 20.8, notes in 20.2, 20.4, 20.5, 20.6 and 20.7: the executor of `exact_distinct` (`secondpass/exactset.py`: one set per kind of key, strings of up to 18 digits as integers by length, a pool of the bytes the plan gave, `limited` with a lower bound when the pool cannot hold it) and of `exact_frequencies` (`secondpass/frequencies.py`, always a table keyed by native type and analytical text; the `dense_counts` method and the dense state shared with the histogram are dropped), the results `distinct`, `distinct_limited` and `frequencies`, the `original` domain of an analysis, the measured model of the exact set (`EXACT_SET_FIXED_BYTES`, `SET_SMALL_*`, `FREQUENCY_KEY_BYTES`, `cost_model_version` 3), `NS_PER_CELL` of the set (400) and the table (120), `EXECUTABLE` derived from the registry. | Lot 7b of the Scan and JSON work: D03, EXACT-01 to EXACT-07, D06, D07, D08 (executor half). Maintainer decisions of 2026-10-09 ("oui a tout" to the plan: keys by kind with integer sets by length for digit strings, a table for the frequencies, a lower bound published when a field is stopped). |
| 2026-10-09 | SJ-7c | New decision O39, new sections 20.9, 20.10 and 20.11, notes in 18.12, 20.1, 20.2, 20.4 and 20.5: the executors of `pattern_validation` (`secondpass/patterns.py`: compiled possessive regular expressions for ASCII values, the token matcher for the rest, exclusive classification, overlaps, reconciliation, derivation from the exact counts of the Scan without reading) and `temporal_distribution` (`secondpass/periods.py`, dates as written, ambiguous counted apart), `CellReader.cells(dates=)`, `skip_reading`, `reading_candidates`, the datetime columns as temporal fields, `NS_PER_CELL` of the matcher (800 plus 100 a candidate) and the period (1,600), `cost_model_version` 4, `deep.mode` and `DeepSection`, the second pass inside the Report (`report_chain.py`, `deep_store.py`, `report --deep`, `--yes`, exit code 3, `analyses` in the Report) and its pages. | Lot 7c of the Scan and JSON work: D02, D08, PAT-07 to PAT-11, TIME-01 to TIME-03, 18.2, A13, A14, C11, D12. Maintainer decisions of 2026-10-09 ("oui a tout" to the plan). |
| 2026-10-09 | SJ-8a | New decision O40, new section 20.12, notes in 20.2 and 20.5: the pair analyses (`planner/relations.py`: exploration of the row sample, column and work budgets, `relations` in the plan, candidates with `partner` and `exploration`; `scanner/pearson.py`: stable co-moments, Chan merge, Fisher interval; `secondpass/pearson.py`: `ColumnFeed`, `PairAccumulator`, the result `pearson`; `Router` hands aligned rows to the pairs), `deep.pearson` settings (`PearsonSettings`), `Budgets.automatic_pairs`, `AnalysisRequest.partner`, `NS_PER_CELL["pearson"]`, `cost_model_version` 5. | Lot 8a of the Scan and JSON work: D13, D14, REL-04 to REL-10, COST-05, E01, E02. Maintainer decision of 2026-10-09 (followed the assistant's recommendations: exploration at plan time, complete sample without reading, float64, defaults of `deep.pearson`, automatic pairs limited to eight). |
| 2026-10-09 | SJ-8b | New decision O41, new section 20.13, notes in 18.12, 18.14, 20.2 and 20.5: the tables of a category against a feature (`scanner/features.py`: the classes of a category and of the features `pattern`, `length` and `prefix`, `PatternClassifier` shared with the validation; `scanner/crosstab.py`: margins, purity in both directions, Cramér's V and its bias-corrected form; `planner/crosstabs.py`: exploration of the row sample, `planner/samplerows.py` and `planner/identifiers.py` split out of the exploration of the pairs; `planner/analyzers/crosstab.py`; `secondpass/crosstab.py`: `CodeFeed`, `CrosstabAccumulator`; the result `crosstab`), `PairAnalyzer` and `PairProposal` in the planner, several feeds on a column in the router, `Relations.tables`, `Budgets.automatic_tables`, `AnalysisRequest.feature`, `deep.crosstab` settings (`CrosstabSettings`), the domain `mixed`, the Relationships section of the report (`report_relations.py`, sections renumbered), `NS_PER_CELL` of the three features, `cost_model_version` 6. | Lot 8b of the Scan and JSON work: D14, REL-01 to REL-03, REL-11 to REL-16, E03 to E05, HTML-06. Maintainer decision of 2026-10-09 (approved the plan and its defaults: nulls outside the table, one automatic feature per pair of columns, prefix of two characters from the Scan, 0.45 and 0.9 thresholds, three examples per cell, no separate estimate over the row sample). |
| 2026-10-09 | SJ-9 | New decision O42, new section 20.14, notes in 20.5: the help with stratification (`scanner/stratify.py`: `allocate_strata` moved from `sampling.py`, `saturating_product`, `size_for_every_stratum`; `planner/stratification.py` and `planner/stratmodels.py`: `Stratify`, `advise_stratification`, `with_stratification`, `AnalysisPlan.stratification`; `reasons.STRATIFICATION`), several fields and `max_strata` in `sample`, the balance of strata in `SampleResult`, `scan --plan --stratify`, `--stratify-by` and `--sample-size`. | Lot 9 of the Scan and JSON work: D16, D17, STRAT-01 to STRAT-08, E06 to E08. Maintainer decision of 2026-10-09 ("ok" to the plan and its defaults: CLI options on `scan --plan`, no HTML in this lot, thresholds 50, 1,000, 10,000 and 100,000, a missing value as a stratum of its own). |
| 2026-10-09 | SJ-10a | New decision O43, new section 20.15, notes in 20.5 and 20.14: the targets and the plan of a smart sample (`scanner/smart/`: `SamplingPlan`, the six families of targets, `weights.py`, `plan_sampling`, `Smart`, `sampling_plan_text`), the `smart` settings (`SmartSettings`, `SmartWeights`, `smart_settings`), `PlanSuccess.sampling`, `generate_plans(smart=)`, `scan --plan --smart`. | Lot 10a of the Scan and JSON work: D15, SMART-01 to SMART-04, 15 of the specification, E09, E12, E14. Maintainer decision of 2026-10-09 ("ok avec tout": an autonomous plan document, a top-level `smart` object, the relations family in this lot, D23 left to lot 10b). |
| 2026-10-09 | SJ-10b | New decision O44, new section 20.16, notes in 20.14 and 20.15: the selection of the rows of a smart sample (`scanner/smart/`: `evaluate.py`, `select.py`, `execute.py`, `estimate.py`, `result.py`), the document `tabalyst.sample` and its schema, `tabalyst sample --sample-method smart` (`--yes`, exit code 3), `smart_service.py` (`prepare_smart_samples`, `execute_smart_samples`, `SelectionConfirmationRequired`), `SampleResult.report` and `smart`, D23 for `stratified` (`shared_scan_service.stored_scan`, `max_strata` explicit allows the run), `source_guard.check_plan_base` for any plan that stands on a Scan. | Lot 10b of the Scan and JSON work: SMART-05 to SMART-13, D15, D23, E10, E11, E13, E15. Maintainer decisions of 2026-10-09 (the plan and its defaults, "OK pour le reste"). |
| 2026-10-09 | SJ-10b | New section 16.8: the web page of an explicit `tabalyst scan` (`scan_page.py`, `generate_scans(html=)`, `ScanJob.page`, `prepare_deep(html=)`, `--no-html`). | Maintainer decision of 2026-10-09: an explicit scan writes the page, an automatic scan does not ("ok pour tout" to the name `<stem>.scan.html`, the report rendered from the Scan alone, and the cost measured first). |
| 2026-10-09 | SJ-11 | New decision O45, new section 20.17, notes in 20.13 and 20.16: unstable tables rank last, mirrored pairs collapse in the report, the web page of a smart sample (`sample_page.py`, `templates/sample.html`), the contract of Explore (`tests/scan/test_explore_contract.py`), the final matrix (`tabalyst-lab/benchmarks/final_matrix.py`, `matrix_layouts.py`). | Lot 11 of the Scan and JSON work: the arbitrations left open by lots 8b and 10b, EXPLORE-01 to EXPLORE-05, F07. |
| 2026-10-10 | SJ-12 | New decision O46, new section 20.18, notes in 13 and 20.7: lazy imports of the package, at most 6 workers for the first pass, the routes of the fields of a CSV file in worker processes in the second pass (`scanner/secondpass/parallel.py`, `workers.py` `_Worker(entry=...)`, `run_second_pass(workers=)`, `ChainPlan.workers`, `DeepPreparation.workers`). | Lot 12: memory of the first pass (+42%) and overhead of the Report (+107%) accepted at lot 11 for the time being. |
| 2026-10-11 | IN-13 | New decision O47, notes in 18.13: `numeric.coverage`, the refusal of `numeric` for codes, the rule `minority_length` (observations version 2), `report_measures.py`, Scan and Report format revision 3. | Insight lot 13: manques 2 and 3 of the technical documentation 10.29, leads A1 to A3 of 10.30. |
| 2026-10-11 | IN-14 | New decision O48, new section 20.19, rows in 20.5 and 20.2: `measure_extraction`, `secondpass/measures.py`, `CellReader.cells(measure=)`, `deep.measures`, `COST_MODEL_VERSION` 7, second-pass document revision 2. | Insight lot 14: manque 1 and the remaining part of manque 4 of the technical documentation 10.29, lead B1 of 10.30. |
| 2026-10-11 | IN-15 | New decisions O49 and O50, new sections 20.20 and 20.21, rows in 20.5 and 20.2: `residual_values` (`secondpass/residuals.py`) and `duplicates_report` (`secondpass/duplicates.py`, also a `PairAnalyzer` with `per_field`), `CellReader.readings`, `detectors.registry.replayable`, the record handed to the routes, `deep.residuals` and `deep.duplicates`, `COST_MODEL_VERSION` 8. | Insight lot 15: leads B2 and B6 of 10.30 of the technical documentation. |
| 2026-10-11 | IN-16 | New decision O51, new section 20.22, notes in 20.12 and 20.13: `slope`, `intercept`, `r_squared` and `rank` of `PearsonResult`, `scanner/rankcorr.py`, `secondpass/ranks.py`, `deep.pearson.rank_bins`, the `rank_*` members of `Exploration`, the feature `value`, `deep.crosstab.max_exception_cells`, `exceptions.complete`, `AnalysisRequest.rules` and `provided_rules`, `COST_MODEL_VERSION` 9. | Insight lot 16 (16a and 16b): lead B3 of 10.30 of the technical documentation, in part. |
| 2026-10-11 | IN-17 | New decision O52, new section 20.23, a row in 20.5 and a note in 20.22: `category_stats` (`planner/analyzers/stats.py`, `planner/categorystats.py`, `secondpass/stats.py`, `scanner/correlation_ratio.py`), `StatsResult`, `Relations.stats`, `Budgets.automatic_stats`, `deep.stats`, `COST_MODEL_VERSION` 10. | Insight lot 16c: lead B3 of 10.30 of the technical documentation, the rest of it. |
| 2026-10-11 | IN-18 | New decision O53, new section 20.24, a row in 20.5: `numeric_shape` (`planner/analyzers/shape.py`, `secondpass/shape.py`), `ShapeResult`, `deep.shape`, `FieldRoute.shape`, `binned_quantile_fractions`, `exact_quantile_fractions`, `distinct_band`, `COST_MODEL_VERSION` 11. | Insight lot 17a: lead B5 of 10.30 of the technical documentation. |
| 2026-10-11 | IN-19 | New decision O54, new section 20.25, a row in 20.5: `datetime_parts` (`planner/analyzers/parts.py`, `secondpass/parts.py`), `PartsResult`, `deep.datetime`, `FieldRoute.parts`. | Insight lot 17b: lead B4 of 10.30 of the technical documentation, and the A4 lead for dates. |
| 2026-10-12 | IN-20 | New decision O55, new section 20.26: `inferred_order`, `date_evidence`, `DateResolution`, `CellReader.cells(dates=<order>)`, `deep.datetime.infer_order`, the plan parameter `date_order`. | Insight lot 17c: the maintainer's rule for ambiguous dates. |
| 2026-10-12 | IN-22 | New decision O57, new section 20.28: `MeasureFacts.convention` and `readable`, the plan parameter `number_convention`, the reason `ambiguous_numbers_read_by_evidence`, `CellReader.cells(convention=)` and `measure_detector(detector, convention)`, `Measure.resolved`, `MeasureAccumulator.convention` and `resolved`, `NumberResolution`, `MeasureResult.resolved` and `resolution`, `dotted_thousands` for a format with affixes. | Insight lot 17d.2b: values with a unit follow the rule of the numbers. |
| 2026-10-12 | IN-21 | New decision O56, new section 20.27, notes in 9.4 and 12.6: `scanner/convention_rule.py` (`single_reading`, `NumberRule`, `scan_convention`), `ThousandsReadings` and `NumericAccumulator.absorb`, `DetectorSet.number_convention`, `CellReader.for_field`, `detectors.number.infer_convention` and `min_evidence`, `resolution` with `source: evidence`. | Insight lot 17d.2a: the maintainer's rule for ambiguous numbers (gate N). |
| 2026-10-12 | IN-23 | New decision O58, new section 20.29, a row in 20.17: `report_insights.py`, `InsightCard`, `templates/insights.html`, the Insights sections of the Report and of the column page, the resolution of the dates in the Dates section, `tests/scan/test_report_insights_html.py`, `test_explore_06`, `automatic_stats` 2. | Lot 20 of the Insight milestone: the Report reads what lots 13 to 17d add, the cost model is reviewed with the replayed matrix. |
| 2026-10-12 | IN-24 | New decisions O59 and O60, new sections 20.30 to 20.32, two rows in 20.5 and a note in 20.17 and 20.29: `position_drift` (`planner/analyzers/drift.py`, `secondpass/drift.py`) and `missing_matrix` (`planner/analyzers/matrix.py`, `secondpass/matrix.py`), `PositionDriftResult`, `MissingMatrixResult`, `DriftSettings` and `MissingSettings` (`deep.drift`, `deep.missing`), `FieldFacts.records`, `matrix_member`, `matrix_size`, `records_excluded`, `matrix_members`, `FieldRoute.drift`, `Router(matrices=)`, `native_key`, `InsightCard.scope`, the families `drift` and `missing`, `COST_MODEL_VERSION` 12, `tests/scan/test_insight_lot19.py`, `tests/scan/test_report_drift_html.py`. | Lot 19 of the Insight milestone: leads B9 and B11 of 10.30 of the technical documentation. |
| 2026-10-12 | IN-25 | New decisions O61 to O64, new sections 20.33 to 20.36, rows in 20.5, notes in 12.8, 20.17 and 20.29: `array_profile`, `structure_variants` (`planner/analyzers/structure.py`, `secondpass/structure.py`), `text_profile`, `fingerprint_distinct` (`planner/analyzers/texts.py`, `secondpass/texts.py`), `sensitive_forms` (`planner/analyzers/forms.py`, `secondpass/forms.py`), `ip_class` and `phone_class`, `ArrayProfileResult`, `StructureResult`, `TextProfileResult`, `FingerprintResult`, `FormsResult`, `ArraySettings`, `StructureSettings`, `TextSettings`, `SensitiveSettings` (`deep.arrays`, `deep.structure`, `deep.texts`, `deep.sensitive`), `FieldFacts.arrays`, `objects`, `object_keys`, `object_varies`, `untracked_paths`, `dataset_fields`, `strings_content`, `classified`, `cells`, `ROOT_FIELD`, `root_facts`, `Analyzer.roots`, `FieldRoute.arrays`, `texts`, `fingerprints`, `forms`, `Router(structures=)`, `PARTS` `texts` and `forms`, the family accuracy `fingerprint`, `COST_MODEL_VERSION` 13, `tests/scan/test_insight_lot18.py`. | Lot 18 of the Insight milestone: leads B7, B8 and B10 of 10.30 of the technical documentation. |
| 2026-10-13 | PT-P1 | New decision O65, sections 18.12 and 20.9 rewritten: the contract of the hierarchical discovery and validation of patterns (eligibility, weighted population, families, patterns of fixed length, facets and score, tree, budgets, determinism, exposure, declared keys, target format of `derived.patterns` grammar 2 and of `pattern_counts` revision 2, PAT-12 to PAT-27), ADR `2026-10-13-hierarchical-patterns-fixed-lengths`, the tests of `tests/patterns/` marked by lot. No code of the engine changes. | Lot P1 of the Patterns plan. Maintainer decisions of 2026-10-13 (Porte 0, Q1 to Q9, "tout par defaut"). |
| 2026-10-13 | PT-C1 | New decision O66, section 9.2 rewritten, a note in 12.8: the character profile of `string_characteristics` (`scanner/characters.py`, `CharacterProfile`), `limits.max_special_characters` and `max_distinct_characters`, the column page of the Report, `tests/scan/test_character_profile.py`. Format revision 4 (in preparation). | Lot C1 of the Patterns plan: the first pass counts the classes and the characters of the strings. |
| 2026-10-13 | PT-P3 | Section 18.12: the discovery of families and patterns of fixed length (`scanner/patterninfer.py` rewritten: families by structure key, merge of composition at the edge of a block, one pattern per combination of lengths, constants folded, budgets `max_values`, `max_families`, `max_patterns_per_family`, `max_patterns`, table of lengths), grammar 2 and `ALGORITHM_VERSION` 1, the models of the hierarchy (`PatternFamily`, `FamilyPattern`, `PatternNode`, `PatternTable`, `PatternOtherStructures`), the flat view `FieldPatternsComplete.candidates` that the consumers read until P6 and P7, `check_scan` of the sums, `tests/patterns/pattern_adapter.py` (`discover`, `published_text`), lot P3 enabled. Format revision 4 (in preparation). | Lot P3 of the Patterns plan. |
| 2026-10-13 | PT-P4 | Section 18.12: the content facets, the score and the tree (`scanner/patternfacets.py`: heads, tails and whole tokens read as prefixes, gain and sigma in bits, the G test and `beyond_chance`, `dependence`; `scanner/patterntree.py`: the primary facet, the nested dependent facets, the compressions, the depth cut; `patterninfer.py`: the signature of a node, the tables of content, the cap of three characters on folded constants, `max_patterns` removing the lowest gain first), the setting `max_depth` and its limit, the models (`PatternNode.nodes`, `facet`, `gain`; the tables of content of `PatternTable`), the checks of `check_scan` on nested nodes and tables, `FieldPatternsComplete.unmatched` counting the table of lengths only, lot P4 enabled in `tests/patterns`. Format revision 4 (in preparation). | Lot P4 of the Patterns plan. |
| 2026-10-13 | PT-P6 | Section 20.9: the validation of the hierarchy (`secondpass/patternreader.py`, the reader compiled from the entry and from the population of the discovery, checked against the samples; `secondpass/patterns.py`, the accumulator: exclusive counts by pattern and node, tables of the facets bounded in bytes, new variants of length and of segment, distinct values with their accuracy, sums checked), the models `PatternCounts` (revision 3 of the second-pass document: `families`, `unknown_structure`, `algorithm_version`; `candidates` and `other` remain as views), the settings `deep.patterns` (`table_bytes`, `distinct_bytes`), `PatternNode.value` and `PatternNode.also` in the Scan (a node is read by the text it fixes and by what the nodes merged into it fix), the analyzer method `family_recognizer`, `NS_PER_CELL["pattern_family"]` and `["pattern_facet"]`, `COST_MODEL_VERSION` 14, `tabalyst-lab/benchmarks/pattern_validation.py`, lot P6 enabled in `tests/patterns`. | Lot P6 of the Patterns plan: FR-004, FR-013 to FR-015, TR-002 to TR-005, TR-007, TR-009, AC-005, AC-013 to AC-017, AC-027. |
| 2026-10-13 | PT-P7 | Sections 18.12, 18.13, 20.9 and 20.20: the consumers of the flat list read the hierarchy (`FieldPatternsComplete.candidates` and `.unmatched`, `PatternCounts.candidates` and `.other` and their models are gone; `all_patterns()` and `outside_patterns()` walk the families). `check_scan` checks `value`, `also` and the signatures against the samples, `check_pattern_counts` the result of the validation; `minority_pattern` compares the patterns of the hierarchy; `PatternCoder` and `residual_values` classify with `HierarchyReader.pattern_class` (the pattern of the family that has the lengths of the value); the identity of a Scan and the key of `pattern_validation` hold the grammar and algorithm versions and the digest of the discovery settings (`patterninfer.discovery_versions`, `settings_digest`). The Report lists the patterns of the hierarchy (`PatternRow`). | Patterns lot P7: consumers (FR-020, FR-021, AC-021, AC-022). |
| 2026-10-12 | IN-23 |
| 2026-10-17 | R10b | Section 19.3: the Report holds, per column and dataset, the qualified findings, Overview, Details, signals and quality as codes and numbers (contract `docs/dev/report/summary-table.md` section 20); exposure applied once at the build; the Report no longer promises to contain the Scan for members no page reads (20.5 of the contract, Explore 20.17 unchanged until amended). | Report overview work, lot R10b: maintainer decision of 2026-10-17 (ADR 2026-10-17-report-summary-built-with-the-document). |

## 18. Bottom-k samplers (O26, O28)

### 18.1 Named approximations (O26)

Principle 1 admits an estimate when it is named. An estimate carries
`accuracy: "estimated"`, its `method` and its `parameters`, and never the
status `complete`. Accuracy values: `exact`, `estimated`, `fingerprint_based`
(equality of a digest, not of the full value), `partial` (a count that covers
only the occurrences from a recorded point on, 18.7) and `unknown`. Two approximations
are planned: the KMV estimate of a cardinality (18.5) and quantiles rebuilt
from histogram bins (second pass). Everything the Scan already measures stays
exact for its population.

### 18.2 Tracking limit and sample size (O28)

T, the number of distinct original values tracked exactly, and K, the size of
the bottom-k sample, are two settings of `scan.limits` (the base configuration,
`ScanConfig` in `scanner/config.py`, with their hard caps in `HARD_CAPS`):

| Setting | Meaning | Default |
| --- | --- | --- |
| `max_distinct_per_field` (T) | Distinct values kept in the exact table | 100,000 (unchanged) |
| `max_samples` (K) | Size of the sample the Scan keeps, in its output (the bottom-k sample from lot 2b) | 10,000 since lot 1a (100 before); hard cap 100,000 |

`max_samples` is the existing parameter, evolved rather than doubled by a new
one: it was the size of the sample in the output and it still is. K cannot
exceed T (configuration error, as `max_distinct_per_field` cannot exceed
`max_tracked_values`). The default K is a starting value: lot 1a measures the
weight of the Scan with K entries per column (estimated at 6 to 7 MB for the
reference file, against 1.3 MB today) and the quality of pattern inference,
and may lower it; a KMV error of about 3% already serves planning at
K = 1,000.

Up to T distinct values the table is exact, as today, and no existing exact
measure changes. The first value beyond T proves overflow
(`lower_bound = T + 1`): the K best entries of the T + 1 seen are kept with
their exact counts (all of them were tracked from their first occurrence), and
the bottom-k continues on every later occurrence. A table that stays under T
keeps its sample as `all`, or reduced to its K best when it holds more than K.

Lot 1a delivers the setting: the default is 10,000, the cap is 100,000, an
explicit K above T is a configuration error, and a K that is not set follows a
lower T (a scan that lowers T alone keeps working, with K = T). Lot 2b draws the
sample with the bottom-k (18.3). The Report does not read K: it works on at
most 100 values of the sample (`value_examples.kept_per_column`, 19.4b), the
whole sample when it has no more, otherwise the 100 of smallest priority, so
its examples do not depend on K (a `bottom_k` sample gives its first 100
entries, an `all` sample is ranked by the Report with the same hash and seed).
Reading the whole sample made the Report quadratic: 0.6 s for 3,000 rows at
K = 100, 25 s at K = 1,000. `random_seed` is the seed of the hash: an unsigned
64-bit integer.

The first version of this decision (O28, 2026-10-06) set T = K = 10,000. The
baseline of lot 0 showed that it saves memory (715 to 536 MB on the reference
file) and no time, while it makes columns of 10,000 to 100,000 distinct values,
and the identifiers of every file of fewer than 100,000 rows, lose their exact
cardinality, complete frequencies and exact median until a second pass that
`tabalyst scan` never starts by itself. The maintainer therefore kept T and
separated it from K, on 2026-10-07. Lowering T remains possible if the global
memory budget (lot 2c) requires it, with a recorded reason.

### 18.3 Module `tabalyst.scanner.bottomk` (lot 2a)

The selection mechanism is isolated from the product metadata (specification
section 7). A key is `(native type, canonical original text)` (section 21), so
the string `"123"` and the integer `123` stay distinct.

| Name | Contract |
| --- | --- |
| `HASH_ALGORITHM`, `HASH_VERSION`, `HASH_BITS` | `"blake2b"`, 1 and 128: the priority function, its version and its width (18.8). |
| `priority(key, *, seed=0) -> int` | Stable priority in `[0, 2**128)`, from the full key and the seed (an integer in `[0, 2**64)`, else `ValueError`); never the builtin `hash()`. |
| `BottomKSampler(k, *, seed=0, priority=None)` | `priority` replaces the function in tests (injected collisions). `k` and `seed` are attributes. |
| `BottomKSampler.from_exact(k, counts, *, seed=0, priority=None, overflow_at_occurrence=None)` | The sample of an exact table of `counts` (key to exact count) that holds more than K keys: the K best, with their counts. The engine uses it at the overflow of its table of T keys (18.2); the result equals streaming the same keys. |
| `BottomKSampler.from_exact_strings(k, texts, counts, *, seed=0)` | `from_exact` for keys of the type `"string"` given as texts: the same sample, hashing in a tight loop and keeping only the K best (the engine's release of a table of strings, lot 2b). |
| `.add(key, count=1)` | One or `count` occurrences; `count` below 1 is a `ValueError`. |
| `.update(keys, counts)` | A batch of distinct keys with their counts (the engine's hot path: its batches of 4,096 distinct values, section 13), equivalent to adding the occurrences one by one in any order. Counts are not checked. |
| `.update_strings(texts, counts)` | `update` for keys of the type `"string"` given as texts (the engine's hot path, lot 2b): once the sample is full, a text whose priority is above the limit is rejected before any key is built or looked up. Same result as `update`; with an injected priority it defers to `update`. |
| `.entries()` | `Entry(key, priority, count)` ordered by `(priority, key)` ascending. |
| `.occurrences` | Occurrences added. |
| `.retained` | Keys in the sample (at most K). There is no `__len__`: an empty sampler must not be falsy. |
| `.distinct_exact` | True while no overflow happened and no entry was dropped. |
| `.overflow_at_occurrence` | 1-based occurrence number of the first occurrence of the (K + 1)th distinct key, else `None`. |
| `.threshold` | Largest priority of the sample once it is full after an overflow, else `None`. |
| `.reduce(k)` | Keeps the smaller priorities; a larger `k` raises `ValueError`; entries dropped make `distinct_exact` false. |
| `.kmv()` | `KmvEstimate` or `None` (18.5). |

Rules (BK-01 to BK-07, tests B01 to B06 and B09):

- The priority depends only on the key and the seed. Equal priorities are
  ordered by the complete key, ascending. Distinct keys are never merged.
- Every distinct key is kept, with its count, until K is exceeded. The first
  overflow keeps the K best of the K + 1 keys, with their counts.
- An occurrence of a retained key increments its count. An unretained key
  enters only if its priority is below the threshold, and then replaces the
  worst entry.
- The threshold never increases. A key that left never comes back, so a key of
  the final sample was admitted at its first occurrence and never left: its
  count is the exact count of the whole stream.
- The sample is a function of the set of distinct keys, not of their order
  (B03), of the seed and of K.
- K can shrink to the smaller priorities; it cannot grow, because values
  rejected earlier are lost (B09).

Implementation (lot 2a). The sampler does not keep a heap: it admits a key
whose rank `(priority, key)` is below the limit of the last compaction, and
compacts (sort, cut to K, new limit) when the first overflow is reached (K + 1
keys) and then every half of K admissions. A key of the final sample is below
every intermediate limit, so it is admitted at its first occurrence and never
lost; the public members settle to exactly K keys first. The limit compares the
complete key on equal priorities, which a heap of integers could not do. Memory
at K = 10,000 is about 5.3 MB per field (550 bytes per entry, with the keys
and the compaction slack).

Where the state lives (confirmed at lot 2a, built at lot 2b). The sample of a
field belongs to the field's `ValueProcessor` (`scanner/valuesample.py`,
`ValueSample`), the object that already receives the released table
(`release`) and then the streaming batches (`process`) of distinct values with
their counts: in the scan process of a one-process scan, in the worker of the
field in a parallel scan (section 13, item 7). The engine's `ValueTracker` keeps
only the exact table of at most T keys, so the scan process gets no new
per-value work. A `ValueSample` keeps a plain dictionary of original keys with
their counts, in first-seen order, and no hash, while the field has at most K
distinct values; the first batch that exceeds K hands that dictionary to
`BottomKSampler.from_exact`, and every later batch goes to `update`. A complete
table of more than K keys is handed to `from_exact` at finalization. Keys of
`str` are paired with the type `"string"` by `zip(repeat("string"), keys)`,
without a conversion loop. The sample reaches the scan process inside the
field's value block, as plain data like the rest. No merge between processes
is needed. A merge would nevertheless be
exact: a key of the global K best is among the K best of each partition that
holds it and was never dropped there, so its partial counts sum to the total
(useful for reading one source with several processes, section 13).

### 18.4 Counters

Counts of retained keys are exact (`count_accuracy: "exact"`) when the key
identity is exact. They are not a top-N and not a frequency table: the most
frequent value can be absent. Proportions among sampled distinct values are
not proportions of rows.

Work counters (PERF-02 and PERF-03, lot 2c). `BottomKSampler.counters` gives
the priorities computed (`hashed`), the keys that entered the sample
(`admitted`), the occurrences of keys it already held (`hits`), the keys
computed and refused (`rejected`) and the keys that left it (`evicted`):
`hashed = admitted + hits + rejected` for `update_strings`, and `hits` are not
hashed in `update`. They only move in branches that do work (admission, hit,
compaction), never per rejected key, so they cost nothing on the hot path and
are always kept. The long text sampler adds `hashed_texts` and `hashed_bytes`.
`scan(..., counters=True)` (`tabalyst scan --counters`) writes their sum over
the fields in `run.counters.sampling`, with the sizes granted (`k_effective_min`,
`k_effective_max`, `reduced_fields`, `strata_fields`, `strata_limited_fields`) and the bytes
reserved in the cost model (`sample_model_bytes`, `long_model_bytes`,
`length_model_bytes`); without the request the member is
absent. A counter that the scan did not measure is not written, never 0: bytes
hashed are known for the long texts only, and the peak memory is
`run.peak_memory_bytes` (null when the platform does not report it). Counters
belong to `run`: they are not facts and do not enter `facts_sha256`.

### 18.5 KMV estimate (lot 2a)

After an overflow, with `K > 2` and a valid sample, `KmvEstimate` gives
`estimate = (K - 1) / theta`, where `theta = threshold / 2**128`;
`relative_standard_error = 1 / sqrt(K - 2)`; `k`; `theta_hex` (the threshold
as 32 hexadecimal digits, since a 128-bit integer is not a safe JSON number).
`kmv_estimate(threshold=..., k=...)` raises `ValueError` for `k < 3`, a
threshold of 0 or one at or above `2**128`; `BottomKSampler.kmv()` returns
`None` instead for a threshold outside that range, which only injected
priorities produce. No estimate is made while the domain is exact. The estimate serves planning; it is not a count of
duplicates or a proof of uniqueness. Certain bounds (`lower_bound`,
`upper_bound`) stay separate from the statistical interval, and an estimate
may be published with a version clamped to them, with the raw value kept.
Test B13 controls the error distribution over several datasets and seeds, with
a tolerant fixed-seed check, never a bound per seed.

### 18.6 Long texts (lot 2c)

A value longer than `limits.max_stored_value_length` (1,000 characters of its
canonical text) is never stored. It is counted, measured and tested like any
value, and sampled apart.

`tabalyst.scanner.longtext.LongTextSampler(k, *, preview_chars, seed=0)` keeps
a small bottom-k of long texts (`limits.max_long_samples`, 100 by default; LONG-01
rules out thousands of descriptions). The text is read once: its digest is
`digest_of(native_type, text)`, BLAKE2b with a 128-bit digest of
`native type NUL text` in UTF-8 (lone surrogates kept), independent of the seed,
and the priority is that of the key `("digest", hexadecimal digest)` through the
sampler of 18.3, so the sample, its counts, its threshold and its KMV estimate
come from the same code. An entry stores `digest`, `type`, `preview` (the first
`preview_chars` code points, so valid UTF-8; `long_preview_chars`, 200 by
default, never above `max_stored_value_length`), `truncated`,
`original_length_chars`, `original_length_bytes`, `count` and
`identity_accuracy: "fingerprint_based"`: two texts are the same entry when their
128-bit digests are equal. Two texts with the same prefix are two entries (B07,
B08). The preview and the lengths of an entry are built when it is admitted;
a text that is not admitted costs one read. Memory is bounded by K entries
(`LONG_ENTRY_BYTES` plus the preview). A preview does not certify the pattern or
alphabet of the whole text (LONG-05): a pattern inference must not read it as
the value; the pattern inference of 18.12 excludes the long texts.

In the scan a field with long values has `values.samples.long_texts`
(absent otherwise): `{selection, k, requested_k?, preview_chars, occurrences,
kept, of, digest: {algorithm, bits}, hash?, threshold?, listed}`.
`occurrences` counts every occurrence of a long value, exactly (LONG-03: the
minimum, maximum, total and mean lengths are in `string_lengths`). `selection`
is `all` until a text was dropped, then `bottom_k` with `hash` and `threshold`.
Entries are `{id, digest, type, preview, truncated, original_length_chars,
original_length_bytes, count, count_accuracy, identity_accuracy}`. A field with
`max_long_samples` 0, or whose size the memory budget cut to 0, still counts the
occurrences and lists none (`k` 0), and then has no cardinality estimate. A
sensitive field lists none (`kept` 0): a preview and a digest are the value, and
its threshold is withheld like the one of the values.

The cardinality estimate of such a field adds two disjoint domains, the stored
values and the long texts (the split is by length of the original text): each
is exact while its sampler dropped nothing and a KMV estimate otherwise, and
`estimate.parts` gives them (`{domain, accuracy, value, relative_standard_error,
k?, theta_hex?}`). The estimate is their sum, its relative error is
`sqrt(sum((value_i * error_i)^2)) / sum(value_i)` and, with `parts`, `k` and
`theta_hex` belong to the parts. It exists once either domain dropped a key.
The certain bounds of 9.1 still clamp it.

### 18.7 Length strata (lot 3a, D07, LEN-01 to LEN-06)

`tabalyst.scanner.lengthsample.LengthStrataSampler(per_length_k, max_lengths)`
keeps a bottom-k per tracked length, with a bounded number of lengths. The
length of a key is the number of characters (code points) of its original text
(21): the engine's `string_lengths` stays the analytical histogram.

| Name | Contract |
| --- | --- |
| `.update_strings(texts, counts, priorities)`, `.update(keys, counts, priorities)` | A batch of distinct keys with their counts and priorities, which the caller computed once for the global sample (the hash is not computed twice). |
| `.from_exact_strings(...)`, `.from_exact(...)` | The strata of an exact table, equal to streaming the same keys; used when the global sample becomes a `bottom_k`, at which point the table holds every value with its exact count. |
| `.add(key, count=1)` | One key, for tests. |
| `.strata()` | `{length: Stratum}` in ascending length. A `Stratum` has `entries()`, `occurrences`, `retained`, `distinct_exact`, `threshold`, `count_accuracy` and `tracking_started_at_occurrence`. |
| `.other` | `OtherLengths`: `lengths` (distinct untracked lengths now) and `occurrences`. |
| `.limited` | True when `other.occurrences` is above 0. |
| `.drop(length)` | Gives a stratum up: its occurrences move to `other`. |

A length is tracked from its first occurrence while a place is free (first met,
first tracked: LEN-04 and the "fixed quota from admission" of the specification);
others are summed in `other` and `limited` is true (B11). Strata and `other` add
up to every occurrence the sampler received, also after a `drop`. A stratum is a
`BottomKSampler` of `per_length_k` keys with the priority of the global sample, so
the argument of 18.3 holds: a key retained was admitted at its first occurrence
and its count is exact (`count_accuracy: "exact"`). `drop(length)` is the hook
of the memory budget; a dropped length that returns, or a length of `other` that
meets a free place, is admitted late: its stratum has `count_accuracy:
"partial"` and `tracking_started_at_occurrence` after its first occurrence, and
no frequency of it is announced as exact (B12, LEN-05). Occurrences are numbered
from 1 in the order the sampler receives them (the keys of a batch in the order
of the batch).

Where it lives (`scanner/valuesample.py`). Strata exist for a field whose
sample is `bottom_k`, not for an `all` sample, which lists every value and so
every length: they start at the switch, seeded from the exact table
(`from_exact*`), then every batch gives them the priorities it computed for the
global sample (`bottomk.string_priorities`, `priorities`; `update_strings`,
`update_ranked` and `from_exact*` accept them). Per key the strata add a `len`,
one dictionary lookup and one comparison against the admission limit of the
stratum (`BottomKSampler.admission_limit`); only the keys that can enter are
handed to a stratum. The values longer than `max_stored_value_length` are not in
the strata: they have `long_texts` (18.6), with their own lengths. As the global
sample, the strata are in the `ValueProcessor` of the field (the worker of the
field in a parallel scan), and no merge is needed.

Mutualisation (LEN-02). A value of a stratum that is in the global sample is
one entry: the stratum lists its `id`. Only the others are in
`by_length.listed`, with ids that continue the numbering (18.9). The two
samplers do hold their own keys in memory (the text is shared, the tuple and the
counters are not): the saving is in the document.

Combining (LEN-06). The strata and the global sample have different selection
laws; a consumer must not add them to estimate a proportion. A stratum gives
the exact `occurrences` of its length and a bottom-k of its values; the
global sample gives the values by global priority.

### 18.8 Hash choice and refusal threshold

Decided at lot 2a from the measures of `tabalyst-lab/benchmarks/bottomk_hash.py`
([benchmarks.md](benchmarks.md)): **BLAKE2b with a 128-bit digest**
(`HASH_ALGORITHM = "blake2b"`, `HASH_VERSION = 1`, `HASH_BITS = 128`). The
message is the 8-byte little-endian seed, then the type, a NUL character and
the text in UTF-8 (lone surrogates kept, `surrogatepass`); the seed is
absorbed once and the state copied for each key. It is the fastest function of
the 128-bit candidates (0.3 to 0.45 microseconds per key, encoding included;
SHA-256, SHA-1 and MD5 take 0.6 to 0.9, SHAKE-128 0.9 to 1.0) and BLAKE2s is no
faster. The 64-bit CRC-32 pairs, about 20% cheaper, are refused: 64 bits is
below the contract, and a linear checksum is not a hash whose independence
across seeds the estimate can rely on. No third-party library (xxHash, MurmurHash)
is added for a gain of about 0.2 microseconds per key. The KMV error on
sequential identifiers is within the model for every 128-bit candidate (12
seeds), so quality does not separate them.

The version is part of the output (`values.samples.hash`, 18.9). Changing the
function, the seed encoding or the key encoding raises `HASH_VERSION`; a golden
test (`tests/scan/test_bottomk.py`) pins the priorities of fixed keys.

Refusal rule: a candidate is refused when the first pass of the realistic dataset
regresses by more than 20% against the baseline of the same session, or the
worst-width dataset (30 columns including 5 unique identifiers) by more than
35%. The prototype of lot 2b (a patched `ValueProcessor`, throwaway) costs
3.4% on the combined file, 5.3% on the worst-width file and 3.4% on
`insurance-ontario` in the default parallel mode, where the workers hash. In one
process (`workers=1`, not the default) it costs 25%, 47% and 36%: the sampler
and the key conversion of the prototype, not the hash, which is about 0.35 of the
1.7 microseconds per key measured there. Lot 2b must bring the one-process cost down
(no conversion of keys, no intermediate table) and measure it again; the
parallel figures are its reference. Two levers are noted for it: a table of at
most K distinct keys needs no priority in the Scan (its sample is `all`; the
Report can hash its few kept values), and only a field whose sample must be cut
(a table above K, a released table) pays the hash.

### 18.9 Output (cardinality settled at lot 1a, samples and estimate at lot 2b)

`values.cardinality` is described in 9.1. The strata of lengths (18.7) are
`values.samples.by_length` (below).

`values.samples` also carries `requested_k` and `reason` when the memory budget
(18.10) granted a size K smaller than `limits.max_samples`: `k` is the size in
force, `requested_k` the one asked for and `reason` is `memory_budget`. They are
written only for a `bottom_k` sample that is smaller than asked (an `all`
sample, which holds every value, was not cut); `k` 0 means no value is sampled
(`kept` and `of` are 0) and the cardinality has no estimate. The `estimate`
uses the size in force (`k`). `long_texts` (18.6) is the member of the values
that are too long to be stored.

`values.samples` (lot 2b):

- `selection` is `all` when the sample holds every distinct original value
  (none was dropped or excluded): `listed` is in first-seen order, there is no
  hash and no `k`. Otherwise it is `bottom_k`: `listed` holds the sample (at
  most K entries, K being `limits.max_samples`) in ascending `(priority, key)`
  order, and the block names `k`, `hash` (`algorithm`, `version`, `bits`,
  `seed`) and, once a key was dropped, the `threshold` (32 hexadecimal digits).
- An entry is `{id, value, type, count, count_accuracy, identity_accuracy}`:
  `id` is the position of the entry in the `listed` of the Scan (kept by a
  Report that keeps a subset; the pool of lengths, below, continues the
  numbering), `value` the original text, `count_accuracy` and
  `identity_accuracy` `exact` (`partial` for a late stratum, `fingerprint_based`
  for the long texts).
- Exposure applies after the calculation on originals (21). `mask` merges the
  entries with the same mask in the order of the listing, counts added; `hide`
  lists none. `of` is always the number of originals sampled and `kept` the
  number listed, so exposure that withholds values shows as `kept < of`, which
  is the capability a planner reads (`complete_samples`) to refuse the sample
  (VAL-06). The `threshold` of a sensitive field (mode `mask` or `hide`) is not
  written: it is the priority of one of its values.

`values.samples.cases` (18.15) keeps the cases of the whitespace and minority length rules.

`values.samples.by_length` (lot 3a, 18.7), written for a `bottom_k` sample when
`limits.max_samples_per_length` and `limits.max_length_strata` are above 0 (and
absent for an `all` sample, whatever the lengths):

```
by_length: {
  domain: "original", unit: "characters",
  per_length_k, max_lengths, requested_max_lengths?, reason?,
  limited, tracked,
  strata: [{length, selection: "all" | "bottom_k", kept, of, occurrences,
            count_accuracy, tracking_started_at_occurrence?, threshold?, ids}],
  other?: {lengths, occurrences},
  listed: [entry]              # ids continue those of samples.listed
}
```

- A stratum lists `ids` of entries of `samples.listed` or of `by_length.listed`
  (the pool: values of a stratum that the global sample does not hold). Every id
  of a stratum exists, appears once, and names a value whose text has the length
  of the stratum (checked by `check_scan`). The pool starts at `len(samples.listed)`.
  `of` is the number of values the stratum sampled (at most `per_length_k`), `kept`
  the number listed. `occurrences` is the exact number of occurrences of the
  length since its tracking started. `tracking_started_at_occurrence` is written
  for a `partial` stratum only (an exact one began at the first occurrence).
  `threshold` is as in the sample: present once the stratum dropped a value, not
  for a sensitive field.
- `other` is written when `limited` and gives the untracked lengths and the
  occurrences counted into `other`; strata and `other` add up to the stored
  values of the field (`values.count` less the long texts). `limited` is
  also true when `max_lengths` is 0.
- Exposure: a sensitive field (mode `mask` or `hide`) keeps `length`, `of` and
  `occurrences` of its strata and lists nothing (`kept` 0, `ids` empty, no
  `threshold`, empty pool), the same capability declaration as the sample.
- Report: its base keeps the strata without their members (`kept` 0, no pool):
  the ids would point at values the Report does not hold (19.4). `facts_sha256`
  leaves the members out like the sample's.
- Memory budget: `max_lengths` is the number in force (18.10) and
  `requested_max_lengths` with `reason: memory_budget` the one asked for,
  written only for a field that has more lengths than the budget granted.

`values.cardinality.estimate` is written for a `limited` count when a sampler
dropped a key and every value reached a sample (a value that fits no sample,
because the memory budget granted a size of 0, would leave the estimator without
the whole field): `{accuracy: "estimated", method: "kmv", value,
unclamped_value?, relative_standard_error, k, theta_hex?}`. `value` is the
estimator held within `[lower_bound, upper_bound]`; `unclamped_value` is the
raw `(k - 1) / theta`, present only when a bound changed it; `theta_hex` is
absent for a sensitive field. A field with long texts has `parts` instead of
`k` and `theta_hex` (18.6). A complete count has no estimate: it is exact.

### 18.10 Memory budget of the samples (lot 2c, MEM-01 to MEM-06)

`limits.max_tracked_values` stays the budget, in values, of the exact tables
(section 11). The samples have their own budget in bytes,
`limits.max_sample_memory` (512 MiB by default), because K entries per field is
5 MB per field at K = 10,000 and a source of a thousand columns would take
gigabytes. It is a cost model, not a measurement: `memory.sample_entry_bytes`
(600 bytes of structure, which includes the slack held between two compactions,
measured at 540 bytes at K = 10,000, plus two bytes per character of the mean
stored value) and `memory.long_entry_bytes` (700 bytes plus four per preview
character). A test checks the model against `tracemalloc`.

`memory.SampleBudget` has three sub-budgets: the long texts take an eighth, the
samples by length another eighth (18.7), the samples of values the rest (MEM-01: keys, payloads, structure and compaction
slack of the samplers; the tables, the parser and the pending batches have their
own limits, 13). Sizes are reserved before the sample is built (MEM-04), in the
scan process only, in the order the source is read, so they do not depend on the
workers (principle 6):

- A released table reserves K entries for its field when it is released
  (`ValueTracker._grants`), at the record where the limit was proven, and the
  size travels to the field's processor in the `release` message.
- A complete table reserves its distinct values (at most K) in field order
  before any worker starts (`ValueTracker.reserve`, called by `ScanEngine.finalize`
  for every field).
- Long texts reserve their sample when the first long value of the field is met:
  at the release if it holds one, otherwise when the streaming batch that holds
  it is handed over (`long_k` travels with the batch). First come, first served.
- A field never takes more than the whole sample budget divided by the fields
  discovered so far: one wide source cuts every column alike instead of the
  late ones first. The size granted is `min(K, room / cost)`, 0 when not even
  one entry fits (MEM-06: the sampling of that field stops in a controlled way,
  the scan goes on, and the counters, lengths and exact tables are not touched).

The requested and the effective sizes are both in the document (MEM-03):
`values.samples.k` and `requested_k`, `values.samples.long_texts.k` and
`requested_k`, with `reason` `memory_budget` and the warning `sample_budget`
(one per scan, with the number of fields cut). Consequences are read from the
block: a cut sample is a `bottom_k`, its KMV estimate has the error of the size
in force, and a sample of size 0 has no estimate. No limit is ever lifted by a
request for an exact result (MEM-06); the exact tables are bounded by T and by
`max_tracked_values`, and lowering T stays the other way to spend less.

The cases of the observed rules (18.15) have an eighth of the budget (`memory.CASE_SHARE`), so the
samples of values keep five eighths.

The samples by length (18.7) have their own sub-budget, an eighth of
`limits.max_sample_memory` (`memory.LENGTH_SHARE`), so the samples of values
keep three quarters. A field that becomes a `bottom_k` reserves the cost of a
full stratum (`per_length_k` entries) for each of the `limits.max_length_strata`
lengths it may track, at the same places as K: a released table in
`ValueTracker._grants`, a complete table of more than K values in `reserve`
(it reserves its distinct values at most), and a table that fits its sample
reserves nothing. The grant is a number of lengths, `min(requested, share /
cost of a stratum)`, travelling with the sample's in the `release` and `table`
messages, so it is the same for 1 or several workers. The sampler's `drop` is
the hook for a budget that must take a stratum back; the engine does not call it
(a scan tracks every length from its first occurrence, and a grant of fewer
lengths sums the others in `other`), so a scan writes `exact` strata today.

Bounded states (MEM-02): the number of samples (K), their length
(`max_stored_value_length`, `long_preview_chars`), the long texts (`max_long_samples`) and the
batches (13) each have a bound. The lengths, patterns and error categories of
later lots will join this table. The warm-up values of a streamed field are
bounded by `detection.warmup_values` and by the stored length. A giant record
(MEM-05) cannot be split: the working memory of the parser is the largest record
(and, for CSV, the cells of a batch of at most 8 MiB).

### 18.11 Row sample (lot 3b, D12, ROW-01 to ROW-11)

Each dataset keeps a small sample of whole rows, taken in the one pass: the
first `edge` records, a bottom-k of the interior and the last `edge` records,
with the cells of every projected field of the same row (ROW-06). It is the
common storage of the Report (the rows to show) and of the analyses of later lots
(relations between fields, which need values of the same record). Names (ROW-01):
S = `records.sample.rows` (1,000), E = `records.sample.edge` (50) and the middle
M = S - 2E (900). K is the size of the sample of distinct values and does not
appear here.

`tabalyst.scanner.rowsample.RowSampler` lives in `RecordFacts`, so in the scan
process: the workers only receive the work per value. It has two entries, one
per reader item: `add_batch(start, rows)` for the CSV batches of strings (lot 6
of the engine, section 13) and `add_record(record)` for any other `Record`.
Both give the same rows (a test compares them, and random batch sizes); only
`bytes` differs, since a record costs more in the model than a row of strings.

- **Positions.** The position of a row is the index of its record, which counts
  the records a tolerant scan excluded (they have no row and leave gaps). `start`
  is the first `edge` records read, in reading order, not the records numbered
  1 to `edge`.
- **End and middle (ROW-03, ROW-04).** The records after the start wait in a
  buffer of the latest `edge`. A record that leaves the buffer is a candidate of
  the middle; the buffer at the end is the end. The two groups are disjoint, and
  no record of the start enters the buffer. Only candidates that leave the buffer
  can enter the middle, so the last `edge` records never do, even when their
  priority is the smallest (C03). The population of the middle is the positions
  `edge` + 1 to N - `edge`, `population.interior` of them, and the block says
  `population.scope: "interior_rows"` (ROW-07). The rows of the middle are not a
  uniform sample of the whole dataset (ROW-08): `RowSample.interior()` returns
  them alone, and an estimate over the whole population would need weights
  (not delivered).
- **Small datasets.** With N < 2E the end window overlaps the start: a record is
  stored once, with `origins: ["start", "end"]`. With N at most S every record is
  a row (`complete: true`): the interior fits in the middle. With N = 0 the
  sample has no row.
- **Priority (ROW-05).** `RowPriority(seed)`: the 64-bit priority of the
  position `i` is the number `i mod 8` of the eight little-endian 64-bit words of
  BLAKE2b with a 512-bit digest (personalization `tabalyst.rows.v1`) of the seed
  and the block `i // 8`. One hash call serves eight rows: 0.07 s per million
  rows against 0.28 s for a call per row (benchmarks.md, lot 3b). It never looks at
  the cells, so two identical rows are two observations with their own
  priorities (C02). `ROW_HASH_VERSION` is 1; the seed is `random_seed`. The ties
  of a 64-bit priority are broken by the position. The middle keeps the M
  smallest `(priority, position)` among the candidates: the same rows whatever the
  batches, the readers and the number of workers (principle 6).
- **Hot path.** The priorities of the candidates of a batch are computed together
  (`RowPriority.range`) and a batch is filtered once against the threshold of the
  middle; only the few rows that can enter are projected. The buffer holds
  references to the rows of the batch (to the `Record` for the record path), not
  copies, and a row is projected only when it is admitted, at the end for the
  buffer, and for the start. A reader that reused the observations of a record
  would break the record path: none does (a test reads JSON and JSONL).
- **Cells (ROW-06, ROW-09).** The cells of a record are its scalar observations as
  canonical text per path: a list when the path repeats
  (items of an array), `null` for a JSON null, no key for a path absent from the
  record. The cells of one path share `cell_chars` characters (200): the text
  that passes it is cut on a code point, the following values of the path are
  dropped, and the row lists the field in `truncated` (counted in
  `truncated_cells`). A table row projects all its columns. `fields` lists the
  projected field ids (those with a scalar value); `fields_limited` says that
  untracked paths (`limits.max_fields`) are not.
- **Exposure (12.8).** At the end: `mask` merges, `hide` writes
  a hidden cell as `null`; nulls and strings that are not content stay as read.
  The original values stay in memory until the end.
- **Budget (ROW-10, ROW-11, MEM-01 to MEM-06).** `records.sample.max_bytes` (16 MiB)
  is the budget of the rows kept by all the datasets of a scan, in bytes of a cost
  model (`rowsample.TABLE_ROW_BYTES`, `TABLE_CELL_BYTES` and `RECORD_*`, between
  0.9 and 1.6 times the `tracemalloc` figure in a test) and first come, first served. It is a limit
  on bytes: S is not an authorization to exceed it. When it is exceeded the worst
  rows of the middle are given up one by one (the size in force `middle_k` can only
  shrink, as in B09), then the start stops growing (the first rows that fit stay),
  and the end is projected from the newest row back while it fits. The end is
  charged to the budget when the dataset is finalized, so with several datasets
  the order of their finalization (the order of the datasets) is part of the
  result: a later dataset read while the budget was half spent can leave the
  earlier one only what its own end needs. The document
  says `reason: "memory_budget"` as soon as anything was cut, with `requested`,
  `middle_k`, `bytes` and `max_bytes`. A cut middle still has its `threshold`
  and is the bottom-k of its size; the shrinking depends on the data and their
  order only, so it is the same with 1 or several workers. The largest memory of
  a scan is also bounded by the record in reading and by the CSV batch (13).
- **Output.** `records.sample` (absent when `records.sample.rows` is 0):

  ```json
  {"selection": "start_middle_end",
   "hash": {"algorithm": "blake2b", "version": 1, "bits": 64, "seed": 42},
   "requested": {"rows": 1000, "edge": 50, "middle": 900}, "middle_k": 900,
   "population": {"records": 3000, "interior": 2900, "scope": "interior_rows"},
   "complete": false, "threshold": "4e361452e3b67ee0",
   "fields": ["column_1", "column_2"], "fields_limited": false,
   "cell_chars": 200, "truncated_cells": 0, "bytes": 2477121,
   "max_bytes": 16777216, "kept": 1000, "of": 1000,
   "rows": [{"record": 1, "origins": ["start"],
             "values": {"column_1": ["a"], "column_2": ["1"]}}]}
  ```

  Rows are in source order within each group: the start (with the rows that are
  also the end), the middle, the end. `threshold` (16 hexadecimal digits) is the
  largest priority kept, written once a row of the interior was not kept.
- **Report (O27, 19.4, 18.14).** The Report keeps the header and the rows
  `report.row_sample` asks for (`start`, `middle` and `end`, 10 each by default):
  the first, the last, and the interior rows of smallest priority, an exact
  subset of the Scan's. `kept` and `of` declare it, the facts are otherwise the
  Scan's. `facts_sha256` leaves out `rows` and `kept`; `complete_samples` is
  false for a base that dropped rows. The "Data sample" of the report shows
  them in three labelled parts (18.14); `records.preview` no longer exists.
- **Consumers.** `RowSample.interior()` (the rows an exploration may treat as a
  sample, C04) and `RowSample.covers(field_ids)` (false when a field is not
  projected, or has a cut or hidden cell in a row: C06) are the seams of the
  planner of lot 6a and of the relations of lot 8a. `covers` is false for a sample
  that lists no row or fewer than it sampled, which is what a Report holds. A cell is the text, not the
  native type; lot 8a decides whether the type must be added.
- **Validation.** `check_scan` checks the hash identity (algorithm, version, bits
  and the seed of the configuration), the settings in force, the population, the
  groups and their order, the fields of the cells, the counts and the threshold
  (the largest priority of the middle rows, recomputed).

### 18.12 Pattern discovery (lot 4a, D08, PAT-01 to PAT-06, C07 to C10; rewritten by the Patterns lot P1, PAT-12 to PAT-20, O65)

This section is the contract of the hierarchical discovery. It replaces the flat list of candidates of the lot 4a
(a list of structures with generalization levels and `overlaps`). Its sources are the specification (`DEC-001` to
`DEC-034`, `FR-001` to `FR-024`, `TR-001` to `TR-011`), the algorithm (version 1.1) and the notation; this section states what the code must do and does not depend on reading them. The decision
record is the ADR `2026-10-13-hierarchical-patterns-fixed-lengths`. The lots P2 to P8 of the Patterns plan implement
it; until a lot delivers, the tests of `tests/patterns/` for that lot stay skipped ("to enable"). The lot P3 delivered the
families, the patterns of fixed length, the folded constants, the merge of composition, the budgets and the target
format; the lot P4 delivered the content facets, the score, the tree, the tables of content and the depth
(`scanner/patternfacets.py`, `scanner/patterntree.py`); the lot P6 made the validation read the hierarchy and the lot P7
the other consumers: `check_scan`, the observation `minority_pattern`, the features of a column (`PatternCoder`), the
smart sample, the residual values and the Report. The views of the flat list of the lot 4a are gone; a reader walks the
families (`FieldPatternsComplete.all_patterns()`, `outside_patterns()`).

After the scan, `tabalyst.scanner.patterninfer.infer_patterns(datasets, settings)` discovers the structural patterns
of the fields from their samples. It reads the finished datasets, never the source (PAT-01), and `scan()` calls it once
after `finalize`; the result is `ScanResult.derived.patterns` and its time is `run.timings.derived`. The discovered
patterns are not the configured ones (12.7): those stay detectors (`pattern:<id>`) in `field.detectors`.
`scan.pattern_inference.enabled` set to false leaves `derived` out. The discovery stays in this post-pass and not in a
second-pass analyzer (O65), so a Scan alone, and a Report made from it, show patterns without any second reading.

**Vocabulary.** A *format* is the exact form of one value, a symbol per character (`AA-9999`). A *pattern* describes
values of one structure and one set of lengths, with its constants (`'AK-'9999`); a discovered pattern has a fixed
length for each position and never a range. A *family* gathers the patterns of one structure that differ only by
their lengths or their constants; it is not a pattern, has no rendering as a range and presents itself as the list of
its patterns with their counts. A *facet* is a dimension along which a family can be specialized (composition,
lengths, content). A *node* is a family plus constraints on facets, with its counts. A *table* is the list of the
values of a facet with their counts, not nested in the tree. Every figure is given in two measures: `d`, distinct
values, and `o`, occurrences.

**Order of the work, for one field (PAT-12 to PAT-18).** Eligibility (the field is a candidate or not), population,
families, facets, score, tree, budgets, publication. A field that is not eligible costs only its eligibility.

**Eligibility (PAT-12, FR-001, DEC-004, DEC-022, REC-001).** Every field has an `eligibility` object: `state` (one of
`eligible`, `low_relevance`, `excluded`, `not_assessable`), `score` (a number from 0 to 1, rounded to four decimals)
and `reasons` (a list of codes). It is computed from the statistics and the samples of the Scan, without building a
tree, in two phases: a preselection on the facts (technical type, presence, cardinality, lengths, detectors,
availability of the values) and a light structural check on the sampled values (character classes, shared prefixes
and suffixes, separators, positional constants). Only an `eligible` field is discovered. The rest of the contract:

- The state `excluded` has few causes, each a reason code: no usable value (`no_values`), values that are only
  structures or booleans (`structures_only`, `booleans_only`), exposure (`exposure`, below), only long texts
  (`long_texts_only`). The state
  `not_assessable` says that information is missing, with a reason (`samples_withheld`, `too_few_distinct`), and is
  never a silent exclusion. The state `low_relevance` is a field that can be assessed and that a pattern would
  describe poorly (a free description, a handful of statuses).
- Cardinality is never a cause of exclusion by itself: it is combined with structural regularity (a column of unique
  identifiers is the best candidate). A column of digits typed as integers is admitted (RC-10, RC-11): the technical
  type `integer` no longer excludes, and the discovery reads such a value as its decimal text. A field recognized by
  a semantic detector (a date) lowers its score and is not excluded (AC-002).
- The fixed-length criterion (DEC-034): a field is relevant only if at most `N` formats of fixed length cover at
  least `P` percent of its values; the ISBN with hyphens of RC-12 (more than six combinations of lengths), names and
  free text fail it, `A9A 9A9` and `'AK-'9999` pass it. `N`, `P` and the weights of the score were calibrated at
  the lot P2 on the corpus (OPEN-009, below); the relative order is the contract of AC-001: an identifier scores
  strictly more than a free description and more than a column of five statuses.
- The state and the reasons are published for every field, so a reader can tell "no pattern" from "not looked at".
  A field in a state other than `eligible` has the status `not_applicable` and no `families` (the entry below). Such
  an entry keeps a `reason`, the deciding reason of its eligibility (the first that is not `regular_structure` or
  `integer_digits`), for the readers that want one word.

**Calibration of the eligibility (lot P2, OPEN-009, `scanner/pattern_eligibility.py`).** The first phase reads the
facts, in this order: an exposure that masks or hides (`excluded`, `exposure`), the technical type `boolean`
(`excluded`, `booleans_only`), samples withheld (`not_assessable`, `samples_withheld`). The population is that of the
discovery (below), an integer read as its decimal text; when it is empty the field is `excluded` with
`long_texts_only`, `structures_only` (only objects or arrays) or `no_values`, and with fewer values than
`min_distinct` it is `not_assessable` with `too_few_distinct`. A field that is excluded or not assessable scores 0.
The second phase tokenizes the population once (the inference reuses the tokens) and computes, each in both
measures, the larger kept:

```text
F = share of the values that the N = 6 commonest formats of fixed length cover
    (format = the tokens with their lengths, a literal with its character)
S = share of the values with a structural mark (an ASCII digit or a literal
    character other than a space)
V = min(1, log2(distinct) / 6)                       variety, saturates at 64
score = F * (0.5 * S + 0.5 * V) * D * G             rounded to four decimals
D = 0.75 when a detector interprets the field (interpretations, except number
    and configured patterns), else 1                AC-002
G = 0.25 for each hard criterion failed: F < P = 0.90 (many_fixed_lengths), an
    integer one of whose commonest formats (those that cover P of its values,
    in either measure) has fewer than 4 digits (small_integers), the technical type number
    (decimal_numbers)
eligible when score >= 0.35, else low_relevance
```

A failed hard criterion brings the best score (1) under the threshold, so the state follows the score. The integer
rule looks past the commonest format because a sequence of counts is mostly of its largest length (0 to 2,997 is two
thirds four digits) while a code has no short tail: the cards of RC-11 need 16, 15 and 14 digits. The reasons
list `regular_structure` (F reaches P) or `many_fixed_lengths`, then `integer_digits` (an integer of 4 digits or more,
admitted) or `small_integers` or `decimal_numbers`, `no_structural_marks` (S < 0.5), `few_distinct` (V < 0.5, fewer
than 8 distinct values) and `semantic_detector`. Why these values: RC-07 needs six formats and the hyphenated ISBN of
RC-12 reaches only 0.80 with six (its 11 formats), so `N = 6` and `P = 0.90`; the threshold falls between the
letters-only codes of RC-12 (0.4818, 55 codes) and five statuses (0.1935). Results on the corpus and the contract
columns (`tests/patterns`):

| Columns | State | Score | Reasons |
| --- | --- | --- | --- |
| RC-02, RC-03, RC-05 to RC-09, RC-13, RC-14, RC-16, RC-17 (scaled), identifiers | eligible | 1.0000 | `regular_structure` |
| RC-10, RC-11 (typed `integer`) | eligible | 1.0000 | `regular_structure`, `integer_digits` |
| RC-20 postal codes, ISO dates | eligible | 0.7500 | `regular_structure`, `semantic_detector` |
| toys RC-01 to RC-04, RC-15 (4 to 6 values) | eligible | 0.6667 to 0.7154 | `regular_structure`, `few_distinct` |
| RC-12 codes `AA`, `AAA` | eligible | 0.4818 | `regular_structure`, `no_structural_marks` |
| RC-12 ISBN | low_relevance | 0.2000 | `many_fixed_lengths` |
| five statuses | low_relevance | 0.1935 | `regular_structure`, `no_structural_marks`, `few_distinct` |
| free descriptions | low_relevance | 0.0019 | `many_fixed_lengths`, `no_structural_marks` |
| RC-18, RC-19 (masked) | excluded | 0 | `exposure` |
| one value | not_assessable | 0 | `too_few_distinct` |

These constants belong to the version of the algorithm, like those of the score below. Known limit: a column of
uniform amounts of five digits is structurally a code and is eligible; the numeric profile describes it better.

**Population (PAT-13, FR-002, FR-003, DEC-010, DEC-018).** The stored distinct original values of the field, each with
its count: the `listed` of `values.samples` and the pool of `by_length.listed` (once each, by `id`), in id order, at
most `max_values` (10,000; the setting runs up to 20,000; `limits` says `max_values` when the cut acts). The two
selection laws are not added (LEN-06). The counts are used: every score, order and coverage is computed on the pairs
(value, count), in the two measures `d` and `o`. The counts are exact when the sample is `all` (`population.complete`)
and the basis of the occurrences is `sample` otherwise; a coverage in occurrences is then a discovery indicator and
not a frequency of the file, which only the validation (20.9) gives. Excluded, and counted in `population.excluded`:
the long texts (PAT-05 of the lot 4a, C10), values that are neither strings nor integers (an integer is read as its decimal text), empty values, values longer than
`max_value_length` (64) and values of more than 32 tokens. The discovery never reads the source (TR-001).

**Grammar, version 2 (PAT-03, PAT-04, DEC-032).** A value is cut into tokens as in version 1: a run of ASCII digits, a run of ASCII capitals, a run of
ASCII lowercase letters, a run of letters that has a non-ASCII letter, and every other character, a literal (a run of
the same character is one token with a count). The notation changes (DEC-032): `9` a digit, `A` a capital, `a` a
lowercase letter, `@` a letter of either case (non-ASCII too), `X` a capital or a digit, `x` a lowercase letter or a
digit, `#` an ASCII letter of either case or a digit; `?` (any character) is never produced by the discovery and
belongs to written patterns; literals are quoted (`'AK'`), with `''` for an apostrophe, and a fixed value with the separators or spaces that touch it is one block of text (`'CLI-00'999999`); a separator alone stays as it is (`-9999`), and a single space between two elements is written as it is and ends the block (`'AK' 9999`, `A9A 9A9`), quoted with the text it touches at the start, at the end or repeated; repeats are `{n}`, and only a
written pattern uses `{m,n}` and `{a|b}`. A position that mixes a non-ASCII letter and a digit has no class: the
formats stay apart. The match of a signature is still one pass without backtracking (PAT-04). A change of a class, a
rule or the rendering raises `GRAMMAR_VERSION`, here to 2 (the notation of version 1, where `X` was a capital and `#`
a letter or a digit, no longer exists). The signature, a list of typed tokens, is the reference; the `render` is its
text in the notation above.

**Families (PAT-14, FR-005, FR-009, E2).** The values are grouped by structure (the tokens without their lengths): the
structure key. A family is a group of one key, or of keys merged at the edge of a block, only when all hold: same
skeleton of separators and same block lengths; the classes differ only on a prefix or a suffix of one or two
positions; the stable part of the block is not empty and at least as long as the mixed part; every structure is
material (`d` at least 2, or a share of at least 5% in `d` or `o`). The rule as the lot P3 implements it (the
maintainer accepted it on 2026-10-13): the base structure has a block of one class token `T` (`D`, `U` or `L`), a
merged structure has the same block with a token of another class `Y` of `k` positions (1 or 2) right after `T`
(suffix) or right before it (prefix), and `D` is one of the two classes; all the values of the merged structure add the
same `k`, keep `T` at least `k` characters long and give a total block length that the base structure also has.
Several merged structures (`Y` being `U`, then `L`) join one base at the same edge and width, the edge with most values
wins, and a structure that is a base, or was merged, is never merged into another. The classes of the merged positions
become one: `D` with `U` is `X` (`upper_digit`), `D` with `L` is `x` (`lower_digit`), the three together are `#`.
`DDDDU` and `DDDDD` merge into `DDDDZ` (a position
that is a capital or a digit, `X` in the notation); `UDD` with `UUD` (the mixed position is in the middle) and `AK`
with `ak` (the stable part is empty) do not. The families are disjoint by construction, since a value has one
structure key; the five raw variants of `AK-1234` (RC-15) are five families. They are ranked by the larger of their
shares in `d` and `o`, then by key text; those beyond `max_families` (16) go to `other.structures`. The generalization
ladder of the lot 4a (levels 1 and 2) and `overlaps` disappear.

**Patterns of fixed length (PAT-15, FR-008, DEC-034).** In a family, each combination of the lengths of the variable
tokens that the population shows is one pattern, with no test of gain, within `max_patterns_per_family` (32): `'INV-'999`,
`'INV-'9999` and `'INV-'99999` are three patterns of one family. The lengths are those of every token of the
family's skeleton, a literal run counting too, and a merged block counts as one token as long as the whole block. A
constant carried by all the members of a pattern, in `d` and in `o`, creates no child: it is folded into the
rendering (`'AK-'9999`), while the parent stays general so that a later value is a new variant, not an unknown
structure (DEC-026). What is folded (lot P3): the characters that every member has at the start of a class token, the
whole token when it is all constant (`'202'9`, `'INV'`), never the end of a token (a tail is a facet) and never
a position of several classes; at most three characters (`MAX_FOLD`) of a token that varies, so that a pattern of a
few numbers never publishes the start of one (RC-11), and a token that every member repeats entirely whatever its
length; a pattern of one distinct value folds nothing, a lone value proving no constant. A
pattern that holds several of the merged structures has the union class at the merged positions (`'A'A-9999X`) and a
node of the facet `composition` for each structure (`'A'A-99999`, `'A'A-9999A`), with no test of gain. A family whose
patterns would need more combinations than the budget keeps the largest and counts the rest in the `lengths` table of
the family (one cell per combination of class lengths, `others` for the rest), with `limits`.

**Facets and score (PAT-16, FR-006, FR-007, FR-010, DEC-023, DEC-029 to DEC-031).** A family can be specialized by,
in this order: its composition (the merged structures become nodes without a test of gain); its lengths (above); its
content, which is a chain of heads (1 to 3 first characters of a token), of tails (1 to 3 last characters) and the
whole token. A token that is almost unique (distinct contents at least 50% of `d`) is ignored, and no specialization
may fix every free position of the family. For a value `v` of a facet in a node of weight `X` (in `d` or in `o`),
reading `k` positions with `b` bits a position (letter 4.70, digit 3.32, alphanumeric 5.17):

```text
gain(v) = x_v * (k*b + log2(x_v / X)) - (k*b + kappa)      the whole prefix, DEC-029
b_f     = k*b of the longest prefix kept                   positions read, DEC-030
sigma   = sum of gain(v) over the leaves / (X * b_f)
```

A head of `k` characters is a candidate only if the characters that follow its parent differ from chance (a G test
against the uniform law on the alphabet of the class, `p < 10^-6`, on the measure tested) and the parent has at least
4 distinct values (DEC-031). A branch is kept if it is a candidate and `gain_d(v) > 0`, or if `gain_o(v) > 0` and no
single value carries more than 90% of the occurrences of the branch. A character shared by all the members of a head is
folded into it and counts in its `k` positions. A facet is published if `max(sigma_d, sigma_o)` is at least 0.10. The
starting values are `kappa = 2`, `alpha = 10^-6`, 0.10, 90%, 95% and 4; they belong to the version of the algorithm
(below), not to the settings, and a change of one raises it.

*How the lot P4 reads it* (`patternfacets.py`; `tests/patterns/pattern_bits.py` is its independent calculator and
`test_pattern_facets.py` compares them on the corpus). A facet reads one token of the skeleton of the family (the
merged block is the composition, never a content facet; a literal reads nothing). A token has up to three readings:
its heads, its tails and its whole value, and the one that saves most bits (`max(gain_d, gain_o)`) is its facet, the
head winning a tie, if it is published. A tail is read only on a token longer than the chain of three characters:
a shorter one is read in full by its heads, and reading it from the other end would find chance in the last letter of a
code (RC-12). The whole value is read for a token of at most four characters (`MAX_WHOLE_TOKEN`: the year of RC-05;
a longer token is an identifier, and no complete number is published) whose distinct contents are fewer than half of
the distinct values (an almost unique token is ignored, E3); heads and tails of such a token are still read (the end
`00` of the numbers of RC-16). A value of a whole token is kept when it is beyond chance among all the tokens of that
length: the G test over every possible token has too few expected counts when four digits make 10,000 symbols, so
the value is tested alone with the Chernoff bound of the binomial tail, multiplied by the number of possible values
(`beyond_chance`, same `alpha`). Heads and tails keep the G test of DEC-031. A token whose members are all equal reads
nothing, and a pattern of fewer than four distinct values is not developed.

**Tree and compressions (PAT-17, FR-005, FR-012, DEC-024, DEC-025).** The tree is built best first. Level 1 under the
family is the composition or the lengths (the patterns); level 2 is content, the facet of the largest absolute gain
being the primary one; level 3 is a content facet that depends on the primary one. The default depth below the family
is 3 and the ceiling 4 (`max_depth`). A node receives only facets that read positions disjoint from those of its
ancestors. Another facet is nested under a node only if it depends on it, measured against the marginal table of the
family (`log2(p_node(v) / p_family(v))`, normalized by the marginal entropy); otherwise it stays a table of the family.
A node of one child that covers at least 95% of itself merges with that child, and an intermediate whose kept children
cover at least 95% of its `d` and of its `o` is removed and its children move up. The rest of a facet (`others`) is
never developed. A node has fewer than 4 distinct values: it is not developed. Each value counts for one node, the
deepest, so a node's counts equal the sum of its children and the rest, and the patterns of a family sum to the family.

*How the lot P4 builds it* (`patterntree.py`). The tree is built for each pattern, over its own members: lengths are
the first level, so RC-07 sets `CC` and `CD` apart in the pattern of lengths 2 and 4 only. The facet of each token is
chosen as above. When the pattern holds several merged structures, the composition nodes are the primary ones and a
content facet is nested under a structure only if it depends on it. Otherwise the primary facet is the published one
with the largest `max(gain_d, gain_o)`, the lowest position on a tie, and its prefixes are the nodes at level 2 (the
longer prefixes the facet kept, `0` then `00`, are their children). Below a leaf, another published facet is nested
when its dependence on the leaf (`dependence`: the divergence of its table in the leaf from its table in the pattern,
over the entropy of the latter, the larger on `d` and `o`) is at least `NU_MIN`; the facet that saves most bits
inside the leaf is read there again (same reading, head, tail or whole value), and the positions read by the
ancestors are not read again. A published facet that no node reads is a table of the family: its cells are its
leaves and `others` the rest, so cells and rest add up to the family. A family of one pattern that holds all of it
reuses the facets read for the pattern; otherwise the facets of the positions no node reads are read over the whole
family. A node whose only child covers 95% of its `d` and of its `o` merges with that child (not a composition node,
which is a partition of its pattern). Nodes are built one level beyond `max_depth` and then cut, with the limit named,
so that a cut is told from a tree that simply ends; with a `max_depth` of 1 a pattern has no node, composition
included.

The signature of a node is that of its pattern (or of its structure, below a composition node) with what the node and
its ancestors fix: a head as a literal followed by the class of the rest, a tail as the class of the characters between
the folded start and the tail followed by the literal (`9{4}'00'`), a whole token as a literal. The start that the
pattern folded is kept, and a node folds nothing more, so that a constant is not read by chance in a small node.

**Budgets and limits (PAT-18, FR-011, DEC-006).** The settings of `scan.pattern_inference` are `enabled`,
`max_values` (10,000, at most 20,000), `max_families` (16), `max_patterns_per_family` (32), `max_patterns` (128: the
patterns and the nodes published for a field, which changes the meaning of the setting of the lot 4a, whose default
was 8 and whose upper bound of 64 rises to 1,024), `max_depth` (3, at most 4: the levels of the tree under a family, the pattern being the first), `max_value_length` (64) and `min_distinct`
(2, a condition of the eligibility of the field: a structure with one value is a family of its own). When a budget
acts, the branches of the lowest gain are folded into the `others` of their parent and `limits` names the budget
(`max_values`, `max_families`, `max_patterns_per_family`, `max_patterns`, `max_depth`). The families beyond
`max_families` are counted in `other` (`structures`, `d`, `o`). Under `max_patterns` the nodes of content of the lowest
gain go first (with the nodes below them), then the nodes of the smallest patterns (a pattern keeps all its composition
nodes or none), then the smallest patterns, each family keeping its largest, into the `lengths` table of their family.
A table of content with more cells than `max_patterns_per_family` keeps the largest, the rest going to `others`, with
that limit. `max_depth` is named in `limits` when a node deeper than the setting was left out; in the Report its setting
is `scan.pattern_inference.max_depth` (`report_labels.MEASURE_REASON_SETTINGS`), since the limit of the JSON structure
shares the name. The names and defaults are the ones the maintainer accepted on 2026-10-13; the values are not
final and a change of any setting makes the Scan stale like any other (21).

**Determinism (FR-018, AC-019).** Same values, counts and settings give the same result, byte for byte, whatever the
number of workers. Every score is rounded to nine decimals before it is compared; ties are broken by the text of the
key or of the signature, then by the first id.

**Exposure (PAT-19, PAT-20, FR-022, DEC-027).** A field whose exposure masks or hides it is `excluded` with the
reason `exposure`: the generic discovery is off, and no node, table, constant or example of such a field is published.
The one exception is the *declared keys*, below. A new block of the discovery goes through the same gate as the
samples, and a field the exposure does not mask but that no detector names is discovered (there is no card or
social-insurance detector, so those columns are read; no complete number is published, constants having at most
three characters). A test makes sure of both.

**Declared keys (PAT-19, DEC-027, DEC-028; lot P5).** The detectors `email`, `phone` and `postal_code` declare keys
that have an established meaning, counted exactly on the whole file during the first pass (the accumulators of the
detectors, like `NameCounts` for the domains): the extension and the domain of an e-mail (read from the right, so
`co.uk` emerges without a list of public suffixes), the region (`nanp`, `fr`) and the area code or zone of a
telephone number, the first letter or digit and the FSA or the ZIP3 of a postal code. For one level: sort the values
by decreasing share, then by text; keep one while its share reaches the floor of the level (0.5% at level 1, 2% of the
parent at level 2), it has at least 5 occurrences, its rank is in the budget (32 at level 1, 16 by parent) and the
cumulated coverage has not reached 95%; the rest is `others` (number of keys, occurrences). The levels nest. No test
against chance applies, the detector having established the meaning. These aggregates are exposed even on a masked
field, with a floor of 5 occurrences that is also a privacy floor; examples, the profile and the rows of the sample
stay masked. The setting `exposure.detector_keys` (`aggregate`, the default, or `mask`) brings the masking back: the
block is then `disabled` (`reason` `exposure`) on a masked or hidden field and unchanged elsewhere.

*How the lot P5 does it* (`scanner/detectors/keys.py`, `ExposureGate.exposes_keys`). The block is `details.keys` of the
detector's entry in the field: `{status, levels, keys: [{key, occurrences, keys?, others?}], others: {keys,
occurrences}}`, `levels` naming the meaning of each level (detectors.md, "Declared keys"). The accumulator of the
detector counts occurrences, so the result is the same with one or several workers and in both execution modes: the
extension of an e-mail in a `NameCounts` of its own (exact when the domains tracked overflow, otherwise `limited`
without a listing), the domains in the existing one, whose suffixes of up to four labels give the levels below; the
area code or zone of a phone number and the area of a postal code in small dictionaries that need no limit. The
floors are integer comparisons (`count * 200 >= total`, `count * 50 >= parent`), and the keys of a level and its
`others` add up to the level, which `check_scan` verifies (`_check_keys`: first level and `others` equal the
`matched` values of the detector, keys below a key and its `others` equal the key, order and floor of 5
occurrences). Overflow of `max_tracked_domains` makes the block `limited`: the counts of the keys listed stay exact,
the number of keys left out is a lower bound. The `domains` block of an e-mail field is untouched and stays masked
(it lists up to 20 domains with no floor). The detectors `email`, `phone` and `postal_code` move to version 2, so a
stored Scan made before is scanned again. The Report does not draw the keys yet.

**Failure.** The discovery of each field is isolated, as a detector is (CA19): an exception on one field gives it a
`failed` entry (`reason` `inference_error`, `diagnostic` the index of a `pattern_inference_failed` error naming the
dataset and the field, with the exception type and never its message). The other fields, the other analyses and the
scan `status` are unaffected.

**Output (target format, grammar 2; PAT-13 to PAT-18).** `derived.patterns` is `{grammar: {name: "tabalyst.pattern",
version: 2}, algorithm: {version}, domain: "original", fields: [...]}`, one entry per field in the order of the
datasets and fields, each with `dataset`, `field`, `status` (`complete`, `not_applicable` or `failed`) and
`eligibility`. A `complete` entry also has:

- `population`: `source`, `selection`, `complete`, `available`, `distinct`, `occurrences`, `occurrences_basis`
  (`exact` or `sample`), `excluded`;
- `families`: each with `id` (`f1`, ...), `key`, `d`, `o`, optional `composition` (the merged keys), `patterns`
  (each with `id` `f1.p1`, `signature`, `render`, `format` of the commonest value, `lengths`, `d`, `o`, `examples`,
  `nodes`), `tables` (each with `facet`: `lengths`, or `head:N`, `tail:N`, `token:N` for the Nth token of the key
  counted from 1, `cells` of `{value, d, o}` (the text of a prefix, spelled from the left), `others` `{distinct, d, o}`
  and, for a table of content, `gain` `{bits_d, bits_o, sigma}`; the cells and `others` of a table of content add up to
  the family, a table of `lengths` completes the patterns to the family), and `examples` (up to three ids of entries of
  the samples, the smallest);
- a node: `id` (`f1.p1.n1`, then `f1.p1.n1.n1` below it), `parent`, `level` (2 under a pattern), `facet`
  (`composition`, `head:N`, `tail:N` or `token:N`), `value` (the text it fixes at its facet, spelled from the left; the
  text of the structure for a node of composition), `also` (when a node whose only child covers 95% of it merged into
  this one, what that node fixed: `{facet, value}` pairs, omitted when empty; the validation reads a node by `value` and
  checks `also`), `signature`, `render`, `d`, `o`, `role` (`principal` for the first
  of its siblings, the largest, `secondary`), `gain` (`bits_d`, `bits_o`, `sigma`, for a node of content only) and
  `nodes` (omitted when empty). The nodes of composition add up to their pattern; those of content are a strict part
  of their parent;
- `other`: the structures and values read by no family (`structures`, `d`, `o`); the model has no flat list;
- `limits`: the budgets that acted.

Percentages are not stored (they are computed from `d` and `o`). `coverage.basis` of the lot 4a is now `occurrences_basis`
and `population.complete`. `merged_structures`, `generalization`, `confidence` and `overlaps` are gone and the
candidates are not kept: no compatibility with the flat list is promised (beta). An example, indicative:

```json
{
  "dataset": "orders", "field": "code", "status": "complete",
  "eligibility": {"state": "eligible", "score": 0.91, "reasons": ["regular_structure"]},
  "population": {"source": "samples", "selection": "all", "complete": true,
                 "available": 500, "distinct": 500, "occurrences": 500,
                 "occurrences_basis": "exact", "excluded": {}},
  "families": [{
    "id": "f1", "key": "UP-D", "d": 500, "o": 500,
    "patterns": [{
      "id": "f1.p1", "render": "AA-9999", "d": 500, "o": 500,
      "signature": [{"kind": "upper_ascii", "min": 2, "max": 2},
                    {"kind": "literal", "text": "-", "min": 1, "max": 1},
                    {"kind": "digit_ascii", "min": 4, "max": 4}],
      "nodes": [
        {"id": "f1.p1.n1", "parent": "f1.p1", "level": 2, "facet": "head:1",
         "render": "'AK-'9999", "d": 50, "o": 50}
      ]
    }],
    "tables": [], "examples": [12, 40, 41]
  }],
  "other": {"structures": 0, "d": 0, "o": 0},
  "limits": []
}
```

The revision of the Scan format is 4 for the whole Patterns plan (3 today), and that of the second-pass document
moves once (20.9); the changelogs are kept in the lot that changes the format (P3 for the discovery). `derived` is part
of the base model (a Scan with it reads back) and not of its facts: `facts_sha256` leaves it out, a Report carries it
as it is (19.3) because its base keeps fewer values and cannot compute it, and `check_scan` checks it (PAT-22 of the
tests, below): one entry per field, the eligibility of every entry, the render of each signature, and the sums:
the patterns of a family add up to the family, the children of a node to the node and its rest, the tables to their
family, the families and `other` to the population.

**Algorithm version and cache (FR-020).** `derived.patterns.algorithm.version` is the version of the discovery
(scores, constants, order of the steps); a change of the algorithm or of a constant of it raises it, as a change of
the notation raises the grammar. The Scan carries the settings it used, so a changed setting makes it stale and the
discovery is rebuilt, and the validation that depends on it with it (20.9). The identity of a Scan (19.5, `ScanIdentity`)
holds the grammar and algorithm versions of its `derived.patterns` (`None` when the discovery is off) next to the source,
the configuration and the engine, so a stored Scan found by another version is stale and scanned again
(`current_scan`, `stored_scan`); a Report of a scan document the user chose only gets a warning that names the two
versions (`engine_warning`). The versions are read through `patterninfer.discovery_versions()`. Rendering the Report again
never reruns either (lot P7, AC-021).

**Consistency of the hierarchy (lot P7, PAT-27, `check_scan`).** On top of the sums, the ids and the parents above, a node
fixes a text that the validation reads it by: `value` is not empty (for a node of composition it is one of the keys of
the family) and `also` lists distinct facets of the form `head:N`, `tail:N` or `token:N` with their text; two siblings
never fix the same facet, text and `also`. When the Scan holds the samples the discovery read (it is not the reduced base
of a Report), the signatures describe them: of the distinct values of a family, the pattern accepts exactly its `d`,
and a node accepts exactly its `d` among the values of its parent. This is the check of the examples over every
node (ASCII values go through a compiled expression). It tokenizes the population again: on `synthetic-1m.csv` (five fields, 20,000
samples each) `check_scan` takes 0.35 s instead of 0.06 s, about 60 ms a field.

**The Report (lot P8, FR-021, OPEN-013, TR-016).** The Report reads the hierarchy from the document alone and never recomputes it
(AC-021). `report_sections.pattern_view` builds `PatternView.families` (`PatternFamilyView` > `PatternPatternView` >
`PatternNodeView`, and `PatternTableView`): every count has its shares of `d` and `o` of the population, computed at render time,
and, when the second pass ran, the occurrences and distinct values of `pattern_counts` joined by id (`validated`, `validated_exact`),
the new variants of each family and the cells of its tables. The page of a column (`templates/patterns.html`, macro `family_tree`) shows each
family as a `<details>` block, its patterns, the nodes as nested lists (a node with children is folded below level 2) and the tables,
all readable without JavaScript. The gain of a node (`bits_d`, `bits_o`) is a secondary line, and a table's `others` row completes the
family. The table of the dataset stays flat, one row per pattern with its family. Nothing of the JSON changes.

**Tests of the contract.** `tests/patterns/` holds the reference corpus RC-01 to RC-20 and the expected trees, each
test marked with the lot that provides its behavior (`P3`, `P4`, `P5`, `P6`) and skipped until the lot enables it in
`conftest.py`. The tests without a mark check the corpus and the hand calculations and always run.

### 18.13 Observations, quality issues and limits (lot 4b, D18, QUAL-01 to QUAL-05, O34)

After the scan and its derived patterns, `tabalyst.scanner.quality.build_observations`
turns the facts into findings. It reads the finished datasets, the scope, the
source and `derived.patterns`; it never reads the source and writes no value,
only counts and references (fields, records, diagnostics, patterns). The result
is `ScanResult.observations`, built by `scan()` and counted in
`run.timings.derived`; `scan.observations.enabled` set to false leaves it out.
The block is part of the base model, so a Scan with it reads back, a Report
carries it as it is (its base keeps fewer values and cannot compute it) and
`facts_sha256` leaves it out. Its version (`observations.version`, 1) names the
rules and their constants: a change of a rule, a threshold or a status raises it (2 since lot 13: `minority_length`).

**Three concepts (QUAL-01).** An *observation* is a finding about the data. A
*quality issue* is an observation that may be a defect: a `candidate_anomaly` or
a `confirmed_issue`. A *limit* is what the scan could not establish; it is never
a defect of the data (QUAL-04) and is listed apart.

**Observation (QUAL-02).** `{id, rule, category, status, dataset?, field?,
population, count, of?, accuracy, records?, patterns?, diagnostics?,
limited_by?}`. `id` is `o1`, `o2`, ... in the order of the listing. `rule`
names the rule, whose `category` and `status` are fixed by the version of the
rules. `population` says what `count` counts out of `of`: `value_slots`
(occurrences plus absent members, 9.11), `content_strings`, `occurrences`
(values of the field), `records`, `distinct_values`, `groups` or `columns`.
`accuracy` is `exact`, `lower_bound` (a count that a limit stops from being
exact; `limited_by` lists the limits) or `sample` (a count over sampled
distinct values). `records` lists the first record indices (at most
`limits.max_listed_records`), `diagnostics` the indices of the diagnostics that
explain it and `patterns` the patterns of the hierarchy it is about (ids such as `f1.p2`). Members
that carry nothing are absent.

**Rules, version 1.** A field rule applies to each field; a dataset rule to each
dataset; `excluded_records` to the whole scan (`dataset` absent).

| Rule | Status | Category | `count` of `of` |
| --- | --- | --- | --- |
| `excluded_records` | `confirmed_issue` | `records` | records excluded of records read; `records`, `diagnostics` from the exclusion diagnostics |
| `ambiguous_header` | `confirmed_issue` | `names` | columns that share a blank or repeated header name (tabular sources) |
| `duplicate_rows` | `candidate_anomaly` | `records` | `records.duplicates.count` of the records; `lower_bound` when that count is limited |
| `mixed_types` | `candidate_anomaly` | `types` | values outside the closest technical type of a `mixed` field, of its values |
| `type_outliers` | `candidate_anomaly` | `types` | `technical_type.outside_count` of the values, for a field that is not `text` or `mixed` |
| `ambiguous_dates` | `candidate_anomaly` | `dates` | ambiguous date values of the date values (ambiguous ones included) |
| `variant_groups` | `candidate_anomaly` | `normalization` | groups of raw spellings that normalization compares as equal (complete only) |
| `minority_pattern` | `candidate_anomaly` | `patterns` | distinct values of the minority candidates of the distinct values read |
| `minority_length` | `candidate_anomaly` | `patterns` | content strings outside the dominant length, of the content strings counted by the length histogram (exact) |
| `missing_values` | `informational` | `presence` | `missing.count` of the value slots (not for an empty column) |
| `empty_column` | `informational` | `presence` | all the value slots, for a field of technical type `empty` |
| `constant_column` | `informational` | `values` | values of a field of at least two values with one exact analytical distinct value |
| `trimmed_cells` | `informational` | `normalization` | `changed` of the `trim` stage of the content strings |
| `collapsed_whitespace` | `informational` | `normalization` | `changed` of the `collapse_whitespace` stage of the content strings |

A `minority_length` is a field of at least 20 content strings (`MINORITY_LENGTH_MIN_VALUES`) where
one length holds at least 95 % of them (`DOMINANT_LENGTH_MIN_SHARE`) and the others at most 5 %
together (`MINORITY_LENGTH_MAX_SHARE`): the malformed `CLI-12` that the pattern `'CLI'-9{2,7}`
absorbed. It reads the exact histogram, so it is always `exact`, and a field with no dominant
length raises nothing. There is no row test for it yet: the smart sample reports it as
`needs_length_test`.

A column that is 85 % empty is a remark and not an issue (QUAL-03): absence
becomes an issue only through an explicit presence rule, which the Scan does not
have yet; the statuses above are the ones the facts alone can justify. A
`minority_pattern` is a field whose principal pattern covers at least 80 % of
the distinct values read (`PRINCIPAL_MIN_SHARE`) and that has secondary
patterns covering at most 5 % each (`MINORITY_MAX_SHARE`); the patterns are those of the
hierarchy, of every family, the largest in distinct values first (lot P7); it counts those
patterns, is `exact` when the inference read every distinct value
(`population.complete`) and `sample` otherwise, and names the limits
of the inference (`max_patterns`, `max_values`) in `limited_by`. It is a
heuristic over distinct values, not over occurrences, and says "worth a look",
never "an error". Counts that a limit made unsafe are never invented: a
`constant_column` needs an exact distinct count and a limited one gives none; a
limited `variant_groups` gives none. There is no `severity` in version 1:
priority is the status, and weights belong to the smart sampling (lot 10a).

**Listing.** The items are sorted by status (confirmed issues, candidate
anomalies, remarks), then by generation order (datasets, then fields, in the
order of the document), numbered after the sort and cut to
`scan.observations.max_items` (1,000; 100,000 at most). The limits are cut to
the same number. `truncated` says that a list is shorter than its count; the
summaries count before the cut, and a `limited_by` may then name a limit that is
not listed (its identifier is still the one of the full numbering).

**Summaries (QUAL-01).** `observations.summary` (the whole scan, no `dataset`)
and `observations.datasets` (one per dataset, in order) hold `informational`,
`candidate_anomalies`, `confirmed_issues` and `limits`, and the flags derived
from them: `has_observations` (any observation), `has_quality_issues` (a
candidate anomaly or a confirmed issue) and `has_limits`. A scan-wide
observation counts in `summary` only. The flags are per scan and per dataset; a
consumer that needs them per field reads the items (`field`).

**Limits (QUAL-04).** `{id, dataset?, field?, measure, reason, limit?,
lower_bound?, diagnostic?}`, `id` is `l1`, ... in generation order. `measure` is
the location in the dataset or field. Sources: every `limited` envelope of the
structure, the records and the field (a normalization stage that repeats the
count of its input, and the `raw` stage that repeats `values.cardinality`, are
not listed again); the sample reduced by the memory budget
(`values.samples`, `.long_texts`, `.by_length`, `records.sample`, reason
`memory_budget`); the strata of lengths that hit `max_length_strata`; a sample
that exposure withheld (`exposure`); `records.sample.fields` and
`structure.depth_truncated_observations` (`max_fields`, `max_depth`); and the
pattern inference of a field: `max_patterns` and `max_values` when they acted,
`inference_error` with the index of its diagnostic when it failed.

**Failure.** The build is isolated like the pattern inference (CA19): an
exception leaves `observations` out, raises an `observations_failed` error
(the exception type only, never the message) and the scan is complete. A
document without the block and without that diagnostic, while the setting is
on, is invalid.

**Validation.** `check_scan` verifies the version; one summary per dataset in
order; the flags against the counts; that the listing is cut exactly when its
count says so; ids; the status order; the rule, category and status of each
item; its dataset and field; `count` between 1 and `of`; the references
(diagnostics, limits, patterns); the summaries against the items when nothing
was cut; and the counts that one fact gives again (`excluded_records`,
`duplicate_rows`, `missing_values`, `trimmed_cells`, `collapsed_whitespace`).
It also verifies the `equals` rule of the normalization stages (section 10).

Not in this lot: cross-column features (REL-01), which belong to the
relationships (lots 8a and 8b). The Report reads the observations since lot 5
(18.14): its `issues`, `with_issues` and `limits` are gone.

### 18.14 The report reads the findings (lot 5, D19, HTML-01 to HTML-09, F01 to F06)

The HTML report is rendered from the document alone (HTML-01, F01): the Scan base
the Report holds, its `report` block and nothing else. No page recomputes a rule
and none reads the source. Three modules own the reading:

- `report_labels`: the words. The Scan carries codes; the labels of the
  13 observation rules, the statuses, the accuracy kinds, the limits and the
  reasons a field has no pattern are here and nowhere else.
- `report_sections`: the builders of the views of one dataset or one column,
  computed when a page is rendered and never stored: `QualityView` (the
  observations of the dataset and of the whole scan, grouped by rule),
  `LimitsView`, `PatternView`, `RowsView` and `CardinalityView`.
- `report_views`: the view models (`ColumnView`, `DatasetView` and the others).

**What the projections no longer hold.** `report.datasets[].issues`, `preview`,
`limits`, `columns[].with_issues` and `summary.with_issues_column_count` are
removed (revision 2 of the Report is not published). The observations of the
base replace them: a column is *with issues* when an observation about its
`field` has the status `candidate_anomaly` or `confirmed_issue` (QUAL-01), and a
remark such as missing values is not an issue (QUAL-03). The limits of a
dataset are `observations.limits`; its untracked and depth-truncated counts are
read from the base `structure`; its diagnostics are those of the root, with the
display path of their field. A document without `observations` (the setting is
off or the build failed) shows "Not computed" where the findings would be and
rebuilds nothing.

**Accuracy vocabulary (HTML-03, HTML-04).** Five kinds, each a word and a
shape in front of the word, never a color alone (HTML-09):

| Kind | Word | Means |
| --- | --- | --- |
| `exact` | exact | counted on every value of the file |
| `estimated` | estimated | a KMV estimate from the sample, shown with its relative error |
| `sample` | sample | counted on a sample of the distinct values, not on the file |
| `at_least` | at least | a limit stopped the count: a proven lower bound, written `≥ n` |
| `not_computed` | not computed | the scan did not compute it |

The kind of an observation is its `accuracy` (`exact`, `lower_bound`, `sample`).
A candidate rule is a status (`Candidate anomaly`), not an accuracy. A group of
observations is as sure as its least sure item. "Validated on the whole file"
does not exist yet: a pattern share is `exact` when the inference read every
distinct value (`coverage.basis` `all_distinct`) and `sample` otherwise, and
the page says "Not validated against the whole file" (lot 7c adds the other).

**Distinct values of a column (`cardinality_view`).** The count follows the last
enabled analytical stage. A stage that changed nothing (`equals`, section 10) is
the identity on the distinct values, so the raw count and its estimate still
hold; a stage that changed something has its own count, which has no estimate.
The view is `exact` (a number), `at_least` (the lower bound, and the estimate
with its error when the scan made one) or `not_counted` (a limit that proved
nothing). The tables write `≥ 51` and, below it, `≈ 2,031 est.`.

**Observations section.** One table of the listed items with status, rule,
column, `count` and `of` with the noun the population gives (`value_slots` are
"values", `distinct_values` "distinct values"), accuracy and the references
(records, patterns, limits, diagnostics). The overview groups the items by rule:
the number is the sum of the counts, or the number of columns for the rules that
are about a column (`empty_column`, `constant_column`), with `≥` when any item
is a lower bound. A link goes to the section that shows the finding in detail,
or to Observations when that section is absent.

**Patterns section.** One row per candidate and one for the values no candidate
takes, with the share of the distinct values read and its basis. Examples are
the ids of the field's samples: a Report keeps the smallest priorities of the
sample (19.4), so an example the Scan listed may not be among them; the page
shows those that resolve and says how many do not (HTML-08: no invention). A
field with no pattern says why (`PATTERN_REASONS`); a failed one is "not
computed". Shares count distinct values, never occurrences of the file.

**Row sample.** The first records, the interior rows and the last records of
`records.sample`, each row with its logical record number and its part (`Start`,
`Sampled`, `End`), so the edges are recognized and the middle is not mistaken for
a uniform draw (HTML-05, ROW-07). `records.preview` is gone: the start of the
row sample is the same cells, and `scan.records.preview` is refused with the
place of its replacements (`scan.records.sample.edge`, `report.row_sample`).
The Report keeps `report.row_sample` rows: `start` (the first), `end` (the
last) and `middle` (the interior rows of smallest priority, which are the rows
a bottom-k of that size would have kept: an exact subset of the Scan's, 19.4),
10 each by default, 1,000 at most and never more than the Scan kept. `kept` and
`of` declare it. `check_scan` accepts a reduced sample: the `threshold` and
`truncated_cells` of the Scan are bounds of what the Report lists.

**Display budgets (HTML-07, F04).** The document holds every row, finding and
pattern it kept; a page prints at most `DISPLAY_LIMITS` of each (300 rows, 500
findings and limits, 400 pattern rows) and says "Showing the first n of m". A table
that can be long (`data-page-size`) starts with its first 25 rows and has a "Show
more" button; filters and sorting still see every printed row. So the page cost
does not grow with `report.value_examples.kept_per_column` or `report.row_sample`.

**Large counters (Q6, F06).** The JSON holds Python integers, written with all
their digits (the schema stays typed). The page never turns one into a float:
`format_number` writes an integer exactly, `NumericStats` keeps `int | float`,
and the sort keys are the text the report wrote. In the browser, an integer of
more than 15 digits is compared as a `BigInt` by the sort and the numeric filters
(`numCmp` in `report.js`). A float is already an approximation: it is shown
rounded. A reader of `report.json` in JavaScript must parse integers beyond
2^53 without loss: `JSON.parse` rounds them (documented in `json-profile.md`).

**Escaping and keyboard (HTML-08, HTML-09).** Every value, column name, pattern
literal and cell goes through Jinja autoescape, including the `data-*`
attributes; the page has no other script than its own. A cell cut by the scan
carries "… cut", a hidden cell "hidden", an absent one "absent". Every control
is a native button, link or input; the tables keep their `tabindex` and
`aria-sort`; the charts of the report carry a text alternative and their figures
are in the tables.

**Setting sentences.** The "Analysis settings" section states the real size of
the samples the document keeps (the largest `values.samples.kept` of the dataset,
not `kept_per_column`), the row sample the scan and the report kept, and whether
the patterns and the observations were computed.

Not in this lot: the validated coverage (lot 7c), the relationships (HTML-06, lot 8b),
the analyses and the plan (lots 6a to 7c).

**Relationships section (lot 8b, HTML-06).** The section sits between Patterns and
Second pass (the later sections are renumbered 12 to 15) and is shown when the second pass
computed a table or a correlation. `report_relations.py` builds its views from the
`analyses` of the document (`RelationsView`, one `RelationGroup` per pair of columns with
the leading feature first, `RelationTable`, `CorrelationRow`) and the page prints the counts
and the percentage of each category in every cell before the scores, the exceptions without
requiring anyone to know Cramér's V or Pearson, and the candidate rules, labelled learned and
not validated. A score on low counts is `unstable` and gets no strength word; a table without
a score says why. What the planner explored on the sample, and found nothing in, is a note.
The Second pass section keeps a row for each analysis.

### 18.15 Cases of the observed rules (lot K1, CASE-01 to CASE-15, O68)

Status: **Accepted** by the maintainer on 2026-10-18. Step 1, the Scan, is built (`scanner/cases.py`,
`tests/scan/test_cases.py`); the Report reads the cases in step 2.

**Problem.** The Report explains a finding with examples (R12, `summary-table.md` 22). It reads
them from `values.samples`, a bottom-k of the distinct values by hash (18.9). A field of D distinct
values above K keeps a given value with probability K / D: with K = 10,000 and D = 100,000, the
two cells that carry a trailing space are in the sample one time out of ten, and the finding
prints "no example". Nothing in the Scan can be blamed: the observation is exact (the counters
saw both cells), only the cases are lost. The strata of 18.7 do not solve it: they exist for a
`bottom_k` sample only, they class the original text by its original length while the findings
speak of the analytical text, and they hold 100 values for each of 64 lengths whether or not a
rule needs them. The smart sample (20.15, 20.16) finds rows by rule but reads the source again
and is a user decision; the cases are wanted in the first pass, without a second reading.

**Decision.** While it reads the values, the Scan keeps a small bounded sample of the original
texts of each case of the rules it can later observe, with the exact number of cells of the case
and the exact count of each text kept. A reader that wants the cells of a rare case reads them
here, whatever the size of the field. This extends `values.samples` with a member `cases`; it
creates no observation and changes none (CASE-01).

**What is a case.** A case is a class of cells defined by a fact the first pass already
computes, never by a new rule:

| Group | Class | Defined by | Rule it explains |
| --- | --- | --- | --- |
| `whitespace` | `leading` | the `trim` stage changed the text and the text does not start as its left-stripped form | `trimmed_cells` |
| `whitespace` | `trailing` | the `trim` stage changed the text and the text does not end as its right-stripped form | `trimmed_cells` |
| `whitespace` | `repeated` | the `collapse_whitespace` stage changed the text (a run of whitespace other than a line break read as one space, as `Normalizer.run` does) | `collapsed_whitespace` |
| `lengths` | a length | the analytical length of the text, the one of `string_lengths.length_histogram` (after `nfc`, `trim` and `collapse_whitespace`) | `minority_length` |

A text with a leading and a trailing space is a case of both classes; a class counts its own
cells. Both groups are classes of content strings. A disabled stage creates no class
(CA16). Minority patterns need nothing (CASE-13) and dates and the other rules are not in K1
(`types`: CASE-14).

**Member.** `values.samples.cases`, present when at least one class has a cell and absent
otherwise (a field with nothing to explain keeps the document it has today):

```
cases: {
  per_class_k, requested_per_class_k?, reason?,
  whitespace?: [{kind, occurrences, selection, kept, of, threshold?, listed}],
  lengths?: {max_lengths, other?: {lengths, occurrences},
             classes: [{length, occurrences, selection, kept, of, threshold?, listed}]}
}
```

- `kind` is `leading`, `trailing` or `repeated`, in that order, and only the kinds that have a
  cell are written. `occurrences` is the exact number of cells of the class. `selection` is `all`
  while the class dropped no text (the list is then every distinct text of the case, a
  complete answer), `bottom_k` otherwise, with `threshold` as in 18.9. `kept` is the number of
  texts listed and `of` the number of texts the class sampled (at most `per_class_k`).
- `listed` is a list of `{value, count}` in ascending `(priority, text)`, the priority of the key
  `("string", original text)` through 18.3 with the seed of the Scan, so the choice is the same
  as the global sample would make, reproducible and independent of the order of the values, of
  the batches, of the workers and of `max_distinct_per_field`. `count` is the exact number of
  occurrences of that original text in the whole field: a class sampler admits a text at its
  first occurrence and never loses it (the argument of 18.3), so no count is partial and the
  member has no `count_accuracy`. A case carries its own text: it is not an id into
  `samples.listed`, because the Report base reduces and drops samples (19.4) and an id would
  point at nothing.
- `lengths` is written only when the field has a minority length by the rule of the observation
  (`MINORITY_LENGTH_*` of `quality.py`, applied to the same histogram by one shared function),
  and its `classes` hold every tracked length but the dominant one. A field of free text, with
  forty lengths and no dominant one, writes no `lengths`. Lengths are tracked as met: the
  `max_lengths` (`scan.limits.max_case_lengths`) first lengths in the order of the distinct
  values; the other cells are summed in `other`. A length that has no class
  has no case, and the Report says so.
- A text longer than `max_stored_value_length` is counted in `occurrences` and listed in no
  class (a case is a stored text, 18.6). `occurrences` of `repeated` equals the `changed` count
  of the stage `collapse_whitespace` and `leading` and `trailing` obey
  `max(leading, trailing) <= changed(trim) <= leading + trailing`, so the new counts can
  never disagree with the ones the findings already print (CASE-07).

**Exposure (CASE-08).** After the calculation on originals, like 18.9. `mask` merges the texts
with the same mask, counts added (`kept` below `of`); `hide` lists none; `occurrences`, lengths
and kinds are numbers and stay; the `threshold` of a sensitive field is not written; a document
edited to another exposure leaks nothing because the Report applies its gate again.

**Memory (CASE-09).** The cases have their own share of the budget of 18.10: an eighth of
`limits.max_sample_memory` (`memory.CASE_SHARE`), taken from the share of the samples of values,
which keep five eighths. The first draft said a sixteenth and 112 KB per field; `tracemalloc` showed
that a sampler of five texts costs 5.3 KB, not 3.4 KB, because its two dictionaries and its counters
are a fixed cost that the 600 bytes per entry of 18.10 spread over thousands of entries (measured
in `test_the_memory_of_the_cases_stays_within_the_model`), so the model has a cost per class
(`memory.CASE_CLASS_BYTES`, 2,048 bytes) and the share doubled. A field reserves, once, when its
sample is made, the cost of its largest possible set of classes: `(3 + max_case_lengths) *
(CASE_CLASS_BYTES + per_class_k * sample_entry_bytes(mean_chars))`; the grant is the largest
`per_class_k` that fits the share of the field (`room / fields discovered so far`, as 18.10), never
below 0. A grant under the request writes `requested_per_class_k` with `reason: memory_budget`; a
grant of 0 keeps every `occurrences` (counters cost nothing) and lists no text. With the defaults
(5 and 32) a field reserves 35 * 5,248 bytes, 184 KB, and the share holds about 360 fields at full
size and 700 at one text per class; beyond that the fields keep their counts and no text. The
warning `sample_budget` does not count a field whose cases alone were cut. The numbers are a
model, checked against `tracemalloc` like the others.

**Settings.** `scan.limits.max_cases_per_class` (5, hard cap 100, 0 turns the cases off) and
`scan.limits.max_case_lengths` (32, hard cap 256, 0 turns the lengths off). Both are in the
configuration hash of the Scan (`config_sha256`): a document without cases and one with them are
two different scans. Five per class is two more than the three the Report shows for each kind,
so a `mask` that merges a few texts still leaves three.

**Cost (CASE-10).**

- Complete table (at most T distinct values, `all` or `bottom_k` sample made at the end): the
  cases are read from the table at the end, only for a rule that fired (`changed` of a stage above
  0, a minority length), so a clean field pays one test. The only hashing is that of the
  texts of the classes written.
- Released table (more than T distinct values): the class samplers are fed by the same batches
  as the sample and the strata, with the priorities computed once per batch and shared by the
  three. A text that cannot enter its class costs one lookup and one comparison against the
  admission limit (`BottomKSampler.admission_limit`), as in 18.7. Only the cells of a class
  are offered to it: whitespace is rare, but the rule of the minority length is only known at the
  end, so a released field offers every cell to the class of its length while it reads.
- Refusal rule, as 18.8: lot K1 is refused if the first pass of the realistic dataset regresses by
  more than 3 % against the baseline of the same session or the worst-width dataset by more than
  5 %, with the cases on (defaults) against `max_cases_per_class = 0`. Measured in
  `tabalyst-lab/benchmarks` (`cases.py`), recorded in `benchmarks.md` with a file that has rare
  whitespace in a column of 200,000 distinct values and one that has a minority length.
  A regression above the threshold goes back to the maintainer, who may accept the lengths and
  refuse nothing else, or the reverse.
  Measured (`tabalyst-lab/docs/benchmarks/scan.md`): in the default parallel mode +0.6 % on the realistic
  file, +0.9 % on the worst-width file; with one process +4.4 % on the realistic file (+2.1 % wide,
  +1.9 % rare), after the priorities of a batch were hashed once for the sample, the strata and the cases
  (a first version hashed them again: +7 %, +12 %, +21 %). The one-process figure is above the 3 % line and
  waits for the maintainer's decision.

**Validation and schema (CASE-11).** `check_scan` (`validation.py`) verifies, for every field
whose exposure is `show`: `kept <= of <= per_class_k`, `kept` equals the length of `listed`;
each text is listed once; its priority is in ascending order and equals the one the seed gives;
the text belongs to its class when the Normalizer of the configuration is run on it (a `leading`
text starts as its left-stripped form does not, an analytical length is the class length);
the sum of the counts is at most `occurrences`, and equals it when the class is `all`, the field
has no long text and nothing was masked; the identities of CASE-07 hold against the stages of
`normalization`; the classes of `lengths` are distinct ascending lengths, never the dominant one, with
`occurrences` at most the cells of that length in the histogram, and with `other` they
add up to at most the cells of the other lengths. `scripts/scan_schema.py` regenerates
`tabalyst.scan.schema.json` and the test that compares it fails when it is out of date.

**Format (CASE-12).** The member is new and optional: revision 4 of the Scan, still in
preparation, gains it in place, with a line in `docs/en/scan/format-changelog.md` and in
`docs/en/scan/format.md`. `facts_sha256` leaves `listed` of `cases` out like the one of
`samples` (19.5) and keeps `occurrences`. A Report base keeps the counters of `cases` and
empties the lists (19.4): the details of the Findings already carry the examples the page prints.
No migration (19.6).

**What the Report reads (CASE-13).** After the Scan lot, `report_finding_details.py` reads the
`whitespace` and `lengths` details from `cases` in place of the sample: `examples_from` gains the
value `cases`; the examples of a class are its first texts in the order above, with their
exact count; a class marked `all` is said to be complete, one marked `bottom_k` to be a
sample of its texts. The Normalizer detour of 22.14 stays only to show the analytical text of a
length case (the class holds the original). The note "a rare case is often missing" of the
whitespace and the lengths hovers and 22.15 and 22.17 are removed. Counts, shapes and the
order of 22.3 do not change. Patterns need nothing: the examples of a minority pattern are
values of the population the inference read, which are in the sample the Report receives
(22.13), and a pattern too rare to be inferred is not an observation. Dates have no example.
Attached to a document without `cases` (a Scan of an older revision is refused anyway), the
details keep saying `none`.

**Mixed types (CASE-14, lot K2, after K1).** The technical family of a string is known only after
the detectors ran (`registry.add_string_measures`), and a text column offers every value to the
`text` class. K2 measures the cost of a class per family (`types`, outside the dominant family)
on top of K1 and is built only if the cost stays under the thresholds above. Until then the
`types` detail keeps printing no example.

**Tests (CASE-15).** `tests/scan/test_cases.py`: the classes of a hand-built field, one case per
class with exact counts; a field of 200,000 distinct values with two cells with a trailing space
lists both, with count; reproducibility (batch sizes, `workers` 1 and 4, `max_distinct_per_field`
50 against the default give the same member byte for byte); the `all` selection; the lengths
tracked, `other`, and the absence of `lengths` without a minority; the parity of CASE-07 on
`insurance-customers`; `mask` (merged, counts added) and `hide`; the memory grant (field wide
source, `requested_per_class_k`) against `tracemalloc`; a stage disabled; long texts; JSON and
Excel sources; the schema and `check_scan` refusing a hand-edited case (wrong class, wrong
priority). The Report tests of 22.9 gain the case where the sample lacks the text and the cases
hold it.

**Order of work.** K1 in three steps, each validated: (1) the Scan (models, collectors, budget,
settings, validation, schema, changelog, benchmark); (2) the Report reads the cases (after R12 is
committed: the builder it changes is in the branch `report-overview/l0`); (3) K2 if the cost
allows. Follow-up for `tabalyst-studio`: the Scan format page and the Findings capture.

## 19. Scan and Report as one document family (O27, O29, O30)

### 19.1 Identity

`tabalyst.scan` is the base document. `tabalyst.report` is a superset: the
base at the same paths (`engine`, `status`, `run`, `source`, `config`,
`config_sha256`, `scope`, `datasets`, `diagnostics`), plus a `report` block
and, later, `analyses` (second-pass results). The Report profile of
revision 1 had no `format` field; the document of revision 2 identifies itself
with `format: "tabalyst.report"` and has its own `format_revision` (2), with a
reference to the revision of its base in `report.base_scan` (19.5). The root
holds the base at its own paths, so `format` and `format_revision` are the only
members of the root whose value is the Report's and not the base's.

### 19.2 Common loader

`tabalyst.scan_document.load_document(path_or_dict) -> LoadedDocument` reads a
Scan or a Report (lot 1b) and returns its `kind`, the `base` (a `ScanResult`),
the `report` block of a Report and the `capabilities` (`complete_samples`);
`load_base()` returns the base alone. The `report` block and the namespaces
`analyses` are not part of the base; `derived` and `observations` are (19.3). The
loader checks `format_version` and the revision like `scan_reuse` (a document
of another revision is refused with a request to run again, never converted;
for a Report, its own revision and that of its `base_scan`), and that the base
matches the identity the Report declares (`source_sha256`, `config_sha256`,
`facts_sha256`). `require_complete_samples(purpose)` is what a planner calls:
it refuses a document whose samples are not complete (19.4). Extracting the base
of a Report gives the same model and the same facts as the Scan it was built
from, without rounding, filtering or renaming, except the reduced samples
(A02, A11). A Report is not an input of `tabalyst report --scan`: that command
reads scan documents only and says so.

### 19.3 The `report` block

It holds the generation date (`generated_at`), the generator (`name`,
`version`), `processing_seconds`, the presentation configuration (`report.config`:
`string_analysis`, `value_examples` and, since lot 5, `row_sample`; `config` stays
the Scan configuration),
`base_scan` (19.5) and the projections `report.datasets`, one per dataset
shown, identified by the dataset `id`, with columns identified by the field `id`.
No statistic is stored twice: the copies `scan_details`, `numeric`,
`string_profile` and `date_profile` of the columns are removed and the pages
read the base (A04). Since lot 1c the pages read it through the views of
`tabalyst.report_views`, computed when a page is rendered and never stored:
`ColumnView` is the column projection plus its canonical `field` (the Scan
field, read as the Scan wrote it: the column page reads presence, first and last
values, categories, lengths, numeric, boolean and temporal facts from it) and the
three figures the pages derive (`numeric`, `date_profile`, `string_profile`:
percentages, length classes, examples by length). `DatasetView` is the dataset
projection with `ColumnView` columns. The other projections (`summary`,
`structure`, the normalization and detector blocks of a column) are stored. Since
lot 5 the views also hold the findings the pages read from the base
(`report_sections`, 18.14) and the projections no longer hold `issues`,
`preview`, `limits` or `with_issues`.
The Python model is `ReportProfile` (the document): `profile.datasets` are the
scan datasets and `profile.report.datasets` the projections. The `derived` and
`observations` blocks of the Scan are at the root of the Report, carried as they
are: the base of a Report keeps fewer values and cannot compute them again. The
pages read `observations` (18.14).

### 19.4 Reduced samples (O27)

A Report keeps fewer sample values than its base: by default the 100 smallest
priorities of each field (`value_examples.kept_per_column`, 19.4b), an exact and deterministic subset of the Scan's, with
the same exact counters. It declares `kept` and `of` in each `values.samples` (a Scan has them equal:
`of` is the size of the sample the Scan listed, `kept` the number listed here,
`selection` still the Scan's). Lot 1b keeps what the Report already used
(`report_sample`: up to `kept_per_column` values, 100 by default; since lot 2b
the first ones of a `bottom_k` sample, and for an `all` sample the ones of
smallest priority, computed with the scan's hash and seed, so that a Report is
an exact subset of what a bottom-k of that size would keep); lot 1c made it the
setting of 19.4b. The capabilities of the loader say whether the
samples are complete (`kept == of` everywhere); a planner refuses a document
whose samples are not, so a Report is never an input to replan. The invariants
of `check_scan` apply to a reduced base: `kept` is the length of the listing and
at most `of`, `of` at most `max_samples`, and the sum of the counts of an `all`
sample equals `values.count` only when nothing was dropped. The
computation (planner, second pass, patterns) reads the Scan, in memory or from
the cache. A Report can be sent alone and rendered without the source (A10).

### 19.4b Settings by tool

One configuration file serves every command (section 15): the `scan` object
holds what Scan measures and keeps, the `report` object holds what Report
presents, and the top-level `csv` settings serve `tabalyst sample`.
Names are never reused across the two, so a number is read for one tool only:

| Setting | Where | Tool | Meaning | Default |
| --- | --- | --- | --- | --- |
| `scan.limits.max_distinct_per_field` (T) | `scan` | Scan, and Report through the scan it runs | Distinct values kept in the exact table | 100,000 |
| `scan.limits.max_samples` (K) | `scan` | Scan | Size of the bottom-k sample kept in the Scan document | 10,000 |
| `report.value_examples.kept_per_column` | `report` | Report | Sample values kept per column in the Report document: the smallest priorities of the K of the base, so an exact subset (19.4); at most K, and a Report built from a Scan with a smaller K keeps all of it and declares `kept` and `of` | 100 |
| `report.value_examples.*_result_size`, `inline_display_size`, `full_distribution_max_distinct` | `report` | Report | What the HTML shows and how examples are chosen | unchanged |
| `report.row_sample.start`, `middle`, `end` | `report` | Report | Rows of the Scan row sample the Report keeps in its base and shows: the first, the interior rows of smallest priority, the last (at most what the Scan kept; 0 to 1,000 each) | 10, 10, 10 |

`report.value_examples.kept_per_column` (1 to 1,000) replaces the role that `max_samples` had for
the Report (the candidate pool of its examples, `candidate_sample_size` before
`max_samples`): 100 is the former default of `max_samples`, so the examples of a
Report do not move when K becomes 10,000. It is presentation: changing it never
invalidates a Scan document or starts a scan (A14), whereas a change of
`scan.limits.*` changes `config_sha256`. The Report document records the Scan
configuration in `config` and the presentation in `report.config` (19.3), which
has the shape of the `report` object of the file. The upper bound of 1,000 is
the cost of the Report: choosing diverse examples compares the candidates
pairwise: measured at lot 1c on the 34 columns and 3,000 rows of the insurance
demo, a report from a scan takes 1.2 s at 100, 3.3 s at 300 and 28 s at 1,000. Other presentation settings of
the old top level (`string_analysis`, `value_examples`) are refused with their
new place, like the settings that moved to `scan`. The Python `ReportConfig`
stays flat (presentation settings then `scan`): only the file has a `report`
object. `docs/en/reference/configuration.md` has the table of these settings by
tool.

### 19.5 Identity of the base

`report.base_scan` identifies the base a Report stands on: `format`,
`format_version` and `format_revision` of the Scan base, `engine_version`,
`source_sha256`, `config_sha256` (the existing scan identity) and
`facts_sha256`, the SHA-256 of the canonical JSON of the base without `run` and
without `listed` and `kept` of each sample, so a change of presentation or of
sample size does not change it. A Report and the Scan it comes from have the
same `facts_sha256` (`scan_document.facts_sha256`). The Scan2 document (lot 7a)
will carry the same block at its root.

### 19.6 Format revisions (O30)

The revision in progress is not published (release 0.6.2 published revision 1
of the Scan and of the Report; the Scan is at revision 2 and the Report at
revision 2 since lot 1b, which changed the structure of the Report). The work changes it in place; each
lot updates `docs/en/scan/format-changelog.md` and the Report changelog; the
revision increases once, when the release is made. No adapter reads older
documents.

### 19.7 Schema and validation of the base (lot 1a)

The JSON Schema of the base document is generated from the result models
(`tabalyst.scanner.schema.scan_schema()`) and committed as
`src/tabalyst/schemas/tabalyst.scan.schema.json`; a test fails when the file is
out of date (`python scripts/scan_schema.py` rewrites it). It describes what a
reader accepts (validation mode: models that omit unknown members cannot be
described in serialization mode), requires the constants of the format, pins
the revision and declares the namespaces `analyses`
and `report` of the extensions with an open schema, so that `additionalProperties:
false` does not stop a reader of the base from recognizing a Report; the schema
of the Report validates their content. Lot 1b adds it:
`tabalyst.report_schema.report_schema()`, committed as
`src/tabalyst/schemas/tabalyst.report.schema.json` and guarded like the other
(`python scripts/scan_schema.py` writes both). It requires the `report` block
and keeps `analyses` open. The base of a Report,
with the `format` and `format_revision` of its `base_scan`, satisfies the Scan
schema; the Report schema fixes the Report's own `format_revision` (2).

`tabalyst.scanner.validation.check_scan(result)` returns the violated
invariants between fields, which a schema cannot express: presence and native
types adding up, string categories, `values.count`, missing components, bounds
and records of the cardinality, listings against `values.count` and
`max_samples`, histogram and numeric sums, detector coverage, scope and source
shape against the datasets, and `config_sha256` against `config`. A scan the
engine produced has none. The private project storage (`projects/`) runs it
when it validates a generation and consumes the Scan base only, never a Report
(lot 1d).

## 20. Second pass and the rule of costly operations (O31)

### 20.1 Commands

| Command | Behavior |
| --- | --- |
| `tabalyst scan` | First pass only. Never automatic. |
| `tabalyst scan --deep` | Forces the second pass (lot 7a). With a valid Scan in the cache (source, configuration, engine), one pass; otherwise the first pass, then the second if the planner keeps analyses: at most two passes. It plans as if forced, with the analyzers that have an executor, asks first when 20.3 says so (`--yes` skips the question) and writes `<stem>.deep.json` (`deep.json` beside the shared `scan.json`; beside the Scan written with `--output` or `--output-dir`). It names the second pass before it starts and what it did when it ends. |
| `tabalyst scan --plan` | Shows the plan without running it (20.5): from the current stored scan, or after the first pass; never the second pass. It also shows the estimated time and whether a run would ask for a confirmation. |
| `tabalyst scan --plan --deep` | Plans the second pass as if forced (20.2): every applicable analysis the hard memory budget holds, on merit, including the analyses that have no executor yet, which it says cannot run in this version. |
| `tabalyst report` | The planner decides whether a second pass has a benefit and a low cost, and what it holds (lot 7c, 20.11). It names what it added or left out, and why, in its progress, its result and the `analyses` of its JSON. It never asks: an automatic choice does not go beyond a limit of 20.2. |
| `tabalyst report --deep` | Forces the second pass, as `scan --deep` does: it asks first when 20.3 says so (`--yes` skips the question, exit code 3 outside a terminal without it), once for the batch. |
| `tabalyst report --scan` | Reads no source: what the Scan and the stored `<stem>.deep.json` answer is in the report, the rest is `skipped` with its reason. With `--deep` it reads the source beside the document, and fails when it is not there. |

The Python API never prompts (O37): `tabalyst.run_second_pass(scan, source,
plan, previous=)` runs a plan and returns the document, `prepare_deep` scans or
reuses the Scans and plans the second pass of a batch with its confirmation,
`execute_deep(preparation, confirmed=)` runs it and raises
`ConfirmationRequired` when a confirmation is needed and was not given, and
`generate_deep` does both. The line "`tabalyst.scan(..., deep=True)`" of the
first drafts is not kept: `scan` returns the `ScanResult` of the first pass and
its signature and speed are not touched by the second.

`deep.mode` (`auto`, `off`, `force`) is a configuration setting for scripts
and CI, with no command-line option to skip the second pass (lot 7c). It only
tells `tabalyst report` what to do: `auto` lets the planner decide, `off` never
plans a second pass (the report says it is disabled), `force` is `--deep`. It
is not part of the settings a second-pass document records, so changing it never
makes a stored result stale, and `tabalyst scan --deep` is an explicit request
that runs whatever the mode. The section `deep` of a configuration file holds
`mode`, `bins` and `bin_strategy` (20.7) and is validated with the other
top-level settings.

The Report side of the API never prompts either: `generate_reports(deep=,
confirmed=, confirm=)` and `analyze(deep=, confirmed=)` raise
`ConfirmationRequired` when a forced pass needs a confirmation and none was
given (`confirm` is a callback asked once with the total of the batch).

### 20.2 Deterministic budgets and the cost model

Automatic selection uses deterministic quantities: memory in bytes, cells to
process and CPU class, never measured time, so the same file gives the same plan
on any machine. Estimated time only feeds messages and one threshold (20.3).
The constants live in `scanner/planner/costmodel.py`; changing one changes
`COST_MODEL_VERSION`, which the plan carries.

| Limit | Automatic choice | Request or forced plan |
| --- | --- | --- |
| Memory, firm bound of the states plus the reading | 128 MiB (`automatic_memory_bytes`) | 512 MiB hard budget (`memory_bytes`), never lifted (MEM-06) |
| Cells of the common reading | 100 million (`max_cells`) | no limit |
| CPU class of an analysis and of the reading | `moderate` at most (`automatic_max_cpu`) | no limit |
| Utility | 45 at least (`AUTOMATIC_MIN_UTILITY`) | none: it only orders the candidates |

Why these values. 128 MiB keeps a Report that adds a second pass well under the
peak of its first pass (715 MB with workers, 177 MB for the main process, on the
1 M x 34 baseline). 512 MiB is the budget of the samples
(`limits.max_sample_memory`). 100 million cells is about 12 s of reading and
under a minute of work at the rates of the baseline (34 million cells read in
4.0 s and analyzed in 20.6 s in one process), a low cost. The number of columns
enters through the cells. The pair analyses (lot 8a, COST-05) and the tables of lot 8b (20.13) have their own
bounds, set by the `deep.pearson` settings and described in 20.12: the columns
explored (50), the pairs times rows compared by the exploration (1 million), the
pairs listed (20) and the pairs chosen by the planner itself (8).

**Memory (COST-01, specification 11.3).** Sizes are payloads, measured with
`tracemalloc` (`tabalyst-lab/benchmarks/planner_costs.py`) and checked by
`tests/scan/test_planner_costs.py`:

| Structure | Model | Measured |
| --- | --- | --- |
| Text in a set | 41 bytes + characters + a slot of 27 (minimum), 37 (expected) or 80 bytes (maximum, with the old and the new table of a growing set), plus 27 bytes for each of the first 50,000 entries in the firm bound (a small set grows to four times its fill: up to 107 bytes of table an entry right after a growth) | 82 to 91 bytes for 8 characters, 139 to 147 for 64, peak up to 104 for 12 |
| Integer in a set | 32 bytes + the same slots | 66 to 74 bytes, peak 88 |
| Entry of a table of counts | 90 bytes + the key | 98 to 101 for a key of 10 characters |
| Key of the table of frequencies (`FREQUENCY_KEY_BYTES`) | 56 bytes more than the text: the tuple of the native type and the analytical text | |
| Empty containers of an exact set (`EXACT_SET_FIXED_BYTES`) | 4,096 bytes: three sets and up to 18 sets of digits of one length, 216 bytes each | |
| Compiled matcher | 5,120 bytes | 2.2 to 4.4 KB |
| Dense counter | 8 bytes a slot | 8 |
| Reading the source once (`PARSER_RESERVE_BYTES`) | 24 MiB | 7 to 8 MB, 19 MB for texts of up to 8,000 characters |
| Cells remembered by the second pass for a field (`REPLAY_MEMO_ENTRIES` x `REPLAY_ENTRY_BYTES`) | 1,024 strings at 250 bytes | under 1 MB a field, 2 MB for 22 text fields (lot 7a) |
| Exact edge of a bin and its float (`EDGE_BYTES`) | 280 bytes | fractions of two integers |

The exact set of lot 7b is measured on its own (`planner_costs.py exact`, one million
distinct identifiers): 61.5 to 65.5 bytes an entry for strings of 8 to 12 digits (a set of
integers per length), 82.6 to 86.6 for 8 to 12 characters of letters and digits, peak 71 and
87; the bytes the executor charges to its pool are within 7% of the bytes held (65.6, 82.6
and 86.6). A field of one million 12-character identifiers is charged 133 MB of firm bound
(87 MB measured at rest, 70 for digits), and a run of four such fields on the 1 M x 34
baseline held a peak of 202 MB of traced memory for a firm bound of 417 MB.

**CPU (COST-02 to COST-04).** The reading (parsing) is a common cost, counted
once and classed by its cells: `very_low` up to 1 million cells, `low` up to 10
million, `moderate` up to 100 million, `high` above. Each analysis adds
nanoseconds to every cell it reads (`NS_PER_CELL`); its class follows from them.
Since lot 7a the limits are `very_low` up to 100 ns, `low` up to 600,
`moderate` up to 2,400 and `high` above: the first pass spends about 600 ns on a
cell of the baseline (20.6 s for 34 million cells), so `low` is an analysis that
costs no more than that and `moderate` one that costs up to four times as much.
The earlier limits (50, 200, 800) were set on proxies of values already parsed;
the executor showed that counting a cell after the work that the first pass does
on it costs several hundred nanoseconds.

The five analyses the executor runs are costed with its measures
(`tabalyst-lab/benchmarks/planner_costs.py executor`, 1 million rows, rounded up): a counter
of integers 900 ns (841), a bin of a decimal 1,800 ns (1,661), a length 250
ns (207), a key of an exact set 400 ns (373, 317 on another file) and an entry of the
table of frequencies 120 ns (108). They include the normalization and the number detector, which the
executor runs once per distinct string of a batch, as the first pass does, and
which a length does not need for its number. Lot 7c replaces the last two proxies
with measures of the executor too (`planner_costs.py executor --max-samples`, 1
million rows, a machine 30% slower than at lot 7a, rounded up and not scaled
down): a pattern validation costs about 800 ns a cell for its field and 100 more
for each other candidate, since a value is tried against every candidate to count
the overlaps (`NS_PER_CELL["matcher_base"]` and `["matcher"]`: one candidate
900 ns, eight 1,600 ns, always `moderate`), and a period counter 800 ns a cell
(670 measured: it pays the date detector once for each distinct string of the file,
since it remembers up to 16,384 strings a column, `PERIOD_MEMO_ENTRIES`; with the
memory of 1,024 strings of the other analyses it read the same dates again in every
batch, 1,700 to 2,900 ns). Lot P6 replaces the validation of the lot 7c: a value is read once in its family, so the cost is `NS_PER_CELL["pattern_family"]` (1,300) and `["pattern_facet"]` (150) for each facet the family reads, whatever the number of patterns and nodes (AC-027, `benchmarks.md`); `COST_MODEL_VERSION` is 15 (the lot P7 reads the patterns of `residual_values` with the same reader: its three tiers are the old ones by 1.5, 20.20). `COST_MODEL_VERSION` was 4 then (7 since lot 14, whose extraction has three tiers, 20.19, and 8 since lot 15, whose residual tables and search for repeated values are measured by tier, 20.20 and 20.21). Both measures include the
reading of the cell. The proxies they replace (35 and 98 ns) did not and were
far too low.

**Time (COST-03).** `estimate_time(plan, scan)` gives a range, outside the plan:
the reading costs what the first pass spent reading (`run.timings.reading`, which
also hashed and built records) at most and 60% of it at least for a CSV (parsing
alone measured 47%, plus the digest that guards the source); the analyses add the
modeled nanoseconds of the selected cells, scaled by how fast the first pass read
compared with the reference machine (8.5 million cells a second, held between a
quarter and four times) and taken between half and twice. It is a guide:
compression, disk cache and the width of the records change it. The plan holds no
time, so `plan_id` does not move from one machine to another.

### 20.3 Confirmation

Forcing an operation whose estimate passes the thresholds asks before starting;
a batch asks once, with the total. Outside an interactive terminal nothing is
asked: the command stops with exit code 3 and a message unless `--yes` is given.
`--force` keeps its meaning (overwrite an output). The API returns the plan with
`requires_confirmation` and the estimate, and executes only with an explicit
parameter.

A confirmation is required when:

- the selection exceeds an automatic limit of 20.2, whoever asked for it: a
  request, or a forced plan. The plan lists the codes in
  `summary.beyond_automatic` (`memory_over_automatic`, `cells_over_automatic`,
  `cpu_over_automatic`), deterministic like the rest of it; what the planner
  picks by itself never has one;
- or the upper bound of the estimated time reaches 120 seconds
  (`DEFAULT_CONFIRM_SECONDS`, "several minutes"), code `time_over_threshold`. This
  part depends on the machine and is therefore not in the plan.

`plan_second_pass(scan, ..., forced=)` returns a `SecondPassPlan`: the plan, the
`estimate` and the `confirmation` (`required`, `reasons`, `memory_max_bytes`),
with `requires_confirmation`. `generate_plans` gives the same per source and
`combine_confirmations` one for a batch: the times add up, since the files are
read one after the other, the memory is the largest of them, and a batch whose
files are each under the threshold can be over it together. The command side is
`cli/confirm.py` (`confirm_second_pass`): proceed without a word when nothing
needs confirming or with `--yes`; in a terminal (input and error output) show the
estimate and ask, the default answer being no; elsewhere refuse with
`EXIT_CONFIRMATION_REQUIRED` (3). Since lot 7a the gate is wired: `tabalyst
scan --deep` plans, asks once for the whole batch (`prepare_deep` combines the
confirmations) and runs; `--yes` skips the question. Exit code 3 means that a
confirmation was needed and not given, whether it could not be asked (not a
terminal, no `--yes`) or the answer was no: nothing was started, and the
Scans made for the planning stay. `scan --plan --deep` shows what a run would
ask. The confirmation is computed on the analyses the executor can run, so it
never asks about a set that would not be built.

### 20.4 Second-pass document (lot 7a, D22, CACHE-01 to CACHE-05, O37)

`<stem>.deep.json` is separate and written atomically; the Scan is not
rewritten (A12). It is the format `tabalyst.scan.deep`, version `0.2.0`,
revision 2 (revision 1 until lot 14), with its own JSON Schema (`tabalyst.scan.deep.schema.json`) and its
own revision history. It is placed beside the Scan it stands on:
`deep.json` next to the shared `scan.json`, `<stem>.deep.json` next to
`<stem>.scan.json` (and `<name>.deep.json` next to any other scan file).

| Member | Content |
| --- | --- |
| `format`, `format_version`, `format_revision` | The identity of the format. |
| `status` | `complete` when every analysis is complete, `partial` otherwise. |
| `base` | The identity of the Scan (19.5): format revision, engine version, source and configuration digests, `facts_sha256`. |
| `settings`, `settings_sha256` | The `deep` settings of the run. |
| `plan` | The plan that was run, whole (20.5), with its `plan_id`. |
| `run` | `started_at`, `duration_seconds`, `timings` (`reading`, `analysis`, `other`), `workers` (1, or the processes that held routes, 20.18), `peak_memory_bytes`, `source_read`, `source_verified` (the digest of the reading was compared with the Scan's, 20.6), `records_read`, `cells_read` (the cells handed to the analyses), `executed`, `reused`, `skipped`. It describes the latest run only. |
| `analyses` | One entry per selected analysis, in plan order. |

An entry has the `id` of its candidate, the analyzer and its version, the
dataset, field and `display`, the `method` and `parameters`, the `domain`
(`analytical`: the values after the normalization of section 10), its `key`, a
`status` (`complete`, `limited`, `failed`, `skipped`), a `reason` and a `detail`
(counts and the type of an exception, never a value of the data) and its
`result` (20.7). `skipped` is an analysis selected that has no executor
(`not_available`); `limited` is an analysis that met a limit and says what it
holds (D08): the exact distinct count whose sets cannot be held (20.8). The
histograms never meet one, their states being of fixed size.

**Key (CACHE-02).** The SHA-256 of the identity of the Scan, the analyzer and its
version, the dataset and field, the method with its effective parameters (the
bins and the way their bounds are chosen are among them), and the domain of the
values. Budgets, costs and the order of the analyses are not: a result computed
under another budget is still the result. A change of the `deep` settings that a
method uses changes its key, so only that analysis is computed again.

**Reuse (CACHE-04, A15).** A run keeps the `complete` entries of the stored
document that have the key it would give, computes the others (missing, `failed`
or with another key) and writes the whole. When nothing is left to compute the
source is not read, no digest is checked and the file is not rewritten. A run that
computes something and whose plan selected other analyses than the stored document keeps
the complete results of that document the plan did not select, after its own entries
(lot 7c: an automatic report after `scan --deep` does not throw away what a forced run
paid for); a report that reads no source writes no document. An entry that was `failed` is tried again: a
failure is not proof of anything.

**Invalidation (A09, CACHE-05).** A document of another source, configuration,
engine version or `facts_sha256` has another `base`, so none of its entries has
the key and all are computed again; a document of another format, revision or
shape is ignored as if it were absent. There is no migration. A change of
presentation, of the number of examples shown or of the order of the charts is not
an input of any analysis, so it never causes a second reading (CACHE-03); what the
document lacks for a rendering is a real request for an analysis.

A Report embeds what it needs under `analyses` (lot 7c, 20.11): the document of
the run, whole, and how the second pass was decided.

### 20.5 Analyzers and the plan (lot 6a, D11, PLAN-01 to PLAN-06, O35)

The planner says what is useful and possible to add to a finished Scan; the Scan
says what was observed. It lives in `scanner/planner/` and reads a `ScanResult`
in memory or from the cache, never a Report (19.4: `plan_document` refuses one
whose samples are reduced) and never the source. It runs nothing and writes
nothing. The second pass (lot 7a, 20.7) gives two of them an executor.

```text
scanner/planner/
|-- models.py      AnalysisPlan, Candidate, Costs, Selection, Budgets
|-- facts.py       FieldFacts: the view of a field that analyzers read
|-- analyzer.py    Analyzer, Assessment, entry sizes of sets and tables
|-- costmodel.py   the calibrated sizes, budgets and CPU classes (20.2)
|-- registry.py    AnalyzerRegistry (internal only, O21)
|-- analyzers/     the built-in analyzers
|-- planner.py     plan_analyses(), AnalysisRequest, selection
|-- reasons.py     the codes the plan writes and their sentences
|-- secondpass.py  time estimate, confirmation, plan_second_pass() (20.3)
`-- render.py      plan_text(): the plan as text
```

**Analyzer (PLAN-02).** A class with an `id`, a `version`, its `outputs`,
`available` (false until an executor exists; true for `numeric_histogram` and
`length_distribution` since lot 7a, for `exact_distinct` and
`exact_frequencies` since lot 7b, and for `pattern_validation` and
`temporal_distribution` since lot 7c: every built-in analyzer), `deterministic` and `reusable`, built with the
`deep` settings that parametrize its methods,
and four methods: `relevant(facts)` (does the analyzer concern this kind of
field at all, so a plan has no row for a text field and a histogram),
`assess(facts)` (`applicable`, `satisfied` or `not_applicable`, with reasons, a
method, its parameters and whether it `requires_source`), `estimate` (the
costs) and `utility` (0 to 100 with reasons). An analyzer reads `FieldFacts`
only: a field's type, counts, cardinality, frequencies, sample selection,
numeric, length, temporal and pattern facts, exposure. It never sees a value.

**Built-in analyzers and the rows of the decision tree (11.2).**

| Analyzer | Applies to | Already satisfied when | Not applicable when | Method |
| --- | --- | --- | --- | --- |
| `exact_frequencies` | any field | `frequencies` complete and not truncated (`counts_complete`), or every distinct original value is listed with its exact count in the samples (`counts_in_samples`) | no values, exposure, more than 1,000 distinct values or a released table (`high_cardinality`), a frequency measure that is off or failed (`measure_unavailable`) | `hash_table`: a table keyed by native type and analytical text (lot 7b) |
| `numeric_histogram` | integer, number, and mixed with a numeric measure | constant (`constant_value`: no spread, no division by zero) | no values, exposure, measure not complete, mixed type (`unreliable_type`) | `dense_counts` (an integer field whose minimum and maximum are integers, at most 65,536 integers apart: exact median, mode, quantiles from one state) or `bins` (`deep.bins`, 100 by default, with the `strategy` of `deep.bin_strategy`) |
| `length_distribution` | text, mixed | the length histogram is complete (`lengths_complete`, always today) | no values, exposure | `dense_counts` |
| `exact_distinct` | any field | the cardinality is complete (`distinct_exact`) | no values, exposure (unless `deep.sensitive.enabled`, O61: then a masked or hidden field is counted, parameter `exposure`, utility 40), long texts only, values longer than 64 characters (`not_compactable`) | `compact_set`, key `integer` (digit strings, JSON integers) or `text`: the key the expected values take, the firm bound always charges a text (20.8) |
| `analytical_distinct` | any field (Unique ID lot 7, 20.41) | the Scan has the analytical count (`distinct_exact`) | no values, exposure (unless `deep.sensitive.enabled`), long texts only, values longer than 64 characters (`not_compactable`), no analytical stage changed a value (`stages_unchanged`) | `compact_set`, parameter `key`; utility 50 for an identifier candidate (20.42), else 40 and never automatic |
| `pattern_validation` | fields with an inferred pattern entry | never (the Scan counts distinct values, not occurrences) | failed or absent inference, exposure, no candidate | `family_recognizer` (20.9); reads no source when the inference read every distinct value (`all_distinct`): the occurrences follow from the exact counts of the samples |
| `pearson_correlation` | pairs of numeric columns of one dataset (lot 8a, 20.12) | never | a column that is not numeric, hidden by exposure or repeated inside a record (explicit pairs only; the exploration counts the columns it leaves out) | `pairwise_complete`, parameter `min_pairs` |
| `category_crosstab` | a category column and a column of text, mixed or integer values of one dataset, by feature (lot 8b, 20.13) | never | a category that is not one (no exact frequencies, one value, too many, near unique, an identifier, exposed, repeated), a column without the classes of the feature (no pattern, one length, no listed value), a column that is its own feature | `contingency_table`, parameters `feature`, `max_categories`, `examples`, `rule_purity`, `rule_support` (and `max_classes`, `prefix_length`) |
| `category_stats` | a category column and a numeric column of one dataset (lot 16c, 20.23) | never | a category that is not one (as for `category_crosstab`), a number that is not numeric, hidden, repeated, constant, an identifier or without a complete measure, a column that is its own category | `group_moments`, parameters `max_categories`, `bins`, `strategy` |
| `numeric_shape` | integer, number, and mixed with a numeric measure (lot 17a, 20.24) | constant (`constant_value`) | no values, exposure, measure not complete, mixed type | `value_table`, parameters `max_values`, `bins`; utility 40, never automatic |
| `datetime_parts` | the fields of `temporal_distribution` and a column of times (lot 17b, 20.25) | never | no values, exposure, mixed type, several kinds, no span | `calendar_parts`, parameters `bins`, `as_of`; utility 40, never automatic |
| `position_drift` | any field of a dataset of at least 100 records (lot 19, 20.30) | never | no values, exposure, repeated in a record, records left out by the Scan, a column that misses nothing and has no value to follow | `slices`, parameters `slices`, `values`, `max_listed`; utility 40, never automatic |
| `missing_matrix` | the columns of a dataset that have a value and lack one somewhere, from two to `deep.missing.max_columns` (lot 19, 20.31) | never | more than `max_columns` columns (`too_many_columns`); no candidate for a column that is not a member | `bit_sets`, parameters `columns`, `max_listed`; utility 40, never automatic |
| `array_profile` | a field that holds arrays (lot 18, 20.33) | every array has the same length (`lengths_constant`) | the lengths spread over more than `deep.arrays.max_lengths` (`array_lengths_too_wide`) | `length_counts`, parameter `max_lengths`; utility 40, never automatic |
| `structure_variants` | a field that holds objects and the root of the records `$` of a JSON source (lot 18, 20.33) | never | paths the Scan stopped naming (`untracked_paths`), one object, no key, every key in every object (`uniform_keys`) | `key_sets`, parameters `max_variants`, `max_listed`, `max_keys`; utility 40, never automatic |
| `text_profile` | a field with content strings whose longest value reaches `deep.texts.min_length` or that has long texts (lot 18, 20.34) | never | no values, exposure | `text_counters`; utility 40, never automatic |
| `fingerprint_distinct` | a field with a value above 64 characters or long texts (lot 18, 20.34) | every value is distinct (`distinct_exact`) | no values, exposure | `fingerprints`, parameter `max_listed`; the table is a state of the pool of the exact sets; utility 40, never automatic |
| `sensitive_forms` | a field whose exposure is `mask`, when `deep.sensitive.enabled` (lot 18, O61, 20.35) | never | no values, exposure `hide` (`hidden_exposure`); relevant to no field while the setting is off | `masks`, parameters `min_count`, `max_listed`, `max_tracked`, `classes`; utility 40, never automatic |
| `temporal_distribution` | date, a column of datetimes (the technical type of the Scan is `text` for them: at least 80% of the values are of one datetime kind), mixed with a temporal measure | single date, or granularity `year` and years already counted (`years_counted`) | no values, exposure, mixed type, several kinds, times only | `period_counts` by `day` (span up to 2 years), `month` (60 years) or `year` (20.10) |
| `measure_extraction` | a field where the `currency`, `percentage` or `quantity` detector matched a value (lot 14, 20.19) | never | no values, exposure, the detector that matched the most values matched fewer than half of the values (`low_coverage`) | `value_table`, parameters `detector`, `max_groups`, `max_values`, `bins`; reads no source when every distinct value is in the samples with its exact count |
| `residual_values` | a field whose patterns leave values out or may (found in a sample), or that a replayable detector reads for at least half of its values while finding some `invalid` or `not_matched` (lot 15, 20.20) | never | no values, exposure, nothing left out (`nothing_left_out`) | `residual_table`, parameters `sources`, `max_listed`, `max_tracked`, `max_value_length`, `records`; reads no source when every distinct value is in the samples with its exact count and `records` is 0 |
| `duplicate_rows_count` | the rows of a CSV file with a single dataset and at least one record (Unique ID lot 6, 20.40) | the Scan counted the extra copies exactly (`copies_exact`) | the Scan was set not to count them (`duplicates_disabled`); records left out (`records_left_out`); no candidate for another source | `extra_copies`, parameters `memory_mb`, `disk_mb`, `max_rows`; utility 50 for a dataset with an identifier candidate whose Scan count is limited (20.42), else 40 and never automatic; `copies_proved` when a valid Dedup report proves the copies |
| `duplicates_report` | a field of text, integer or mixed values, at least 90% distinct (50% under a name that suggests an identifier), and the combinations of two columns a request names (lot 15, 20.21) | the cardinality is complete and equal to the values (`all_distinct`) | no values, exposure, long texts only, a combination of a withheld column or one inside the items of an array | `digest_table`, parameters `max_listed`, `max_tracked`, `records` (a combination: the first two); reads no source for a field when every distinct value is in the samples and `records` is 0 |

A mixed type never gets a typed analysis automatically (specification 11.2):
the rejection is explained, not silent (PLAN-01). Exposure `mask` or `hide`
withholds the values: no analysis is proposed for such a field, but the counts of
decision O61 (`exact_distinct` and `sensitive_forms`) when `deep.sensitive.enabled` is set (20.35).

**Whole rows (Unique ID lot 6).** `duplicate_rows_count` is the first analyzer of whole rows (`Analyzer.rows`, `facts.rows_facts`): its one
candidate per CSV source with a single dataset is named `duplicate_rows_count:<dataset>:$` (20.40).

**Candidate and decision.** One candidate per (analyzer, dataset, field) the
analyzer is relevant to, with `id` `analyzer:dataset:field`, its method and
parameters (counts and domains, never values), its `outputs`, `applicability`,
`utility`, `costs` (for an applicable one) and `execution` (`requires_source`,
`available`, `deterministic`, `reusable`). Its `costs` carry the memory, the CPU class and `cell_ns`, the nanoseconds it adds
to each cell. Its `execution` carries `on_limit`, always `limited` (D08): a limit
met while running makes the result `limited` with its reason, and the count of
what was read so far is never published as complete. Its `selection.state` is:

- `selected`: reason `requested` or `automatic`, with a `priority`, the order of
  choice.
- `already_satisfied` (PLAN-03): reason as in the table, and `satisfied_by`, the
  path of the fact in the Scan that answers it. It is never run again.
- `rejected`: reason `not_applicable` (see `applicability.reasons`),
  `not_requested`, `low_utility`, `cpu_class`, `cells_budget` or `budget`. A
  rejection means budget, utility or prerequisite, not that the analysis is
  impossible (PLAN-06). `selection.requested` stays true for a request refused.

**Selection (PLAN-04, PLAN-05).** Requested analyses that fit the memory budget
come first, in candidate order. With `automatic` (the default) the planner then
takes the analyses of CPU class `very_low` or `low` by decreasing utility, then
the others by utility per byte, but only those whose utility reaches 45
(`AUTOMATIC_MIN_UTILITY`), whose CPU class does not exceed
`budgets.automatic_max_cpu` and, when `budgets.max_cells` is set, while the
shared reading stays within it (an analysis that reads no source is not limited
by cells). Ties are broken by candidate order. Utility is a
heuristic, version `utility_version` 1, with its reasons: `exact_distinct`
scores 20, plus 40 for near-unique values (20 from half), 25 for a name that
suggests an identifier, 10 for an integer key; a histogram of an identifier-like
field scores 15; a pattern validation that needs the source scores 40 plus 20
when the shares come from a sample and 10 when values take no candidate; the
others score 50 (60 for a dense histogram). A request is exempt from the utility,
CPU and cell limits and may use the hard memory budget, never go beyond it (20.2).
With `forced` the planner takes, after the requests, every applicable analysis
the hard budget holds, in the same order, with reason `forced`: the automatic
limits and the utility do not apply, and the selection that goes beyond them is
named in `summary.beyond_automatic`.

**Memory (PLAN-04, 11.3).** Each candidate lists its `states`, each a key and
three scenarios (`min`, `expected`, `max`); `max` is a firm bound taken from
the counts of the Scan (an exact distinct set cannot exceed the number of
values read) and is what the budget is charged. A state used by several
candidates (same key) is counted once, at its largest; the dense counters of an
integer domain are shared by the histogram and the reading of the field. The reading
(parsing) is a common cost, `PARSER_RESERVE_BYTES`, counted once and only when a
selected analysis `requires_source` (COST-01). The plan's `summary.memory` is
that total. These are payloads of the structures, not process memory.

**Values.** The sizes, the budgets, the CPU classes and the utility scores are the
calibrated ones of 20.2 (lots 6b and 7b); the utility scores stay heuristic.

**Plan.** `AnalysisPlan` has `planner` and `planner_version`, `utility_version`, `cost_model_version`,
a `plan_id` (the SHA-256 of the rest of the plan), `base` (the identity of the
Scan: format revision, engine version, `source_sha256`, `config_sha256`,
`facts_sha256`), `objective` (automatic or not, forced or not, the requests with the number of
candidates each matched), `budgets`, `common` (the shared reading: whether it is
needed, its cells, its memory and its CPU class), `summary` (counts by decision,
`second_pass_required`, `executable`, memory, `beyond_automatic`) and `candidates`. `executable` is
false while a selected analyzer is not `available`: the plan says what a second
pass would do on merit. `tabalyst scan --deep` plans with `default_registry().runnable()`,
the analyzers that have an executor, so that it asks for and reports only what it can
run; `scan --plan --deep` keeps the whole registry and says how many of the selected
analyses cannot run in this version. A plan holds no
date, no measured time and no value of the data; the same Scan, request, budgets
and `deep` settings give the same plan on any machine, with any number of workers.
The plan is a member of the second-pass document (20.4), which has its schema and its
changelog.

**Entry points.** `plan_analyses(scan, requests=, automatic=, budgets=,
registry=)`, `plan_document(path_or_dict, ...)` (the loader of 19.2 and
`require_complete_samples`), `generate_plans(inputs, ...)` and
`tabalyst scan --plan`. The command reuses the stored scan when it is current
(source, settings, engine) and otherwise runs the first pass and stores it like
`tabalyst scan`; it never runs the second pass, writes nothing beside the source
and refuses `--output`, `--output-dir`, `--force` and `--counters`. The text goes
to standard output, the scan outcome to standard error. The Python API raises
`ConfigurationError` for a request naming an unknown analyzer, dataset or field.

**Pairs (lot 8a).** `pearson_correlation` has no candidate per field: the planner asks it for
the pairs (20.12). Its candidates have a `partner`, an `exploration` and the id
`pearson_correlation:dataset:first+second`; `AnalysisRequest` has a `partner`, and
`Budgets.automatic_pairs` limits the pairs the planner picks by itself (reason
`pairs_budget` for the others). The plan has a `relations` member, absent when no dataset
has two numeric columns.

**Tables (lot 8b).** `category_crosstab` is the second analyzer of pairs: a `PairAnalyzer` (20.13) that
proposes tables of a category against a feature, directed (id with `>`), with `Budgets.automatic_tables`
(reason `tables_budget`), `AnalysisRequest.feature` and the reason `redundant_feature`. The planner asks
every `PairAnalyzer` for its pairs; `relations` has a member for each (`datasets`, `tables`).

**Stratification (lot 9).** The plan can carry advice on stratified sampling, `stratification` (20.14). It is not an analyzer: it has no executor and takes no part in the selection.

**Smart sampling (lot 10a).** The targets and the plan of a smart sample are `SamplingPlan` (20.15). They are not analyzers and take no part in the selection of the analyses.

**Not yet.** The selection of the rows of a smart sample (done at lot 10b, 20.16).

### 20.6 The source before and after a second reading (lot 6b, PASS2-01, PASS2-06, O36)

`source_guard.py` holds the checks that stand between a plan and the source. A
second pass never mixes two versions of the data.

- **The plan belongs to the Scan** (`check_plan_base`, D04): the format revision,
  engine version, source and configuration digests and `facts_sha256` of the plan
  are those of the Scan offered; otherwise `StalePlan` names what differs.
- **The source can be read again** (`SourceGuard.before`, D05): the file is
  there, is a file, opens, and has the recorded size. Otherwise
  `SourceNotReadable` (an `InputError`, exit code 4) says that the Scan and the
  plan are still valid and that the source must be restored or scanned from a
  readable copy; a different size is `StaleSource`. The content is not hashed in
  advance: that would read the file twice.
- **The digest closes the pass** (`SourceGuard.finish`): the executor hashes the
  bytes it reads (the `HashingStream` of the readers) and compares them with the
  Scan at the end. A difference, including a file rewritten during the reading,
  raises `StaleSource`; the results are provisional until then, and a pass that
  fails is discarded, never published beside the Scan.
- **No materialization.** A source is always a file today. Nothing is copied to a
  temporary file, by default or otherwise; a bounded, explicit copy for a source
  that cannot be read twice (PASS2-06) is left to the day such a source exists.

`prepare_second_pass(plan, scan, source)` runs the first two and returns the guard.

D08 (a limit met by an exact distinct count) has two halves. The plan half is in
force: a set whose firm bound does not fit the budget is rejected with `budget`
and never selected, and `execution.on_limit` is `limited`. The executor half, a
`limited` or `failed` result with its reason that never presents the count of a
prefix as exact, is tested since lot 7b with the exact set
(`test_contract_exact_distinct.py`, 20.8). The executor halves of D04
and D05 are tested since lot 7a (`test_contract_second_pass.py`): a source rewritten
with the same size between the planning and the reading raises `StaleSource`, its
results are discarded and no document is written, an existing one staying as it is; a
source that is gone raises `SourceNotReadable` and leaves the Scan, the plan and the
directory as they were. The executor closes the pass with
`guard.finish(summary.sha256, summary.bytes_read)` of the reader, which hashes the
whole file (`HashingStream.drain`).

### 20.7 The executor and the histograms (lot 7a, D09, D10, PASS2-01 to PASS2-05, HIST-01 to HIST-07, O37)

`scanner/secondpass/` runs the selected analyses that have an executor:

```text
scanner/secondpass/
|-- models.py       DeepResult, AnalysisResult and the results (20.4)
|-- document.py     analysis_key, deep_path_for, deep_document, load_deep
|-- executor.py     run_second_pass, pending_candidates
|-- routing.py      FieldRoute, Router: one reading, each field to its analyses
|-- replay.py       CellReader: the first pass's reading of a cell
|-- accumulators.py DenseAccumulator, BinAccumulator, LengthAccumulator
|-- exactset.py     ExactPool, ExactSet: the exact distinct count (20.8)
|-- frequencies.py  FrequencyAccumulator: the exact frequencies (20.8)
|-- boundaries.py   place_edges: where the edges of a histogram go
|-- bins.py         BinEdges, quantiles, ranks
`-- schema.py       the JSON Schema of the document
```

**One reading (PASS2-01 to PASS2-03).** `run_second_pass(scan, source, plan, ...)`
checks that the plan belongs to the Scan and that the source is there with the
recorded size (20.6), opens the reader of the format with the configuration the
Scan recorded (`readers/factory.open_reader`, which the first pass uses too),
hands each record to the fields that an analysis needs and, at the end, compares
the digest of the bytes read with the Scan's. It returns the document or raises;
it writes nothing, and a failure after the reading publishes nothing. A table is
read column by column from the batches, a JSON or Excel record by the path of its
observations. Every record is parsed once; a CSV file is still scanned to its
separators. The results do not depend on the workers of the first pass (tested).
The reading and the routes that need the whole run stay in the process that asked;
since lot 12 the routes of the fields of a CSV file run in worker processes (20.18),
and the cost model still assumes one process, so its estimate is an upper bound.

**Replay (PASS2-02).** `CellReader` decides for a raw string what the first pass
decided: whether it is content (not empty, blank or a null marker of the
configuration), what its analytical text is (NFC, trim and collapsed whitespace,
with the shortcut the first pass takes for printable strings) and, for a numeric
analysis, which number the number detector gives it (`matched`, within its input
limit; an ambiguous value is not a number). A JSON integer or number is a number
of the text the reader kept. A field remembers the cells of its first 1,024 raw
strings across batches, and counts the distinct strings of each batch once.

**Agreement with the Scan.** An analysis ends with a check: the numeric values it
counted, their minimum and maximum, or the content strings, must be those the Scan
counted. A disagreement is a `failed` entry with the reason `scan_mismatch` and the
counts, never a result; so is a field whose values the executor cannot read as the
Scan did (a decimal in a dense integer domain, `non_integral_value`). An analysis
that raises stops receiving values and fails alone with `analysis_error` and the type
of the exception. The other analyses and the digest check go on.

**Dense counters.** An integer field whose minimum and maximum are written as
integers, at most 65,536 apart, gets a counter per integer (`array('q')`). The
result lists the integers that occur with their counts, the distinct count, every
mode (ten at most, `modes_truncated`), the median and the quantiles, all `exact`.

**Bins (HIST-01 to HIST-06).** Any other numeric field gets `bins` bins (100 by
default; 2 to 1,000) between the exact minimum and maximum of the Scan. The edges
are exact fractions. Bin `i` is `[edges[i], edges[i + 1])` and the last bin is closed
on the right, so the maximum has a bin; a range of one value has a single bin and
no division. A number is placed by comparing its float with the floats of the
edges, and with the exact fractions only when the two floats are equal: rounding to
the nearest float is monotonic, so a strictly greater float proves a greater number.
The placement is therefore exact for any magnitude, integers beyond float64
included. When the minimum or the maximum is written as a float64 (the rounding of a
decimal number, which may be on either side of it), the edges are placed on the
neighbouring floats, so that no value is outside; `outside` counts what is, and
anything but zero is a `scan_mismatch`. The counts per bin are exact. The document
writes the edges as numbers (the minimum and maximum as the Scan wrote them); the
classification used the exact ones, so an edge that float64 cannot represent may be
rounded in the file.

**Quantiles.** The quantile of level `q` of `n` values is the linear interpolation
between the values at ranks `floor((n - 1) q)` and `ceil((n - 1) q)`; for the median
of an even count it is the mean of the two central values (HIST-07). The document
gives the levels 5%, 25%, 50% (also `median`), 75% and 95%. With counters they are
`exact`. Read from bins they are `estimated`: each rank is placed at the middle of its
place in its bin (the bin is taken as uniform) and the bounds `lower` and `upper` are
those of the bins that hold the two ranks, tightened by the minimum and maximum when
the Scan wrote them as integers. The true quantile is always within them (tested
against an exhaustive oracle). The estimate never replaces the median of the Scan: a
Scan whose table was released still says `limited` (A07).

**`bin_strategy`.** `linear` (default) is the above. `sample_quantile` places the
inner edges at the quantiles of what the Scan kept of the field, for a very skewed
distribution: the numbers of the row sample (the shape of the occurrences), when it
holds at least twice the number of bins, else those of the bottom-k sample (the
distinct values), else, with the reason `sample_too_small` or
`sample_without_spread`, it falls back to `linear`. The outer bounds are the exact
ones whatever the strategy, and the counts are those of the whole source. Equal
sample values merge their edges, so there may be fewer bins than asked for. The result
names `strategy`, `requested_strategy`, `bounds_source` (`range`, `rows` or
`distinct`) and the `reason` of a fallback.

**Lengths.** `length_distribution` counts the length, in characters, of the analytical
text of every content string, as `string_lengths` does, and gives the same block
(`count`, `min_length`, `max_length`, `mean_length`, `median_length` and the
histogram). It applies when the Scan's histogram is limited or off; the check is the
number of content strings.

**Cost.** Measured on the baseline (`tabalyst-lab/benchmarks/planner_costs.py executor`, 1 million
rows by 34 columns): 841 ns a cell for counters of integers, 1,661 for bins of
decimals, 207 for lengths; the shared reading 3.1 to 3.4 s; the memory held at the
peak 8.3 to 9.4 MB with 90,909 or 1,000,000 rows, so it does not grow with the number
of records (PERF-05). Forced on the baseline file, the run takes 7.6 s for four
analyses (estimated 4 to 11 s). The costs of the other analyzers stay proxies (20.2).

### 20.8 The exact set and the exact frequencies (lot 7b, D06 to D08, EXACT-01 to EXACT-07, O38)

**The original domain (EXACT-01, EXACT-03).** The distinct count of the Scan is taken
over the original values (section 21): the raw string of a cell, for the values that
are content (not empty, blank or a null marker), and `(native type, value)` for the
other types of JSON. `exact_distinct` repeats that equality, with the classifier of the
first pass and no normalization, number detector or analytical text: a string is
equal to another only if the two are the same characters, so `00123`, `123` and
`123 ` are three values, `Ab` and `AB` two, and the string `"123"` is not the integer
123. The count of a CSV file never goes through `CellReader.cells`.

**Keys (EXACT-02 to EXACT-05).** A value is put in one set, chosen by the value alone
and never by what the other values look like, and the sets hold different kinds of key,
so no value is converted afterwards and none can be merged with another:

| Value | Set | Key |
| --- | --- | --- |
| A string of 1 to 18 ASCII digits | one set per length | the integer of the digits (the length is the other half of the key, so leading zeros count) |
| Any other string (letters, blanks, separators, Unicode, more than 18 digits, a text far longer than its analytical text) | the generic set | the string |
| A JSON integer | integers | the integer |
| A JSON number | numbers | its canonical text |
| A JSON boolean | two flags | the value |

Python without a native array library has no key smaller than an integer or a string
that is still fast: the measures of lot 7b put a set of the integers of 8 to 12 digits
at 66 bytes an entry against 87 for a set of the strings of 12 characters, and a
sentinel-packed ASCII integer at 74 bytes for 170 ns more, and an open-addressing table
in `array` objects was 200 times slower. Only the digits are encoded. D is the sum of
the sizes of the sets, V the sum of the counts, `redundant` is V minus D (the
occurrences beyond the first of each value, not the number of values that repeat) and
`unique` is D equal to V in this domain (EXACT-07).

**Memory (D08, MEM-06, EXACT-05).** The plan charges an `exact_set:` state to each
field: the firm bound is a text of the longest length at the largest slot, plus 27
bytes an entry for the first 50,000 (a small set grows to four times its fill) and 4 KB
for the empty containers. The executor builds a pool with the sum of those bounds, and
every set draws from it: after each batch (every 4,096 native values) it charges the
bytes it holds (the table of each set as Python sizes it, and the size of each key it
added). The first set that makes the pool exceed its total is stopped: its sets are
freed, the entry is `limited` with the reason `memory_budget` and a result of kind
`distinct_limited` that holds `values_read` and a `lower_bound` (the distinct values
proven at that point). The count of a prefix is never `distinct`. The other analyses of
the pass go on, and the digest of the reading is still compared. The bound can be
exceeded by a value the plan could not see, whose raw text is much longer than its
analytical text (blanks around it), which is the case that is reported rather than
undercounted.

**Frequencies.** `exact_frequencies` applies to a field with a complete table of at most
1,000 values whose listing in the Scan is cut. The table is keyed by `(native type,
analytical text)`, as the Scan keys its own, and sorted by decreasing count, then text,
then type. It is checked against the Scan: the number of values, the number of distinct
values, and that the entries the Scan lists are the head of the table. A source with
more distinct values than the Scan found stops adding new ones and fails with
`scan_mismatch`. The dense counters of the histogram are not used: they merge `7`,
`007` and the integer 7, which are three values here, and a table of at most 1,000
entries (about 210 KB at the firm bound) is smaller than an array of 65,536 counters (512 KB).
The Scan lists every distinct value with its exact count in its samples when it has no
more than K of them (`max_samples`, 10,000 by default), so the analyzer applies when
the K of the Scan is lower than the number of values of the field.

**Cost.** Measured on the baseline (`planner_costs.py executor`, 1 million rows): 373 ns a cell for
the exact set of four fields of one million values and 317 for one on another file, 108 for
the table of four fields of 300 to 900 values, so both are CPU class `low`. A forced
`tabalyst scan --deep --yes` of the combined file runs 8 analyses (two counters, two bins,
four exact sets) in 10.6 s (estimated 5 to 14 s; reading 3.6 s) and finds the exact
number of distinct values of the identifiers (1,000,000 and 1,000,000, against a KMV
estimate of 1,000,000 and 984,843), of the postal code (130,082 against 131,022) and of
the claim amount (115,667 against 115,800); the plan asks first, as the sets go beyond
the 128 MiB of an automatic choice (`memory_over_automatic`), and the process peak is 438
MB for a firm bound of 443 MB. Run again, nothing is read: 0.9 s.

### 20.9 Validation of patterns (lot 7c, PAT-07 to PAT-11, C11, O39; rewritten by the Patterns lot P1, PAT-21 to PAT-27, O65)

`secondpass/patterns.py` counts the occurrences of the whole field against the families that the discovery of 18.12
found in a sample of its distinct values. It works in the original domain (21): the raw string of a content cell,
blanks and case kept. The lot P6 of the Patterns plan implements this section (`secondpass/patternreader.py`, the reader
of the hierarchy, and `secondpass/patterns.py`, the accumulator and its result); the flat list of compiled candidates
of the lot 7c is gone.

**Population.** The content values of the field, `values`, which the Scan counted (`values.count`; empty cells and null
markers are its `missing`). A value longer than `scan.pattern_inference.max_value_length` is excluded as `too_long`,
a value of more than 32 tokens as `too_complex` (only a value of 33 characters or more is tokenized to find out), a
JSON number that is not an integer or a boolean as `non_string`: the exclusions of the discovery, counted. A JSON
integer is read as its decimal text, as the discovery reads it (lot P2). A field that is not `eligible` in
the discovery (18.12) has nothing to validate. Every other value is tested.

**Recognition, once per value (PAT-21, PAT-07, PAT-08, FR-013, TR-002, TR-007).** The families are compiled once,
before the reading, into one recognizer per family: the structure key of a value (the tokens without their lengths) is
read in one pass and finds the family; the pattern is found by the lengths read, the nodes by the content extractors the
family publishes (head, tail or token of a given position). A value counts for one family and for the deepest pattern
and node that read it, and the counters of its ancestors are those of the sums of their descendants, so the work per
cell is that of the reading of its structure and a few table lookups: it does not grow with the number of published
variants (AC-027). An ASCII value is read by a compiled recognizer whose repeats are possessive (nothing backtracks);
a value with a non-ASCII character goes through the token matcher itself, and a test compares the two on random
signatures and values. The cost model of 20.2 gets a per-cell cost for the family recognizer and a per-field cost that
is flat in the number of variants; both are measured with 10, 64 and 256 variants (AC-027) and calibrated, not guessed.

**Tables, bounded by bytes (PAT-22, FR-007, TR-003, DEC-007).** The values of a facet are counted in a table whose
capacity is a deterministic budget in bytes (never a measured time, 20.2). A value the discovery knew is counted in its
cell; a value of a facet that the discovery did not see is counted in the same table (an eighth to a twelfth prefix,
RC-14). When the table is full, the most frequent values are kept (a bounded counter with a stable order for ties),
the rest are counted in `others` and the result says `saturated` and the capacity; a limited table is never presented as
complete. The tables of a field are independent of the other fields, serializable and merged by key, so the routes in
worker processes (20.18) give the same result as one process (TR-005).

**New variants (PAT-23, FR-013, FR-015, C-02, OPEN-012).** The validation never looks for new *structures* in the
values that no family reads (PAT-11 stays: a bounded discovery of unseen forms would be a separate result). It does count
new *variants of a known family*:

- a **new variant of length**: the structure key is a known family's and the set of lengths of its variable tokens was
  never seen in its patterns (`INV-10000` among `INV-999`, `INV-9999`, `INV-99999`, DEC-034);
- a **new variant of segment**: the family and the lengths are known and the value of a segment, a head, a tail or a
  token, that a facet reads is not among the values the discovery listed (the ninth to twelfth prefixes of RC-14).

A new combination of segments each known (a known prefix with a known suffix that no sample showed together) is counted
as `known` in the V1; whether it is a new variant is OPEN-012 and decided on real cases. A value of a new variant of length belongs to its family and to no pattern (the family counts it apart); a value of a new
variant of segment belongs to the pattern whose lengths it has, in the `rest` of that pattern, and to the cell of its table.
Neither is ever counted in `other`.

**Outcomes (PAT-24, FR-015, DEC-015, REC-006).** Each occurrence has one of these outcomes, written as counts in the
result: `known` (a family and a pattern or node of the discovery read it), `new_variant` (above, with its two kinds),
`unknown_structure` (no family reads it: it is an observation of structure and never an error, PAT-10). The fourth
outcome of the plan, `atypical` (rare or far from the dominant structure), is not counted at the validation: it is the
observation `minority_pattern`, read from the hierarchy (18.13). The fifth, `invalid`, is reserved for the violation
of an explicit rule; no rule exists in the V1, so it is never written and a test makes sure a result has no such key.
The dominant pattern is not a constraint. A result adds up: the occurrences of the patterns of a family and its new variants
of length are the family's, those of the children of a node and of its rest are the node's, the families plus `unknown_structure` plus `excluded` are
`values`, and every ancestor is the sum of its descendants; the executor checks it, and `check_scan` checks it in a
stored result.

*How the lot P6 reads it.* The reader is compiled once for a field, from its entry in the Scan and from the
population the discovery read (`patterninfer.tokenized_population`), which it recognizes again: that gives it, for each
family, the combinations of lengths the sample showed (which pattern holds each, or the table of `lengths`) and, for each
facet the nodes or the tables of the family read, the segments the sample showed that no cell holds (`seen`): a facet
is *closed* when there are none, every value of the sample being a cell, and *open* otherwise. It checks the
entry against the samples as it learns (the distinct values of every family, pattern and node must be the published ones,
and the values of no family those of `other`) and raises `scan_mismatch` otherwise: a Scan whose entry was not made from its
samples is never validated. A node is read by its `value` (the text it fixes at its facet; the structure for a node of
composition), found in the dictionary of the children of its parent, so the work of a value is its tokenization, the key of
its structure, the lengths of its tokens, a few lookups down the tree (the depth is at most 5) and one lookup for each facet.
It does not grow with the number of patterns and nodes (AC-027). Every string, ASCII or not, goes through the same
tokenization as the discovery, so the two cannot disagree; a test checks that a value a pattern signature reads is counted in
that pattern. A value is found in its pattern by its lengths and not by its signature: the constants a pattern folds do not
bind its members (DEC-026). Each facet has one **table** of the validation, whatever reads it in the discovery (nodes, a table,
or both): its cells are the texts the discovery listed, read at the lengths they have (a head or a tail at each, the whole
token), and a value that is no cell is counted in a new cell of the table when the sample never showed it (up to the capacity,
`deep.patterns.table_bytes` divided by 128 bytes a cell) when the sample showed the facet closed, and in `others` otherwise. The table keeps the `capacity` most
frequent cells, the ties in the order of their text, and `saturated` says that `others` is not empty. A whole token longer than
four characters is never a cell. A value that the table of a closed facet counts as new is a **new variant of segment**, unless its
lengths are new; an open facet (the digits of a date, the tail of a code, in a sample that showed many) flags nothing,
since the sample already showed that it varies: a new value there is not a variant, and a rule that said otherwise
would call a quarter of the dates of a file new when the sample holds a hundred of them. A value of a known structure whose lengths neither a pattern nor the sample's table of lengths holds is a
**new variant of length**, counted in its family only. The occurrences of the family are those of its patterns, of its table of
lengths and of its new variants of length. The distinct values are counted in one set of the field, whose bytes are
`deep.patterns.distinct_bytes` (90 bytes and the text for each value): a value that does not fit is not held and not counted,
so the `distinct` of the bucket that would have counted it, and of the nodes above, is `at_least`. When the Scan holds every
distinct value (`computed_from` `samples`) each entry is a distinct value, no set is needed and the counts are exact. The
accumulator is a plain object that a worker process receives and returns by pickle (a field is held by one worker), and the
result is the same whatever the number of workers (TR-005). The result is `PatternCounts`: `families` (each with `patterns`
and their `nodes` as `PatternNodeCount`, `occurrences`, `distinct`, `rest`; `tables`; `new_variants`), `unknown_structure`,
`excluded`. The reader is shared (lot P7): `HierarchyReader.pattern_class` gives the pattern of a string by its place in the
document (the counters know their pattern, `pattern_of`), which is how `PatternCoder` (the feature `pattern` of the tables
of a column against a category and of the tests on a row of the smart sample) and `residual_values` (20.20) classify.
The cost per cell is `NS_PER_CELL["pattern_family"]` and `["pattern_facet"]` for each facet (AC-027,
`tabalyst-lab/benchmarks/pattern_validation.py`, `benchmarks.md`).

**Result (PAT-09, PAT-10, FR-014, FR-020).** `pattern_counts`, revision 3 of the second-pass document:
`computed_from` (`samples` or `source`), `grammar_version`, `algorithm_version`, `values`, `matched`, `families`
(each family, its patterns and nodes with `occurrences` and `distinct`, its `tables` with their `cells` and `others`,
`saturated`, its `new_variants` as `{length, segment}` counts), `unknown_structure`, `excluded`. The number of values is the Scan's, so a source that
is not the one the Scan read fails the analysis with `scan_mismatch` and no result. The distinct values of a node are
`{count, accuracy}` with `accuracy` `exact` when the Scan holds the whole distribution or the exact set fits the
budget (20.8), and `at_least` otherwise: a bound is never presented as exact (OPEN-011); no estimate is made in the V1.
The `residual_values` of 20.20 keep the values that no family reads, per node where the exposure allows.

**Without the source (PAT-25).** When the discovery read every distinct value of the field (`population.complete`: nothing
excluded, nothing cut), the Scan lists each with its exact count and `requires_source` is false: the same recognition
runs over those entries (`derive_from_samples`), `computed_from` is `samples`, and the second pass reads nothing for it.
The result has the same JSON structure by either path (TR-009), and a test makes both paths agree on the same data. The
executor checks again that the samples are `all`, complete and exact, and fails with `scan_mismatch` otherwise.

**Provenance and cache (PAT-26, FR-020).** The key of the analysis in the second-pass document (20.4) includes the grammar
version, the algorithm version and the digest of the settings of the discovery (`scan.pattern_inference`, without
`enabled`) and of the validation (the capacity of the tables): they are parameters of the candidate of
`pattern_validation` (`grammar_version`, `algorithm_version`, `discovery_sha256`, `table_bytes`, `distinct_bytes`), fed
by `PatternFacts` from the Scan. A changed setting makes the Scan stale (21) and, with it, the document of the
analysis; a Report rendered again from the same Scan and document reruns neither (AC-021).

**Consistency (PAT-27).** `check_scan` validates a result of the hierarchy of 18.12 (18.12, "Consistency of the hierarchy")
and `check_pattern_counts` (`secondpass/patterns.py`, lot P7) validates `pattern_counts` against the entry it was made for
(the accumulator calls it before it returns a result, and a failure is a `scan_mismatch`): one result for each family, the
families, patterns and nodes of the entry in its order, the families plus `unknown_structure` plus `excluded` the values, a
family its patterns, its combinations of lengths left in a table and its new variants of length, a node its rest and its
nodes, no more distinct values than occurrences, and tables bounded by their capacity that complete the family (or its
lengths) with `others`. `check_scan` checks the entry itself: the sums, the parents and children (every `parent` exists, a
node's level is its parent's plus one), the number of entries (one per field, the eligibility of each) and, when the samples
are complete, that every example exists and matches its signature.

### 20.10 Distribution of dates (lot 7c, TIME-01 to TIME-03, D12, O39)

`secondpass/periods.py` counts the dates of a field per calendar day, month or year,
as the planner sized them from the span of the Scan (20.5).

**One reading as the first pass.** The date detector of the Scan's configuration reads
the analytical text of each distinct string of a batch (`CellReader.cells(dates=True)`),
so a value is the date, the ambiguous value or the non-date the first pass said. An
`ambiguous` value is counted and never placed, as the first pass never compared it
(`ambiguous_order` of the configuration resolves it the same way in both). A value of
another kind than the one the Scan found (a time, a datetime in a column of dates) is
not placed and counted in `unplaced`: dates and datetimes are not merged (TIME-03), and
a field of several kinds has no analysis.

**Zone and boundaries (TIME-01, TIME-02).** A value is placed by the calendar date it is
written with: the offset of an aware datetime is not converted, so `2024-03-10T23:30:00-05:00`
is the 10th and not the 11th in UTC, and a change of daylight saving time moves nothing.
A day is `YYYY-MM-DD`, a month `YYYY-MM` (a calendar month, not an interval of seconds),
a year `YYYY`. The result lists the non-empty periods in order with `first` and `last`;
the periods are sized before the reading from the span, and the counters are 8 bytes each.
A column of years the Scan already counts (`years_counted`) is `already_satisfied`.

**Result.** `periods`: `granularity`, `temporal_kind`, `zone` (`as_written`), `values`
(content strings read), `count` (placed), `ambiguous`, `unplaced`, `first`, `last`,
`periods`. `count` is the number of values of this kind the Scan counted in
`temporal.kinds` and `ambiguous` the one of `temporal.ambiguous`; a difference is
`scan_mismatch`, not a result. A column of datetimes is a temporal field for the
planner although its technical type is `text` (the Scan calls `date` a calendar date
only), when at least 80% of its values are of one datetime kind.

### 20.11 The second pass inside the Report (lot 7c, A13, A14, 18.2, O39)

`report_chain.py` decides, plans and runs the second pass of a Report; `service.py` and
`report_service.py` call it between the Scan and the files.

**Flow.** A report of a source: scan (or reuse the stored Scan), plan the second pass,
run it, build the profile with `analyses`, write the JSON and the HTML. The planning
sits on `plan_second_pass` with the analyzers that have an executor; the document is
written beside the Scan like `scan --deep` does (`deep_store.write_deep`: not rewritten
when nothing was computed), so a second report finds it and reads nothing. A presentation
setting is not an input of an analysis (20.4), so changing one reads no source (A14).

**Who decides (`chain_mode`).** `--deep` forces; otherwise `deep.mode`: `auto` plans
automatically (the planner takes what is useful and cheap and never goes beyond an
automatic limit, so it never asks), `off` plans nothing, `force` is `--deep`. A forced
second pass that needs a confirmation (20.3) asks once for the batch, after the sources
are scanned: the Scans of a forced batch stay in memory until the answer, like those of
`prepare_deep`; an automatic report is finished source by source. Time already spent
is kept, so a wait for an answer is not counted in `processing_seconds`.

**A Report of a scan document (18.2).** It reads no source (the promise of `--scan`):
the analyses a stored `<stem>.deep.json` already holds and the ones the Scan alone
answers are in the report, and every analysis that needs the source is `skipped` with the
reason `source_not_read`. `--deep` reads the source beside the document and fails with
`SourceNotReadable` (exit code 4) when it is not there; without `--deep` a source that is
not beside the document gives the reason `source_unavailable`. The base report is always
rendered; the analyses that could not run are named, never silently absent.

**`analyses` (member of the Report root).** `mode` (`auto`, `forced`, `off`), `outcome`
(`ran`, `reused`, `nothing_selected`, `disabled`, `unavailable`, `failed`), `reason`
and `deep`, the second-pass document of 20.4 whole: its plan with every candidate and
why it was kept, answered by the Scan or left out, and the results. An automatic second
pass that meets an error (a source that changed or went away since the Scan) is `failed`
and the report goes without it, with a warning; a forced one raises, since it was asked for.
The common loader ignores the member (19.2) and the schema of the Report describes it.

**Pages.** The HTML reads the member and nothing else (HTML-01): a section Second pass
(who decided, the analyses computed, not computed, answered by the Scan and not selected
with the planner's reasons, and whether the source was read and verified), the exact
distinct count in place of one a scan limit stopped (only while no normalization stage
changes the values: the exact count is of the originals), the exact or estimated median a
scan limit released, the validated occurrences of every pattern, and the dates per period.
Histograms, lengths and the complete frequencies are in the JSON and listed in the section;
their charts are not drawn yet.

### 20.12 Pairs of numeric columns (lot 8a, D13, D14, REL-04 to REL-10, COST-05, E01, E02, O40)

The second pass can count the Pearson correlation of a pair of numeric columns over
every row. The number of pairs is quadratic, so the work has two stages: an exploration
of the row sample, when the plan is made, chooses the pairs worth counting (REL-04 to
REL-06), and the executor counts those over the source (REL-07 to REL-09).

**Exploration (`planner/relations.py`).** It reads the row sample of each dataset
(`records.sample`) of the Scan in memory and nothing else.

- *Rows.* A sample that lists no row, or fewer than it sampled (a Report), is not used
  (`no_sample`, `sample_reduced`). A complete sample is the whole population and is used
  whole (`scope: all_rows`); otherwise only the interior rows are a sample (ROW-07,
  `scope: interior_rows`), and fewer than `explore_min_pairs` (30) of them make the dataset
  `too_few_rows`. The first and the last rows say nothing of the rest of the file.
- *Columns.* A field takes part when its technical type is `integer` or `number`, its
  numeric measure is complete, it is not withheld by exposure, its path does not repeat
  in a record (an `ItemsSegment`: a pair never crosses the items of an array, no
  `explode`), it varies (`numeric.min != numeric.max`), it is not an identifier (the rule
  of 20.5, or an integer field whose values are 99% distinct, whatever its name) and its
  cells are in the sample, whole (`RowSample.covers`: none cut or hidden), with at least
  `explore_min_pairs` numbers. Each exclusion has a code (`not_in_sample`,
  `constant`, `sensitive_exposure`, `repeated_path`, `identifier_like`, `too_few_values`,
  `measure_unavailable`, `column_budget`) and is counted in the plan, never dropped in
  silence. Cells are read by the `CellReader` of the Scan's configuration (the same
  normalizer and number detector as the first pass); for a JSON source, whose native
  numbers the sample writes as text, a decimal also reads what the detector would not.
- *Budget (COST-05, REL-06).* At most `max_columns` (50) columns, and at most
  `max_work` (1,000,000) pairs times rows compared: the columns beyond the budget are the
  least present ones (ties keep the order of the document) and are counted as
  `column_budget`. The work is the post-processing budget; it depends on the data and the
  settings, never on a measured time. All the pairs of the kept columns are scored.
- *Score (REL-05).* Over the rows where both columns have a number: count, coefficient
  (`scanner/pearson.py`) and the 95% interval of Fisher's transform (an estimate: it
  assumes rows drawn at random from a bivariate normal distribution). A pair with fewer than
  `explore_min_pairs` common rows, or a column that does not vary over them, is undefined
  with its reason and is not listed. The `score` is the smaller absolute value the interval
  allows (0 when it holds 0), so that a high coefficient on a few rows does not outrank a
  steady one on many. Figures are rounded to six decimals so that the plan is the same on
  any machine. "Not detected in the sample" is not "absent": rare exceptions can be missing
  (REL-05).
- *Candidates.* The pairs with a score above 0 by decreasing score (ties: more rows, then
  the order of the columns), `max_candidates` (20) at most. A pair named by a request that the
  exploration did not list is a candidate too (REL-06), scored from the sample when it can be,
  and not applicable (`not_numeric`, `sensitive_exposure`, `repeated_path`,
  `measure_unavailable`) when a column cannot be a number. The pair is in the order of the
  dataset whichever way it was asked.

**The plan.** `relations.datasets[]` has, per dataset with two numeric columns, `scope`,
`rows`, `numeric`, `columns`, `excluded` (by code), `possible` (pairs of the kept columns),
`evaluated`, `undefined` with `undefined_reasons`, `listed`, `work` and `unavailable`. A
candidate's `utility` is 100 times its score (reason `exploratory_correlation`); the planner
picks by itself the pairs of 45 or more (a lower bound of 0.45), `automatic_pairs` (8) at most,
and the others are rejected `pairs_budget` (a forced plan takes all those listed, a request
those it names). The `costs` of a pair hold `PAIR_STATE_BYTES` (512) for its co-moments, the
batch of floats of each column (`PAIR_FEED_ROWS` x `PAIR_FEED_ENTRY_BYTES`, one state per column
shared by every pair that uses it, REL-03) and the memory of reading its cells; the time
estimate counts the cells of both columns.

**Executor (`secondpass/pearson.py`).** `ColumnFeed` converts the strings of a column once
per batch (a CSV batch) or the values of a record (JSON, Excel; the rows wait in a buffer of
`PAIR_FEED_ROWS` records) into float64, with the memory of the replayed cells; a value that is
not a number, or does not fit a float64, is missing. It counts the numbers as the Scan counts
them. `PairAccumulator` takes the aligned rows of the two columns:

- the rows where both have a number give count, means, sums of squares and cross product by
  a centered pass, merged with the batches before by the update of Chan et al. (stable
  whatever the sizes and the order), with the minimum and maximum of each column
  (`scanner/pearson.py`);
- the other rows are counted as `first_missing`, `second_missing` and `both_missing`, so that
  `rows = pairs + first_missing + second_missing + both_missing`;
- the means are those of the common rows, never those of the Scan (REL-08);
- fewer than `min_pairs` (10, part of the key) common rows give `insufficient_pairs`, a column
  whose minimum equals its maximum gives `zero_variance_first` or `zero_variance_second`
  (decided by comparison, so no float error hides a constant), and the result is `defined: false`
  without a coefficient, never 0 (REL-09, E02); a coefficient is clamped to [-1, 1];
- the numbers the reading found in each column must equal the Scan's `numeric.count`, or the
  pair fails alone with `scan_mismatch`.

The result is `pearson` (20.4 and the public page `deep-format`): `accuracy` is `exact_counts`
and `precision` `float64`: the counts are exact and the coefficient is computed in float64,
which agrees with an exact fraction oracle to 1e-12 on the tests. It is a linear association
and not a cause (REL-10). `Router` hands each pair the aligned rows of its two columns once;
a pair or a column that fails does so alone. `cells_read` counts each column once.

**Complete sample.** When the Scan holds every row of a CSV dataset (`records.sample.complete`)
and covers both columns, the pair is `requires_source: false`: the executor computes it from the
rows of the sample with the same arithmetic and `source` is `samples`. Other formats read the
source, since their sample cells (canonical text of native values) may differ from what the
reading counts.

**Key.** It holds both fields (`partner`), the method and `min_pairs`, not the exploration, the
budgets or the order: a stored pair is reused whatever chose it.

**Report.** The Second pass section lists the pair as "price and cost" with the coefficient and
the common rows (`report_deep.result_summary`); the pairs are also listed in the Relationships
section (20.13, `report_relations.py`).

**Costs.** `NS_PER_CELL["pearson"]` is the time a cell of a column of a pair adds, the reading of
the cell included, 1.5 ns, `moderate`; a shared column is read once, so the estimate is an
upper bound for pairs that share columns. `COST_MODEL_VERSION` is 5. Measures:
`benchmarks.md`, "Pairs of numeric columns (lot 8a)".

### 20.13 Tables of a category against a feature (lot 8b, D14, REL-01 to REL-03, REL-11 to REL-16, E03 to E05, HTML-06, O41)

A category column, a branch, can determine the shape of another column, a client identifier. The
second pass counts, over every row, how many rows of each category fall in each class of a feature
of that other column. As for the pairs of 20.12, the work has two stages: an exploration of the row
sample, when the plan is made, chooses the tables worth counting (REL-02, REL-04 to REL-06), and the
executor counts those over the source (REL-11 to REL-15). The planner has no special case for either
kind: a `PairAnalyzer` explores, assesses, estimates and rates its pairs, and has its member of
`relations` (`datasets` for the correlations, `tables` for the tables).

**Features and classes (`scanner/features.py`, REL-01, REL-12).** A feature turns each value of a
column into one class of a set that is fixed before the source is read again, and that only the Scan
decides: nothing creates an axis while the source streams. Every set ends with the explicit class
`other`, which stays in the result when it is empty.

| Feature | Reads | Domain (21) | Classes |
| --- | --- | --- | --- |
| `pattern` | the original string | `original` | the candidates of `derived.patterns`, by the exclusive classification of 18.12 and 20.9 (`PatternClassifier`, shared with the validation) |
| `length` | the analytical text, in characters | `analytical` | the `max_classes` - 1 most frequent lengths of the exact histogram of the Scan, in increasing order |
| `prefix` | the first `prefix_length` characters of the original string | `original` | the `max_classes` - 1 most frequent prefixes of the values the Scan lists, counted with their exact counts |
| `value` (lot 16, 20.22) | the analytical text, as a category | `analytical` | the `max_classes` - 1 most frequent values of the exact frequencies of the Scan |

A category is read in the analytical domain against the exact frequencies of the Scan: its
`max_categories` most frequent values are rows, the rest is `other` (a JSON value keeps its native type,
so the integer 1 and the string "1" are two rows). A value is coded `MISSING` when the row has none
(empty, blank, a null marker, an absent key, a repeated path) and `UNCLASSIFIED` when the feature does not
classify it: a value that is not a string (a JSON number or boolean, for the three features), longer than
`max_value_length` or of more than 32 tokens (`pattern`). The classes of a prefix come from the Scan and not from the
plan, since the plan holds no value of the data: it holds their number.

Who may play which part. A **category** has complete frequencies, listed at least as far as
`max_categories`, between 2 and `max_distinct` (100) distinct values, is not withheld by exposure, does not
repeat in a record, does not look like an identifier (the rule of 20.5) and has at most half of its values
distinct (`near_unique`): a value that never repeats is not a category. The **column** of a feature is a
text, mixed or integer column, withheld by no exposure, and offers the feature when the Scan has its classes
(`no_pattern`, `no_lengths`, `few_lengths`, `no_values_listed`, `few_prefixes`: at least two classes). A
column is never its own feature.

**Exploration (`planner/crosstabs.py`).** It codes the rows of the row sample of each dataset (`samplerows.py`:
a complete sample is the whole population, otherwise the interior rows only, ROW-07, and fewer than
`explore_min_rows` (30) of them are too few) and scores every table of the kept columns with the
bias-corrected Cramér's V (below), rounded to six decimals so that the plan is the same on any machine. It
reads the Scan only, and its work is bounded by quantities, not by a time: at most `max_columns` (50)
columns, and `max_work` (1,000,000) tables times rows coded; the least present columns are left out and
counted `column_budget`. Every exclusion has a code counted in the plan (`excluded_categories`,
`excluded_features`), and a table without a score has its reason in `undefined_reasons` (`too_few_rows`,
`single_category`, `single_class`): none is dropped in silence, and "not found in the sample" is not
"absent from the file" (REL-05). A dataset with no eligible category has no block.

*Candidates.* The tables with a score above 0, by decreasing score (ties: more rows, then the order of the
document), `max_candidates` (20) at most; a table named by a request that the exploration did not list is a
candidate too (REL-06), scored from the sample when it can be, and not applicable (`sensitive_exposure`,
`too_many_categories`, `no_pattern`...) when a column cannot play its part. The category is always the row
axis (`AnalysisRequest.field`, then `partner` for the column and `feature`; no feature asks for the three).
The id is `category_crosstab:dataset:category>column:feature`; `parameters` hold what a result depends on
(`feature`, `max_categories`, `examples`, `rule_purity`, `rule_support`, and `max_classes`, `prefix_length`
where the feature uses them).

*Redundancy (REL-16).* Of the features of the same two columns, only the one with the best score is eligible
for the automatic choice: the others wait for it and are rejected `redundant_feature` once it is chosen, or
chosen in its place when it was not (budget, CPU class), so that a relation is not lost for being told twice. A request, or a forced plan, takes them
all, and the report groups them. The utility is 100 times the score (reason `exploratory_association`); the
planner picks by itself the tables of 45 or more, `automatic_tables` (8) at most (reason `tables_budget` for
the others).

**The plan.** `relations.tables[]` has, per dataset with an eligible category, `scope`, `rows`, `categories`,
`columns`, `excluded_categories`, `excluded_features`, `possible`, `evaluated`, `undefined`,
`undefined_reasons`, `listed`, `work`, `cells` (the largest table, rows by classes, counters included, REL-11)
and `unavailable`. A candidate has an `exploration` that says `scope`, the classified `rows`, the effective
`categories` and `classes`, the `purity`, `cramers_v` and `score`. The `costs` of a table hold the counters
and the examples of its cells (`TABLE_CELL_BYTES`, `TABLE_EXAMPLE_BYTES`), the batch of codes of each column
(`PAIR_FEED_ROWS` x `CODE_FEED_ENTRY_BYTES`, one state per column and feature, shared by every table that uses
it, REL-03), the coder and the memory of reading its cells; the time estimate counts the cells of both columns.

**Executor (`secondpass/crosstab.py`).** `CodeFeed` converts the strings of a column once per batch (a CSV
batch) or the values of a record (JSON, Excel; the rows wait in a buffer of `PAIR_FEED_ROWS` records) into
codes, with the memory of the codes of the strings it has seen; `Router` accepts several feeds on a column
(the category, the pattern, the length of the same column) and hands each table the aligned codes of its two
columns. `CrosstabAccumulator` counts the pairs of codes of a batch at once:

- the rows with a class in both axes make the table (`counted`); the others are `category_missing`,
  `feature_missing`, `both_missing` and `unclassified`, so that `rows = counted + excluded` is checked, as is
  each column's number of values against the Scan's (`scan_mismatch` fails the table alone);
- the first `examples` (3) rows of every cell in source order are kept with their record number and the value
  (cut at 64 characters), because the dominant class of a category is only known at the end; only the cells
  that turn out to be exceptions are listed. A batch is scanned for them only when it holds a cell that has
  fewer than `examples`, so the cost does not grow with the rows;
- a complete sample of a CSV file answers without reading the source (`source` is `samples`); other formats
  read it, since the cells of their sample are the canonical text of native values.

**Result `crosstab` (REL-13, REL-15).** `accuracy` is `exact_counts` and `precision` `float64`: the counts are
exact, the purity and the coefficients are computed from them. It holds the axes (`categories`, `classes`,
each with its field, its domain and its classes in the order of the counts), the `feature` (kind, version,
`prefix_length`), `rows`, `counted`, `excluded`, the `counts` with the `row_totals` and `column_totals` (the
margins), `by_category` (the rows of a category, how many of them are in the table and the `coverage` it gives,
its `dominant` class, its `purity` and its `exceptions`), `purity`, `association`, `exceptions` and `rules`. A
class `other` or a category with no row stays in the table with zero counts and takes no part in the scores.

*Purity and the dominant class.* The forward purity A to B is the sum, over the categories, of the count of
their dominant class, over the counted rows; the reverse purity is the same from the classes, and is another
figure (REL-13). A tie goes to the first class listed. `purity.baseline` is the share of the most frequent
class, the purity of an answer that ignores the category. The exceptions are the rows outside the dominant
class of their category, as exact counts (`exceptions.count`, `cells`) and the `listed` largest cells (20) with
their first rows.

*Association (`scanner/crosstab.py`).* Cramér's V over the rows and the columns that have a count (the
effective ones; a zero margin takes no part but stays visible, REL-14) and Bergsma's bias-corrected V, which
does not grow with the number of classes or shrink with the rows the way V does and is what the planner ranks
by. With one effective row or column, or fewer than two counted rows, there is no score and the `reason`
(`single_category`, `single_class`, `too_few_rows`) says why: never 0. The score is `stable` unless more than a
fifth of the cells of the axes that hold at least 5 rows has an expected count below 5, or one is below 1
(`low_share`), or fewer than two rows or columns hold that many: an axis of fewer rows is `sparse`, counted in
`association.sparse` and left out of the test, so a stray class of one row does not make a solid table
unstable. An unstable score is never called strong. The exploration records `stable` in the exploration of a
candidate and does not gate on it: a sample of 900 rows has fewer counts than the file. The coefficients are float64; the oracle of the tests is exact fractions and agrees to
1e-12.

*Candidate rules (REL-15).* A category whose dominant class is a pattern, a length or a prefix (not `other`),
with at least `rule_support` (30) counted rows of which `rule_purity` (90) percent are in that class, gives a
rule with `status: candidate` and `provenance: learned`: a rule a user approves is another thing, with its own
provenance, and is not delivered here.

**Key.** It holds both fields (`partner`), the method and the parameters above (the feature, the classes it
reads, the examples and the thresholds of the rules), not the exploration, the budgets or the order. The
`domain` of an analysis of a table is `mixed`: each axis of the result names its own.

**Report (HTML-06, 18.14).** The Relationships section prints, for each pair of columns, one block with the
leading feature first and the others folded (REL-16): the sentence, the metrics (classified rows, purity,
association with its strength word or `unstable`, exceptions), the table of counts with the percentage of each
category in every cell before any score, the exceptions with their first rows, and the candidate rules, said
to be learned and not validated. It also lists the correlations of 20.12 and says what the planner explored on
the sample. `report_relations.py` builds it from the `analyses` of the document.

**Ranking and stability (lot 11, O45, amended by lot S3a).** The exploration ranks the tables by `(weak, redundant, unstable,
-score, -rows)`, where `weak` is a score below `STRONG_SCORE` (0.45, the threshold of the automatic choice) and `redundant`
marks the features of a pair of columns that score below the best one (REL-16). A table whose expected counts are too low to
trust (`stable` false, the rule above) comes after every stable one of the same kind, and is never left out for that reason
(it stays listed with its caution). Lot S3a changed two things that filled the `max_candidates` (20) places with tables of
little use: an unstable table of 0.45 or more ranks before the weak stable ones (the automatic choice would not take them
anyway), and the redundant features rank after the first feature of every other pair. Measured on the 100,000-row
case: the table of the province code against the province name (V 0.90, unstable, a few rows per rare province) was
not listed, and its exception cell holds the 3 rows of `province_code_city_mismatch`. The score of a table of few large cells is a
fair indicator; the score of many small cells is inflated by chance, and the automatic budget (`automatic_tables`) no
longer spends its tables on them while a stable one is left. The report prints a pair that is listed in both
directions (category A by column B, then B by A) as one phenomenon: the weaker direction follows the stronger one,
collapsed, and no count is merged or lost.

**Costs.** `NS_PER_CELL["crosstab_pattern"]`, `["crosstab_length"]` and `["crosstab_prefix"]` are the time a cell
of either column of a table adds, the reading of the cell included: 600, 500 and 300 ns, all `low`,
rounded up from the measures on the combined file (445, 412 and 230 ns for each cell handed to the
analyses, columns shared by several tables counted once; the planner charges each table both its columns,
so its estimate is an upper bound for tables that share one). `COST_MODEL_VERSION` is 6.
Measures: `benchmarks.md`, "Tables of a category against a feature (lot 8b)".

### 20.14 Help with stratification (lot 9, D16, D17, STRAT-01 to STRAT-08, E06 to E08, O42)

`stratified` sampling keeps its classical statistical meaning (D16, STRAT-01): each stratum gets rows in
proportion to its size, by the largest remainder, and a stratum whose quota rounds to zero is absent. The
arithmetic is `scanner/stratify.py`, shared by `tabalyst sample` and the advice so that the advice describes the
rule the sample applies: `allocate_strata` (moved unchanged from `sampling.py`), `saturating_product`
(non-negative factors, a zero wins over a saturated factor, the product stops at `SATURATED` = 2^63 - 1 and says so)
and `size_for_every_stratum` (the sample size at which the exact quota of the rarest stratum reaches 1).

**The sample (`sampling.py`).** `field` takes one name or several; a stratum is the cell for one field and a tuple of
cells for several, so `("a|b", "c")` and `("a", "b|c")` never collide (STRAT-03). An empty cell is a stratum of its own,
as it always was, and the advice declares it (`limits.missing: "own_stratum"`). The counting pass raises `InputError`
at the first record that would make more than `max_strata` strata (default 100,000, `--max-strata`), before any
reservoir exists and before the output is touched (STRAT-08). `SampleResult` gains `fields` and the balance of a
stratified sample: `strata_known`, `strata_selected` and `strata_uncovered`, the strata whose quota is zero (STRAT-02).
The rounding is the classic one; the single-field sample with the same seed selects the same rows as before.

**The advice (`planner/stratification.py`, models in `planner/stratmodels.py`, words in `reasons.STRATIFICATION`).**
`plan_analyses(scan, stratify=Stratify(...))` (or `with_stratification`, which `generate_plans` uses) adds
`plan.stratification` and recomputes `plan_id`; without a request the plan has no such member and keeps its identity.
It reads the facts and the row sample of the Scan, never the source, and writes counts and field ids, no value of the
data. It is a recommendation with its basis and uncertainty (specification 11.1), not a fact.

- *Column (STRAT-04).* Not a key: no values, exposure, repeated path, identifier, more than half of the values
  distinct, a single stratum, more than 50 strata, or a count the scan stopped tracking without an estimate. Strata are
  `values.cardinality` (the original domain, 21) plus one when values are missing; `strata_basis` is `exact`,
  `estimate` (KMV) or `bound` (`upper_bound`). `smallest_share`, `largest_share` and `size_for_every_stratum` come from
  the exact frequencies when they are complete and untruncated (analytical domain, so a little coarser than the original
  one); with `sample_size` the allocation is simulated with `allocate_strata` and `uncovered_at_size` counts the strata
  with a zero quota. `rare_strata` (rarest at 1% or less, or uncovered) warns without promising a minimum.
- *Combination (STRAT-05 to STRAT-07).* `strata_bound` is the saturating product of the certain maxima of the columns
  (the exact count, or `upper_bound`), capped by the records (`capped_by_records`). A product of estimates is
  `strata_estimate`, apart, and the reason `estimated_strata`; it is never published as the bound (E07). The row sample
  gives `observed`, the distinct tuples of its usable rows (the cell text, `None` for a missing cell), a lower bound of
  the combinations that exist, and exactly their number when the sample holds every row (`observed_exact`); the
  columns must be whole in the sample (`RowSample.covers`), else the reason says why. The risk is `low` up to 1,000
  strata, `moderate` up to 10,000, `high` up to 100,000, `excessive` above or saturated; when the sample is complete the
  exact number replaces the bound. A `high` or `excessive` risk suggests `reduce_fields`, `set_explicit_limit` and
  `use_smart` and names the widest column; a high bound proves a risk, not an explosion. `mean_quota` (the sample size
  over the bound) is a bound that does not depend on the distribution (`mean_quota_below_one`).
- *Limits* are in the plan (`limits`) as constants of version 1 of the advice: 50 strata per column, 1,000 and 10,000
  for the risk classes, 100,000 states, 8 fields per combination, 30 rows at least in the sample. They are not
  `deep` settings, so they do not enter the key of a second-pass result.

**Entry points.** `tabalyst scan --plan --stratify` (columns), `--stratify-by a,b` (repeatable, implies `--stratify`) and
`--sample-size N`; `tabalyst.Stratify`, `plan_analyses(stratify=)`, `generate_plans(stratify=)`; the text is
`stratification_lines` in `plan_text`. A request for an unknown field, an ambiguous dataset, fewer than two fields, a
repeated field or a sample size below 1 raises `ConfigurationError`.

**Not yet.** The Report prints nothing of the advice (lot 11); `sample` reads a stored Scan to refuse an
excessive risk since lot 10b (20.16, D23); `balanced` and `coverage` strategies stay extensions (specification 14).

### 20.15 Targets and the plan of a smart sample (lot 10a, D15, SMART-01 to SMART-04, 15 of the specification, E09, E12, E14, O43)

A smart sample is a sample of diversity and diagnosis (SMART-01): its proportions do not estimate the population. Lot 10a
defines what it would aim for and what it would cost; the selection of the rows is lot 10b. The plan is
`SamplingPlan` (`scanner/smart/models.py`), built by `plan_sampling(scan, deep=, dataset=, size=, seed=, settings=,
enrichment=, scan_stored=)` from a finished Scan and, when it is current, its second-pass document. It reads no source and
writes nothing, holds no date, no measured time and no value of the data, and the same Scan, second-pass document, request
and settings give the same plan (and `plan_id`, the SHA-256 of the rest) on any machine. A Report is refused as an input
(`plan_sampling_document`, 19.4). It is not a member of `AnalysisPlan`: it reads a document the planner does not, and a
plan of analyses must keep its identity.

```text
scanner/smart/
|-- models.py    SamplingPlan, Target, Predicate, Frequency, Weight, Catalog, Sizes, Reserve, Passes
|-- targets.py   the builders of the six families
|-- weights.py   rarity() and weight_of(): monotone, capped, versioned
|-- plan.py      plan_sampling(), Smart (the request), the budget of targets, sizes, passes
|-- reasons.py   the codes the plan writes and their sentences
`-- render.py    sampling_plan_text()
```

**Target (SRS 15.3).** `id` (`family:dataset:fields:kind:discriminator`), `family`, `dataset`, `fields` and `displays`,
`predicate`, `frequency`, `weight`, `obligation` (`mandatory` or `optional`), `minimum` (one row), `feasibility` (`ready`
or `not_evaluable`, with a `reason`), `evidence` (`exact`: established on every value; `sample`: discovered on a sample;
`second_pass`: counted by the second pass), `origin` (the observation or the analysis it comes from) and `needs` (`scan`,
and `second_pass` when it stands on that document). A predicate has a `kind` and a `version` (`PREDICATE_VERSION`, which
the sample of lot 10b reads), a `source` and a `ref` into the Scan (or the second-pass document), and `params` that fix it
(a sampled entry, a pattern, a bin: an index or an identifier, never a value). A `frequency` has an `accuracy`: `exact`,
`lower_bound`, `indicator` (a share of distinct values or of another population, which tells how rare the target is
without being its frequency) or `unknown`.

| Family | Targets | Comes from | Mandatory |
| --- | --- | --- | --- |
| `low_cardinality` | one `value_equals` per distinct original value, `value_missing` | `values.samples` of a column of at most `smart.max_enum_values` (100) values; else, from a current second pass, the `exact_frequencies` table (analytical texts, at most `smart.max_exact_values` (500), optional, base `exact_value`) | when the table lists every value (`samples.selection == all`, exact cardinality) |
| `structured_string` | `pattern_matches` per inferred candidate, `pattern_other`, `length_min`, `length_max` | `derived.patterns`; the exact length histogram; the counts of `pattern_validation` when the second pass has them | never |
| `numeric` | `numeric_min`, `numeric_max`, `numeric_zero`, `numeric_sign` (when both signs occur), `numeric_bin` | the numeric measure; `smart.numeric_bins` (10) bins of equal width between the exact minimum and maximum, never fewer than three | never |
| `date` | `date_min`, `date_max` per kind, `date_kind` when several formats occur, `date_year` (at most 30 years) | the temporal measure | never |
| `quality` | `observation`, one per candidate anomaly or confirmed issue that a row can show, `duplicate_rows` and `missing_values` included | `observations` | the confirmed issues the sample can recognize |
| `relations` | `relation_exception`, one per listed exception cell of a table | `category_crosstab` results of the second-pass document | never |

A column whose every value has a target (`catalog_complete`) gets no pattern, length, numeric or date target: they would
only repeat it. A column masked or hidden by exposure gets no target (`exposure`). The observations a row cannot show
(excluded records, ambiguous header, presence and normalization remarks) are not targets; those a row could show but the
sample cannot recognize yet (none today, see below) are targets with `feasibility: not_evaluable` and a reason
(SMART-11). Lot S2 makes the four remaining rules evaluable, each on one test of the cell: `trimmed_cells` and
`collapsed_whitespace` (the bit of the stage in `Normalizer.run`, so the Scan's own definition; base `remark`),
`minority_length` (the analytical length differs from the dominant one of the exact histogram) and `variant_groups`
(one target per listed group, at most `MAX_VARIANT_GROUPS` (20) per column, the largest first; covered by a row whose
comparison key is the group's and whose raw value is not the group's first variant; exact count `group.count` minus
that variant's; base `signal`, since at `candidate_anomaly` the groups of a column of names pushed out the anomalies
the Scan is surer of). No rule is `not_evaluable` now: `NOT_EVALUABLE_RULES` stays for the next rule the Scan gains.
Lot S2b adds two kinds of target of the `quality` family that stand on no observation: `characteristic` (the
unexpected characteristics of the strings of a column, `UNEXPECTED_CHARACTERISTICS`, counted by the Scan on the raw
string, whitespace-only strings included, so the test runs before the missing-cell test; only when at most
`RARE_CHARACTERISTIC_SHARE` (5%) of the non-empty strings have it) and `value_rare` (the sampled values of a text
column with a count of one, a single target per column; exact when the Scan sampled every distinct value, a lower bound
for a priority sample; none when they exceed `MAX_TAIL_SHARE` (20%) of the values, as in an identifier; base `signal`).
The one `pattern_other` per column stays: the structures that no pattern reads are already one family, hence one
`pattern_matches` target, each, so a target per kind of reject would repeat them (measured on the case).
Lot S4 reads three exact tables of the second pass that no target read (measured on the 100,000-row case, `sample-real-errors`:
nine classes of a few rows were lost, hidden in values the first pass does not list). (1) `residual_value`: one target per
value of a `residual_values` table of a detector (`invalid` or `not_matched`; a table that is complete and not truncated, whose
occurrences are at most `MAX_RESIDUAL_SHARE` (20%) of the values, at most `MAX_RESIDUAL_VALUES` (20) per column; base
`candidate_anomaly`; `MAX_RESIDUAL_TARGETS` (100) for the whole dataset, the first columns winning); a row covers it when its raw string is the listed value. (2) `value_equals` with `source: second_pass`
for a column above `max_enum_values` whose `exact_frequencies` table holds at most `max_exact_values` values (the first pass keeps
100 values chosen by hash, so half of the rare ones are missing): optional, base `exact_value` = 2 (at 5 these ~760 targets
pushed the empty cells and the zero amounts out of a 300-row sample), tested on the analytical text of the cell since the table
counts analytical texts (a table whose texts are not unique, one per native type, makes no target; a number or a date keeps its other targets, only text is `enumerated`); the catalog becomes `catalog_complete` and the column is `enumerated` for the other families.
(3) `pattern_other` is made when the second pass finds occurrences that no pattern reads (`PatternCounts.outside_patterns()`) even
if the sampled values were all read. Without a current second pass nothing changes.
Two rules of lot S1 are evaluable: `missing_values` (an empty cell, for every column that has some and no
`value_missing` target of the low-cardinality family; informational for the Scan, base `missing` and never mandatory) and
`duplicate_rows` (one target for the dataset, no field, covered by any row that repeats an earlier row; a sample holds at
least one, not one per group, because a target names no value and the Scan lists only `max_listed_records` records). The ordinary population is not a target but a reserve (below).

**Catalogs (E09, E12, SMART-13).** `catalogs` has one entry per column and family: `complete`, `guarantee`
(`catalog_complete`: every value the column can take has a target, so a large enough sample covers them all;
`known_values_only`: only the values the Scan saw, no value outside them is promised; `none`) and the `reasons` in
`reasons.CATALOG`. A column whose table of values overflowed but whose KMV estimate stays within `max_enum_values` gets
targets for the values the Scan sampled, all optional, with `domain_not_exhaustive`. A column whose count is not tracked and
not estimated gets none (`domain_unknown`). The plan covers the catalog of targets, not every phenomenon of the data.

**Weight (SMART-02, SRS 15.3).** `weight = min(cap, base * (1 + gain * rarity))`, with `rarity` from 0 (a share of 1) to 1 (a
share of `floor` or less) on a logarithmic scale, and `unknown_rarity` (0.5) when the frequency is unknown. It never falls
when the share of the target falls or when its base rises, and never passes `cap`. The bases are by kind: confirmed issue
10, candidate anomaly 6, value 5, relation exception 5, pattern 4, extreme 4, sign and zero 3, bin 2, empty cells (`missing`) 6, remarks (`remark`) 5, unexpected characters (`character`) 5, values of an exact table of the second pass (`exact_value`) 2; `gain` 1, `floor`
1e-6, `cap` 20. Everything is in `smart.weights`, written in the plan (`settings`, `settings_sha256`) with the version of the
formula (`weights_version`, 1). The values are initial and to be validated on the demos. Rarity is not an error: a rare
target weighs more but is not called an anomaly.

**Plan.** `settings`; `size` (`requested`; `mandatory_bound`: the mandatory targets, a row each, an upper bound that rows
covering several targets beat; `useful_maximum`: the size beyond which only the reserve grows; `records`); `reserve`
(`share` 0.2 by default, `rows_requested`, `rows_granted`, `reduced_by_mandatory`); `conflict` (`mandatory_first`: the reserve
never prevents an achievable mandatory coverage, SMART-10); `candidates` (`per_target` 2, the rows held in memory,
`row_bytes` as the mean size of a source row, `bytes_expected` as source text and not as process memory, `budget_bytes`,
`fits` and `per_target_effective` when it does not); `method` (`weighted_cover`, version, seed: that of the Scan unless
asked); `summary` (counts by family, `dropped`); `catalogs`; `targets` sorted by obligation, then decreasing weight, then
id. At most `smart.max_targets` (10,000) targets are kept: the lightest are left out and counted, and a catalog that lost
targets says `target_budget`. No time estimate and no confirmation threshold yet: they need the executor of lot 10b.

**Readings of the source (SMART-04, 15.6, E14).** `passes.steps` lists `scan` (needed only when no current Scan is stored,
`scan_stored`), `second_pass` and `selection` (always), each with a reason, and `passes.total` counts those needed. The
targets are built before the sample reads the source again. A second-pass document that is current for the Scan (same
`PlanBase`) feeds the targets and adds no reading; a stale one is ignored and reported (`enrichment.deep: stale`). A second
pass asked for before the sample (`enrichment=` the plan of analyses, `--smart --deep` on the command line) and not yet
stored is announced as a reading of its own, with what it would bring in `enrichment.awaiting` (numeric bins sharpened,
patterns counted, relations); the targets it would bring are not listed until it has run. Merging the second pass and the
selection in one reading is not offered: a row rejected before a statistic was known cannot be selected afterwards.
Smart never runs a second pass by itself (R1).

**Entry points.** `tabalyst scan --plan --smart` and `--sample-size N` (the text, `sampling_plan_text`, after the plan of
analyses; `--deep` counts the second pass among the readings); `tabalyst.plan_sampling`, `tabalyst.SamplingPlan`,
`tabalyst.Smart` (the request: dataset, size, seed), `generate_plans(smart=)` whose `PlanSuccess.sampling` carries the plan.
`ConfigurationError` for an unknown or ambiguous dataset or a size below 1. The `smart` object of the configuration file is
`SmartSettings` (`max_enum_values`, `numeric_bins`, `candidates_per_target`, `reserve_share`, `max_targets`,
`max_candidate_bytes`, `weights`); it is not part of `deep` and does not enter the key of a second-pass result. The plan is
not written on disk in this lot, so it has no JSON Schema yet: the report of lot 10b (SMART-12) will carry it.

**Not yet.** The selection of the rows, the report of what was covered and the time estimate came with lot 10b (20.16).

### 20.16 Selection of the rows of a smart sample and its report (lot 10b, D15, D23, SMART-05 to SMART-13, E09 to E15, O44)

The plan of 20.15 says what a smart sample aims at; this lot reads the source once more and chooses the rows. It
is `tabalyst sample --sample-method smart`, `tabalyst.generate_samples(method="smart")` and the two steps behind
it. CSV files only, like every `sample`.

```text
scanner/smart/
|-- evaluate.py  Evaluator: the predicates of the plan as tests on a row (SMART-05)
|-- select.py    SelectionPool: candidates, reserve, greedy cover (SMART-05 to SMART-10)
|-- execute.py   select_rows(): the one reading, guarded by the digest of the Scan
|-- estimate.py  estimate_selection(): time and confirmation (R1)
`-- result.py    SampleDocument: the report `tabalyst.sample`, build_document(), the schema
smart_service.py prepare_smart_samples(), execute_smart_samples(), SelectionConfirmationRequired
```

**Order of the work.** `prepare_smart_samples` plans the outputs, scans the sources through the shared storage
(`generate_scans(refresh=False)`: a current Scan is reused), reads the second-pass document if it is current
(`plan_sampling` ignores a stale one), plans the sample and estimates the selection. Nothing is asked and no
source is read again. `execute_smart_samples` checks the confirmation (`SelectionConfirmationRequired` before any
reading when the batch needs one and `confirmed` is false, R1), then for each source reads it, writes the CSV
file through a temporary file and then the report. The first pass (when no Scan is stored) and the selection are
the readings the report counts (`run.passes`); a second pass is never run.

**Tests on a row (`evaluate.py`).** The predicates name their reference into the Scan; the evaluator resolves
them once and reads each cell as the first pass did (`CellReader`, the replay of the second pass). A column has
one test object: the original value (a dictionary from the sampled value to its targets, the missing cells), the
pattern (`PatternCoder`, the pattern of the family that has the lengths of the value, 20.9), the analytical length, the number (the
extremes by exact comparison with the float64 the Scan wrote, zero, the sign and the bin by the rule of the
second pass, the last bin closed), the date (its kind, the ISO text of the extremes, the year), the findings of
the observations a row can show (`minority_pattern`, `ambiguous_dates`, `mixed_types` and `type_outliers` by the
technical family of the cell, `technical.string_family`) and, for the exceptions of a table of the second pass,
the coders of the table (`CategoryCoder`, `feature_coder`) on the category and the column of the feature. A
batch of rows tests each distinct string once; the result per string is remembered up to 16,384 strings of at
most 256 characters per column. A target that cannot be tested (`unresolved`: a reference that is gone, a Scan
that no longer supports the table) covers nothing and the report says why. `not_evaluable` targets of the plan
(none today) stay so. A `missing_values` observation reuses the test of the empty cells of the column
(`value_missing`), which counts the categories of `values.missing` as the Scan does (a null marker that
the configuration does not call missing is not an empty cell). The duplicate rows are tested on the whole row (`_DuplicateTests`): the evaluator digests every row as
the Scan did (`records.table_digest`) and remembers the digests seen, up to `limits.max_tracked_records` like the Scan, so
a row is a duplicate from its second occurrence and, past the limit, a copy of a row no longer remembered goes unseen (the
count the report verifies is then a lower bound, as in the Scan).

**Pool and cover (`select.py`).** Rows are numbered by their record, and a row has a priority (`RowPriority` of
the seed of the plan: `blake2b` of the position, shared with the row sample). For each target the pool keeps the
`per_target_effective` rows of the smallest priority that cover it, so the choice depends on the file and the
seed only, never on the size of the batches. A row is held once however many targets hold it (a count of the
roles that hold it). The bottom-k reserve keeps the `size` rows of smallest priority overall: enough that after
the cover has taken its rows the reserve can still be filled in priority order. The pool is bounded by
`smart.max_candidate_bytes` in characters of source text (cells and a separator each): optional targets stop at
80% of it so that mandatory targets and the reserve are not starved, and a row that does not fit is refused,
counted (`pool.refused_rows`, `refused` on the target) and never shortened (E15). The cover is a lazy greedy:
first with the weights of the mandatory targets alone, then with all weights, taking each time the row that adds
the most weight not yet covered (ties by priority, then record), for `size - reserve.rows_granted` rows. Between the two
passes the cover takes the worst rows (lot S2b): the pool keeps, apart from the candidates of the targets, the
`smart.worst_rows` rows with the largest sum of the weights of the anomaly targets they cover (`quality` family, empty
cells excluded: `execute._is_anomaly`), and the selection puts up to `min(worst_rows, size // 20)` of them in the sample
whether or not their targets are covered, because a cover counts a target once and would take one such row only. The
report counts them in `selection.by_worst`, apart from `by_cover`. What is
left goes to the rows of the reserve, then to any other held row, by priority (E13: the report declares it in
`reserve.adjusted`). A target is covered once. The result is a heuristic on a bounded pool and promises no
optimum (SMART-07). The rows are written in the order of the source and the targets are not added to the CSV
file (SMART-09).

**Guard.** `select_rows` checks the plan against the Scan (`StalePlan`), the source against the recorded size
(`SourceNotReadable`, `StaleSource`) and, after the reading, the digest against the Scan's: a source that changed
leaves no output (20.6). The reader is the one of the Scan, so a tolerant error policy excludes the same records.

**Time and confirmation (`estimate.py`).** As for a second pass (20.3): the reading costs at least the parsing
share and at most the reading phase of the first pass; the work adds `SELECT_NS_PER_CELL` (600) for each cell of
a column that has a test and `SELECT_NS_PER_ROW` (2,000), scaled by the speed of the first pass; a plan with the duplicate-rows target adds `DIGEST_NS_PER_ROW` (300) and
`DIGEST_NS_PER_CELL` (25) for each cell of the row. The digests live beside the pool, so the memory the confirmation announces adds
`DIGEST_BYTES` (100) for each tracked row. It is a message
and a threshold (120 s on the upper bound), not an input of the choice, and it is not in the plan, which keeps
its identity. `tabalyst sample --sample-method smart` shows the estimate and asks when it passes the threshold;
outside a terminal it stops with exit code 3 unless `--yes` is given. A batch asks once, with the total.

**Report (`result.py`, SMART-12, SMART-13).** `tabalyst.sample` 0.2.0 revision 1 (`<stem>.sample.json`, schema in
`tabalyst/schemas`): `request`, `output`, `run` (times, memory, records and cells read, the digest verified,
`passes`), the `plan` embedded, `selection` (rows by cover and by reserve, the reserve planned and taken, the pool
and the refused rows), `coverage`, `statements` and one entry per target. The coverage is named `target_catalog`:
counts of defined, evaluable, observed and covered targets, the weighted share, the mandatory targets, the same by
family, the heaviest missed targets with their reason (`size`, `budget`, `not_observed`) and a `verification`: for
every target whose frequency the plan holds exactly, the number of rows the reading found against the plan's
count. It is the oracle of the tests: a disagreement is a defect of a test on a row. The statements say that
the coverage is that of the catalog and not of every phenomenon (SMART-13) and that the proportions of the sample
are not those of the population (E13). The plan inside it keeps its own `plan_id`.

**D23 for `stratified`.** `generate_samples(method="stratified")` asks the shared storage for a current Scan of
the source (`shared_scan_service.stored_scan`: it never scans and never writes) and, when the advice of 20.14
finds the strata of the requested columns `excessive` (a combination whose bound passes 100,000 states, or a
column of an exact count above it), stops before reading the file with the advice. An explicit `max_strata` allows
the run: a product of cardinalities is a bound and the combinations that exist can be far fewer. Without a stored
Scan nothing is advised and the runtime cap of 20.14 is what stops it.

**The page (lot 11, O45).** `sample_page.py` renders the document `tabalyst.sample` as `<stem>.sample.html` beside the
report (`--no-html`, `html=False`): the statements in words, the coverage by family and weighted, the gaps with their
reason, the verification of the exact counts, the pool and the readings. It reads the document alone, so it needs
neither the source nor the CSV file, and it adds nothing the JSON does not say.

**Not yet.** An option `--deep` on `sample`; the grouping of rows by target
(SMART-09 allows it on request).

### 20.17 What Explore consumes (lot 11, specification 19.3, EXPLORE-01 to EXPLORE-05, O45)

Explore, the interactive exploration of a file, is a consumer of this work and not part of it. This section fixes
what a Scan, a Report and a second pass give it, so that it can be built without changing them
(`tests/scan/test_explore_contract.py` keeps it true).

| Need | What gives it | Limit |
| --- | --- | --- |
| Facets (EXPLORE-01) | Per field: `values.cardinality` (exact, or limited with an estimate), `values.frequencies` (analytical, exact), `technical_type`, `numeric` and `temporal` bounds, `string_lengths` with its exact histogram, the inferred patterns (`derived.patterns`), the exact histograms and distinct counts of a current second pass | A profile does not hold every row; it says what it holds (`accuracy`, `status`, `kept` and `of`) |
| Price of an exact facet | `plan_analyses`: `summary.memory`, `common.cells`, `common.cpu`, the estimate of the time and `requires_confirmation`, from the Scan and the settings alone | The time is a guide from the first pass, not a promise |
| Rows and filters (EXPLORE-02) | The source, or a cache that Explore builds when it opens one; the identity of the source (`source.sha256`, `size_bytes`, `modified_at`) lets Explore check that the cache is the file the profile describes | Neither a Scan nor a Report requires such a cache, and Scan builds none |
| Global profile against filtered result (EXPLORE-03) | Every count names its population and domain (`domain`, `scope`, `population`); nothing in the profile is the count of a selection | A filtered count comes from a query or an analysis whose scope names the filter; the counts of the Scan are never shown as counts of the selection |
| Reuse of a second pass (EXPLORE-04) | `<stem>.deep.json` and the `analyses` member of a Report, keyed by the source, the settings and the engine (`PlanBase`); a result that matches the source and the scope is reused (`run.reused`) | A different scope (a filter) is a different analysis. A facet of patterns uses the feature and the version of its validation; a column of high cardinality is better served by a search or a range than by a list of values |
| Initial profile (EXPLORE-05) | A Report is autonomous: it carries the Scan base and the analyses, and its HTML is rendered from the JSON alone | Reading the rows still needs the source or a valid cache |
| Later analyses (lot 20) | The results `measures`, `numeric_shape`, `datetime_parts`, `residual_values`, `duplicates`, `category_stats`, `position_drift` and `missing_matrix` (lot 19), `array_profile`, `structure_variants`, `text_profile`, `fingerprint_distinct` and `sensitive_forms` (lot 18) of a forced second pass: each has a `kind` to dispatch on and an `accuracy` (`exact`, or `exact_counts` when the quantiles of a grid are estimates with certain bounds); a facet shows the distribution of the shape of the numbers, the weekday, the hour or the unit without the source | The Report prints them as insight cards (20.29); a card is derived at render time and is not part of any format. `tests/scan/test_explore_contract.py` keeps it true |

Decisions. Explore never edits a Scan, a Report or a second-pass document; it reads them, and writes its own
documents. The backend that serves the rows is its own choice and is outside this work.

### 20.18 The routes of the second pass in worker processes (lot 12, PERF-07, O46)

The second pass reads the source once in the process that asked for it, and a CSV batch gives every selected field
its column (`Router._batch`). A route (`FieldRoute`: one field, its lengths, numeric, frequency, pattern and period
accumulators, the memory of the cells it has read) depends on no other route, so it can live in another process.
`secondpass/parallel.py` does that for the routes of a CSV file with one dataset, from 16 MiB (`worker_count`, so
`--workers` applies) and with at least two routes to share:

- The process sends each worker its routes before the reading (the empty accumulators, which pickle), then one message
  for each batch with the columns of the routes the worker holds, and at the end asks for the accumulators back. A
  worker receives the columns of a route in reading order, so it counts what the process would have counted; the
  accumulator comes back and the process concludes the analysis from it (`_finish`, with the checks against the Scan)
  as it did before. A route that raises in a worker fails alone, with the name of the exception, as in the process.
- The routes are shared out by modeled cost (`route_weight`, from `NS_PER_CELL`), the heaviest first to the least
  loaded worker, the same assignment for the same routes. The result never depends on it.
- A route with an exact set stays in the process: the sets of a run draw from one pool of bytes (MEM-06), so splitting
  them would make the field that is stopped depend on the order of the workers. The pairs and tables of columns
  (20.12, 20.13) stay too: they read two columns together through feeds that several of them share.
- A JSON or Excel source is read record by record and stays in the process. Workers that cannot start leave the pass
  in one process, as for the first pass; a worker that fails during the run stops the pass with an error that names
  it (`SecondPassWorkerError`, a `TabalystError`: an automatic second pass is left out of the Report, a forced one
  fails).
- `run.workers` is the number of processes that held routes. The cost model of 20.2 counts one process, so the time
  estimate of a plan is an upper bound.

Measured on the realistic file (benchmarks.md, lot 12): the second pass of the Report takes 8.0 s instead of 22 s, and
the Report 23.3 s instead of 43 s for 15.3 s without a second pass.

### 20.19 The numbers of the values with a unit (Insight lot 14, B1, O48)

The Scan recognizes `$12.50`, `12,50 €`, `37%` and `215 Go` and counts their formats and markers, but its `numeric`
block holds only the numbers written without one (10.29 of the technical documentation: 172 of 2,000 values of a
column of amounts). `measure_extraction` reads their numbers in the second pass; the first pass is not touched (Q7).

**Applicability.** The planner reads, for each of the three detectors, its coverage and the number of markers it
counted (`MeasureFacts`). The candidate takes the detector that matched the most values (the first of `currency`,
`percentage`, `quantity` on a tie); it applies when that detector matched at least half of the content values
(`MEASURE_MIN_SHARE`, the rule of the codes of 18.13), and is `low_coverage` otherwise. Exposure keeps a withheld
field out. When every distinct value is in the samples with its exact count, the result follows from them and the
source is not read (`computed_from` `samples`), as for the patterns (20.9). Utility 60.

**Reading.** `CellReader.cells(measure=detector)` runs the detector of the Scan's configuration on the analytical text
of each distinct string of a batch, with its input cap, through the detector's `measure` method: `classify` and the
marker it read, written apart so that `classify`, on the hot path of the first pass, does not change (a test keeps the
two equal on every value of its data). The cell gets a `Measure`: the state
(`matched`, `ambiguous`, `invalid`), the number and whether it is written as a decimal (an `int` for the integer formats
of the number detector, so `integral_decimals` is the Scan's), the marker (`split` of the currency detector, `%`, the
unit), whether it comes before the number and whether a space separates them. The route remembers 16,384 strings
(`MEASURE_MEMO_ENTRIES`), as for the dates, but 1,024 for a field of the tier `measure_wide`, whose strings would not
come back (`measure_memo`); the accumulator carries the planned `cell_ns`, which weighs its route among the workers
(20.18) and is no input of the result. When every pending analysis of a source is answered by the Scan, `scan --deep`
says how many it computed from the Scan instead of claiming they were stored (`DeepJob.from_scan`). The accumulator pickles, so a route goes to a worker (20.18) like the others.

**Three levels.** A group per marker holds a `NumericAccumulator` of the first pass (its median list off) and a table
`number -> count`. The result has:

1. `overall`: the metrics of a numeric field over every parsed number, merged from the groups (`NumericAccumulator.merge`
   adds the exact sums, extremes and counts): the members of `NumericStats`, `coverage` being the share of the content
   values, `distinct`, `modes`, and a histogram, `dense_counts` when every number is an integer and the range holds at
   most 65,536 integers, else `deep.bins` linear bins between the exact minimum and maximum; quantiles exact.
2. `groups`: the same for each marker that has a number, by decreasing count then text, `max_groups` of them; `other`
   holds the rest together with the number of its markers.
3. `markers`: every marker with the values written with it (parsed and ambiguous, the population the detector counts in
   `details`), `parsed`, the share, `modes`, `dominant_share`, the rare ones (under 1%) and the layout (before or after,
   spaced or not).

`homogeneous` is false when several markers have numbers: nothing is converted, so the overall metrics add quantities
that differ and the Report reads the groups first. For percentages, `percent_range` counts the parsed values below 0,
within 0 to 100 and above 100 (manque 4).

**The grid.** The table of a group holds one entry per distinct number. When the tables of the field hold more than
`deep.measures.max_values` pairs (100,000 by default), every group goes on in bins of width `2^k`, aligned on 0
(`Grid`): the width is the smallest, not below `2^-64`, whose bins hold the range in at most `deep.bins` bins, and a
value outside doubles it until it fits, merging pairs of bins. Fitting is monotone in the width, so the width of a group
ends as the smallest that holds its whole range: it does not depend on the order of the values, nor on the moment of the
switch (tested on a file read forward and backward). The levels fold the grids of their groups into the width of their
own range, which is never finer. The counts, sums, extremes, positive and negative counts stay exact; the median of
`numeric` is `limited` (`max_values`), the histogram is `bins` with `bounds_source` `grid` (inner edges at multiples of
`2^k`, outer edges at the exact minimum and maximum) and its quantiles are estimates with certain bounds (20.7);
`distinct` and `modes` are absent. `storage` says which, `accuracy` is `exact` or `exact_counts`.

**Checks.** `parsed + ambiguous + invalid + unparsed = values`, `values` is `values.count` and the strings are the
detector's `eligible`. When the detector of the Scan tested every value (`not_tested` 0), `parsed`, `ambiguous` and
`invalid` are its `matched`, `ambiguous` and `invalid`, and the values of each marker are its `details.currencies` or the
listed `details.units`. When adaptive detection left values untested, the second pass reads them all: it finds at least
what the Scan found and at most `not_tested` more (`scan_not_tested` says how many were not tested). Any other difference
is `scan_mismatch`. With a convention proved by the column (20.28) the check counts the Scan's ambiguous values as read.

**Cost.** Measured on the executor (`measure_costs.py` of the lot, a generated file of 1 million rows with five
columns of amounts, percentages and units, one process, the reading of the cell included): 151 ns a cell for a column of
about 20 distinct values, 500 for 1,400 to 1,700, 1,235 for 9,000 (an exact table) and 4,963 for one million distinct
amounts (the grid: the detector runs on every value, 7,269 before the grid used integer shifts instead of fractions).
The cost follows the distinct values, which the Scan knows: `NS_PER_CELL` has three tiers, `measure_few` 300 ns up to
1,000 distinct values, `measure` 1,500 up to the 16,384 strings the route remembers, `measure_wide` 5,000 beyond or
when the Scan stopped counting without an estimate (`measure_tier`). The last is CPU class `high`: an automatic
choice leaves such a field out (`cpu_class`), a request or a forced pass runs it. Memory: 61 to 85 bytes an entry of the
table for an integer, 134 to 170 for a decimal (`MEASURE_ENTRY_BYTES` 200, plus 100 for the table the result merges),
3 KB a group with its grid (`MEASURE_GROUP_BYTES` 1,536 plus 80 a bin). `COST_MODEL_VERSION` is 7. On that file the
automatic plan keeps four extractions and leaves the column of one million amounts out; the forced second pass of its 33
analyses takes 21.6 s, and its results agree with an oracle parsed from the file by the formats of its generator (Porte
E1).

**Key.** The detector, `max_groups`, `max_values` and `bins` are parameters of the method, so changing one computes the
extraction again and nothing else. The domain is `analytical`.

**Not yet.** The unit as a virtual category of the tables of lot 16; the conversion of units or currencies (never
automatic); the rendering of the groups in the HTML report (lot 20: the Second pass section has a one-line summary).

### 20.20 The values that patterns and detectors leave out (Insight lot 15, B2, O49)

The Scan counts the distinct values that no pattern holds (`derived.patterns` `other` and the combinations of lengths that its
tables hold instead of patterns, `outside_patterns()`) and, for each detector, the
values it finds `invalid` or does not match, with ten examples. `residual_values` keeps the values themselves with
exact counts, for the field's `sources`: the `pattern` (state `other`) and the replayable detectors (state `invalid`
and `not_matched`).

**Applicability.** `pattern_source` (the patterns of the field are complete, have a pattern and either left a
distinct value out or were found in a sample) and `detector_sources` (a detector of `replayable()`: value scope, strings
only, that read at least half of the content values and left some invalid or unmatched; at most
`deep.residuals.max_detectors`, the one that read the most first). No source, no candidate (`relevant`). Exposure keeps a
withheld field out. The parameters are the sources (`pattern,date`), `max_listed`, `max_tracked`, `max_value_length` and
`records`. Utility 55 (60 when the Scan answers alone).

**Source or samples.** When the Scan holds every distinct value with its exact count (`samples_all`) the tables follow
from them (`computed_from` `samples`) and no record exists in them (D1 of the session): `records` is false and the
records are absent. `deep.residuals.records` makes the analysis read the source anyway; reading the source always gives
the record of the first occurrence, from 1 (the record number is `RecordBatch.start` plus the position, or
`Record.index`, handed to the route since this lot).

**Replay of a detector.** `CellReader.readings` reproduces `DetectorSet._classify` on the analytical text: a text above
the input cap is `not_tested`, one whose shape the detector rules out (`shapes`) is `not_matched` without being
classified, and the others go through `classify_many`; a state is `matched`, `ambiguous`, `invalid` (with the reason the
detector gave) or `not_matched`. The reading of a text is remembered across batches (16,384 texts per detector).

**Tables.** `_Table` keeps, per source and state, a dictionary `value -> [count, first record]`. A value enters when it
is first met while there is room (`max_tracked`), so its count is exact from then on; the occurrences of the values met
afterwards are `untracked`, and those of a value longer than `max_value_length` are `too_long`. `complete` is false then
and the accuracy `exact_counts`. `invalid` tables also count their occurrences by reason.

**Profile of the patterns.** The values are read by the reader of the hierarchy (20.9, `HierarchyReader`, lot P7): a value
is in the pattern of its family that has its lengths, a node counting for its pattern, and a value of no family, or of a
family whose lengths no pattern holds, is `other`. Each pattern of the Scan (`all_patterns()`, ids such as `f1.p1`) gets its
occurrences, one value it reads with its record, and the distinct values it reads over every occurrence, in an `ExactSet` of
the run's pool (`at_least` when the pool stopped it). The counts of the nodes are in `pattern_counts` and not repeated.
The values the inference leaves out (too long, too complex, JSON natives) are `pattern_excluded`.

**Checks.** The values of the field; for a pattern, `sum(patterns) + other + excluded = values`; for each detector the
strings are its `eligible`, and its four states are its coverage when it tested every value (`not_tested` 0), else at
least the coverage and at most `not_tested` more. Any other difference is `scan_mismatch`.

**Routes.** `FieldRoute.residuals`. A route with a profile (`uses_pool`) stays in the process, as one with an exact set
does (20.18); one without is pickled to a worker. `FieldRoute.strings(column, start)` and `string(value, record)` carry
the record to the accumulators; the workers receive `start` with each column.

**Cost.** Measured on the executor (`measure_costs.py` of the lot, a generated file of 1 million rows, one process, the
reading of the cell included): a pattern with the distinct values of its candidates 217 ns a cell for 400 distinct values,
501 for 5,000, 844 to 1,749 for one million; the replay of a detector 357 for 1,500 distinct dates, 831 for 8,000 numbers,
2,051 for 40,000 dates and 1,729 for one million numbers. `NS_PER_CELL` has three tiers by distinct values of the field,
as for 20.19 (`residual_pattern_few`, `residual_pattern`, `residual_pattern_wide`, `residual_few`, `residual`,
`residual_wide`, rounded up); a field with both pays the larger part and 30% of the others, which share the reading of the
cell (`residual_nanoseconds`). A wide replay is CPU class `high`: an automatic choice leaves it out (`cpu_class`). Memory:
86 to 95 MB measured for 1 million distinct values against a firm bound of 128 to 131 MB. Domain `mixed`: the pattern reads
original values and the detectors the analytical text.

### 20.21 The repeated values of an identifier or of a key (Insight lot 15, B6, O50)

`duplicates_report` lists the values found more than once in a column that looks like an identifier, and, on request, in a
combination of two columns.

**Applicability.** `identifier_candidate`: technical type text, integer or mixed, and at least 90% distinct values (50%
under a name that suggests an identifier, `IDENTIFIER_TOKENS`). A column the Scan proved unique (complete cardinality
equal to the values) is `already_satisfied`, reason `all_distinct`. Otherwise the method is `digest_table` with the
parameters `max_listed`, `max_tracked` and `records`. When the Scan holds every distinct value with its exact count the
repeated ones follow from it (`computed_from` `samples`, no record, as for 20.20).

**Digest table.** Every distinct value is a 128-bit BLAKE2b digest (a string `s` + its UTF-8 bytes; a JSON integer,
number or boolean its type letter and canonical text, so `7` and `"7"` are two values), mapped to `record << 1 |
repeated`. The first time a digest comes back, the value becomes repeated: `[label, occurrences, record]` goes to a
bounded table (`max_tracked`) and is counted from then on; the occurrences of the others are `untracked`. Exact:
`distinct`, `redundant = values - distinct`, `repeated.distinct`, `repeated.occurrences = redundant + repeated.distinct`.
A collision needs two values with the same 128 bits: under one in 10^20 for a billion values.

**Memory and cost.** Measured on the same file: 897 and 959 ns a cell for one million distinct identifiers (`NS_PER_CELL["duplicates"]` 1,100) and 702 to 734 ns for each cell of a combination of two columns (`duplicates_key` 1,000); 121 to 123 bytes an entry, peak included, against `DUPLICATE_ENTRY_BYTES` (110, 140, 200). The table is charged to the pool of the run's exact sets (MEM-06) every `MEASURE_STEP` values; a search the Scan answers alone has its own pool, which the plan did not charge. When the
pool cannot hold it, the search stops and the result is `duplicates_limited` (status `limited`, reason `memory_budget`,
D08): the distinct and repeated values proven so far, never a count. The plan charges
`DUPLICATE_ENTRY_BYTES` (minimum, expected, firm bound) per distinct value.

**Combination of two columns.** `DuplicatesReport` is also a `PairAnalyzer` (`per_field`): the planner asks it for the
pairs a request names (`AnalysisRequest("duplicates_report", field=, partner=)`) and never proposes one by itself
(`automatic_limit` 0, utility 0, reason `requested_only`); a column that is withheld or repeats inside a record (items of
an array) is not applicable. The row sample of the Scan holds too few rows to answer: the source is always read. Each
column has a `RawFeed` (the string where the row has a value, `None` where not), shared by the keys that use it; the
digest of a combination prefixes each part with its length, so no two combinations share a text. `columns` names the
two columns, `values` are the rows where both have a value and `incomplete` those where one has none; each column's
rows with a value are checked against the Scan's `values.count`.

**Not yet.** More than two columns; the exploration of the combinations that make a key (the planner cannot tell which
columns they are); the same digest table shared with `exact_distinct` when both are selected on a field.

### 20.22 The line and the rank of a pair, tables of a category against a value, rules a user gives (Insight lot 16, B3, O51)

**The line.** `PearsonResult` has `slope`, `intercept` and `r_squared` when the coefficient is defined: `slope = cross /
m2_first` (the least-squares line of the second column on the first over the common rows), `intercept = mean_second - slope *
mean_first`, `r_squared = r^2`. They come from the co-moments of 20.12 and cost nothing. `PearsonCorrelation.version` is 2, so a
result stored before the lot is computed again.

**The rank correlation.** `deep.pearson.rank_bins` (64; 0 turns it off; otherwise 4 to 1,024) is a parameter of the method, so it
is part of the key. Each column of a pair has its inner edges fixed before the reading (`secondpass/ranks.py`, `rank_edges`): the
quantiles of the numbers of the row sample of the Scan, else of its distinct values, else equal widths between the exact bounds
(`edges_first` and `edges_second`: `rows`, `distinct`, `range`); the Scan alone decides them, so the grid does not depend on the
order of the reading or on the machine. A number goes to bin `bisect_right(inner, x)`, so equal numbers share a bin. The
accumulator counts the common rows in a `bins x bins` grid (a list of integers, `RANK_CELL_BYTES` 40 a cell in the plan). The
coefficient of `binned_spearman` (`scanner/rankcorr.py`) is the Pearson coefficient of the centered mid-ranks of the bins, an
`estimated` figure. Bounds: let `u` be the true centered average-rank vector of a column (ties share the mean of their ranks) and
`u~` the same with every row given the mid-rank of its bin. The ranks of a bin sum to its mid-rank times its size, even with ties,
so `u - u~` is orthogonal to `u~`, and its squared norm is at most the sum over the bins of `n (n^2 - 1) / 12` (reached when no
values tie). The angle between `u` and `u~` is therefore at most `atan(sqrt(spread) / norm(u~))`; the angle between the two rank
vectors differs from the estimated one by at most the sum of the two (triangle inequality on angles), and `lower`, `upper` are
the cosines of the bounding angles, with a slack of 1e-12 for rounding. The tests check by 400 random draws with many ties that the
exact coefficient is always inside, and that a grid in which every value has its own bin gives exact bounds. A column that fits in
one bin has no rank (`single_bin_first` or `single_bin_second`), a pair with fewer than `min_pairs` common rows
`insufficient_pairs`; never 0. `bins_first` and `bins_second` count the bins that hold a row.

**Exploration.** With `rank_bins` on, `explore_pair` also scores the pair by the Spearman coefficient of the sample (average ranks,
Pearson on them, interval of Fisher with the variance of Bonett and Wright, `rank_*` members of `Exploration`). The rating of the
pair is the larger of `score` and `rank_score` (`effective_score`), so a monotone relation that is not a line is listed and can be
picked by itself; `score` keeps its meaning. A column that does not vary has no rank either (the reason stays).

**The feature `value`.** `FEATURES` is `pattern`, `length`, `prefix`, `value`. A `ValueCoder` is a `CategoryCoder` (domain
`analytical`) on the column side: its classes are the `max_classes - 1` most frequent values of the exact frequencies of the Scan,
then `other`. A column offers it when the Scan holds its complete frequencies down to that rank and it has 2 to `max_distinct`
distinct values (`feature_coder(max_distinct=)`; the second pass, standing on a plan that already checked, passes none). The
exploration reads a pair of columns that could both be a category in one direction only (`value_direction`): the column with fewer
distinct values is the row axis, the first of the document on a tie; so one phenomenon does not take two tables of the automatic
choice. A request names the other direction (`explicit_proposals` does not apply the rule). `max_classes` is a parameter of the
`value` table. `NS_PER_CELL["crosstab_value"]` is 500 (measured 117 ns a cell on the executor, `lot16/measure_costs.py`, 1 million
rows, like the other features once rounded up).

**Exceptions.** `deep.crosstab.max_exception_cells` (20 by default, 1 to 1,000) replaces the constant that bounded `exceptions.listed`;
it is a parameter of the method, so part of the key. `TableExceptions.complete` is true when every cell outside the dominant class is
listed (`cells` is their number).

**Rules a user gives.** `AnalysisRequest.rules` is a tuple of `(category label, class label)`; it needs the category, the column and
the feature of the request (`_check_requests` refuses it otherwise, and for an analyzer without features). The planner attaches the
rules of the requests that match a table to its `PairProposal` (`CategoryCrosstab._with_rules`), sorted and without repeats, and writes
them in the parameter `rules` as compact JSON, so they are part of the key; a table with other rules is another analysis. A rule is
checked at the end of the reading against the counts (`CrosstabAccumulator._check_provided`): `support` is the classified rows of the
category, `confidence` the share in the class, `exceptions` the others, `counter_examples` the cells of the category outside the class
(`ExceptionCell`, their first `examples` rows). `status` is `holds`, `violated`, `no_rows`, `unknown_category` or `unknown_class` (the
label is matched against the labels of the axes, so a class `other` can be named). No threshold applies and the rule is never proposed by
itself. The member `provided_rules` is absent when no rule was given, so a table without rules is byte-identical to before. A plan's
`objective.requested[]` has `rules`, the number of rules of the request.

**Costs.** Measured on the executor (`artifacts/lot16/measure_costs.py`, 1 million rows, one process, the reading of the cell included):
a pair of two columns of 4 decimals, all distinct, 2,340 ns a cell without the grid and 2,372 with it; four pairs that share columns
2,538 and 2,690 ns (the grid adds 30 to 150 ns a cell). The figure of lot 8a (`pearson` 1,500) was calibrated on other columns and is
below what all-distinct decimals cost, because the number detector runs on every string; it is left as it is, since it decides the
class `moderate` and so whether a Report picks the pair, until the matrix of benchmarks is replayed (lot 20). Memory: the grid is
`bins^2 * RANK_CELL_BYTES`. `COST_MODEL_VERSION` is 9 (10 since lot 16c, 20.23).

### 20.23 The numbers of a column by category (Insight lot 16c, B3, O52)

A category explains a number when the numbers of its values differ: a premium by contract type. The second pass
describes the number for each value of the category, over every row, and rates the pairs on the row sample as the
correlations (20.12) and the tables (20.13) do. `category_stats` is a directed `PairAnalyzer` (`relations: stats`,
`budget_reason: stats_budget`, no feature): the category is the `field` of the candidate, the numeric column its
`partner`, the id `category_stats:dataset:category>number`.

**Eligibility.** The category follows `category_state` and `category_coder` of 20.13 (2 to `max_distinct` distinct
values, complete frequencies down to `max_categories`, not an identifier, not near unique, not exposed, not repeated);
the number follows `column_state` of 20.12 (`integer` or `number`, complete numeric measure, varies, not an identifier,
not exposed, not repeated) and must have `explore_min_rows` numbers in the sample. When a column could be both, the
table is read in the direction of `value_direction` (20.22); a request names the other. Every exclusion is counted in
`relations.stats[]` (`excluded_categories`, `excluded_numeric`), as are the pairs `possible`, `evaluated`, `undefined`
(by reason) and `listed`, the `work` (pairs times rows) and `unavailable`.

**The ratio (`scanner/correlation_ratio.py`).** `GroupMoments` (count, mean, sum of squares about the mean, extremes) is
computed by a centered pass per batch and merged by the update of Chan et al.; `ratio` reads the groups that have a row:
`eta_squared = SSB / SST` and `epsilon_squared = (SSB - (k - 1) SSW / (N - k)) / SST`, clamped to [0, 1], `score` its
square root. The class `other` (the categories beyond `max_categories`) is counted among the rows and takes no part in
the ratio. Undefined, never 0: `too_few_rows` (fewer than `explore_min_rows`, or no more rows than groups),
`single_category`, `no_variance` (all the numbers equal). The exploration rounds to six decimals; the utility is 100
times the score (reason `exploratory_correlation_ratio`) and the planner picks by itself the pairs of 45 or more,
`automatic_stats` (8 until lot 20, then 2; 20.29) at most (`stats_budget`).

**Executor (`secondpass/stats.py`).** The category goes through the `CodeFeed` of 20.13 (key `category:<max_categories>`,
shared with the tables) and the number through the `ColumnFeed` of 20.12 (key `number`, shared with the correlations), so
a column is read once whatever the analyses that use it. `StatsAccumulator.add` groups the numbers of a batch by code
and each `_Group` sorts its numbers: the count below each inner edge gives the bins, the position of zero the signs, the
ends the extremes, a centered pass the moments, `math.fsum` the sum (kept as partial sums, folded beyond 64). The rows
without a category or a number are counted (`category_missing`, `value_missing`, `both_missing`); `rows = counted +
excluded` is checked, as are the values of each column against the Scan (`scan_mismatch` fails the analysis alone) and,
when no number was lost to the float64 conversion, the extremes of all the groups plus the numbers of the rows without a
category against the Scan's minimum and maximum.

**The bins.** `stats_edges` places the edges once per number column as `numeric_histogram` does (`place_edges` from the
Scan, `deep.bin_strategy`, `deep.stats.bins`), then keeps the inner edges as float64 values strictly between the extremes;
a number goes to bin `bisect_right(inner, x)`. The edges are the same for every category, so the histograms compare, and
they are fixed by the Scan alone, so the result does not depend on the order of the reading, the batches or the workers.
The quantiles (`QUANTILE_LEVELS`) are read by `binned_quantiles` with the exact fractions of the float edges and the
extremes of the category as bounds: estimates with certain bounds. The result `StatsResult` (`kind: category_stats`,
`accuracy: exact_counts`, `precision: float64`) holds `categories` (a `TableAxis`), `rows`, `counted`, `excluded`,
`bins` (the written edges, the strategy asked and used, `bounds_source`), `overall`, `groups` and `association`.

**Complete sample.** When the Scan holds every row of a CSV dataset and covers both columns, the pair is `requires_source:
false` and computed from the rows of the sample with the same arithmetic (`source: samples`).

**Key.** Both fields, the method and its parameters (`max_categories`, `bins`, `strategy`), not the exploration, the
budgets or the order.

**Costs.** `NS_PER_CELL["category_stats"]` is 2,000 (`moderate`), measured on the executor (`lot16/measure_stats.py`, 1 million
rows, one process): 909 to 954 ns a cell for an amount of 2 decimals, 1,431 for 4 decimals nearly all distinct, 1,758 for 3
decimals, 1,864 for three pairs that share their category, against 2,520 for a correlation in the same session. The number
detector dominates, as for the pairs; the accumulation itself costs 0.18 s a million rows. Memory: per category
`STATS_GROUP_BYTES` (1,024) plus `bins * RANK_CELL_BYTES`; the batch of floats and the codes are the states of 20.12 and 20.13
(`pearson_feed:`, `code_feed:`), charged once. `COST_MODEL_VERSION` is 10. On the combined file (1 M rows, 34 columns) the
automatic Report picks 5 pairs: its second pass goes from 8.0 s to 12.0 s in the same session (43 to 48 analyses), memory
unchanged, almost all of it the reading of the five number columns.

**Report.** One label and one summary line in the Second pass section (`report_labels.py`, `report_deep.py`); the Relationships
section does not print the pairs yet (lot 20).

**Left out.** The unit of a measure as a virtual category (20.19), a rating by ranks (Kruskal-Wallis) for skewed numbers, and exact quantiles per category.

### 20.24 The shape of the numbers of a column (Insight lot 17a, B5, O53)

A histogram says where the numbers are. `numeric_shape` (`planner/analyzers/shape.py`, `secondpass/shape.py`) says how they are
spread: lopsided or not, with outliers or not, written with how many decimals. It applies to `integer` and `number` fields and to
`mixed` ones with a complete numeric measure, with the exclusions of `numeric_histogram` (a constant column is `satisfied` by `numeric`).
Its utility is 40, below the automatic threshold (`AUTOMATIC_MIN_UTILITY`, 45): `tabalyst report` does not pick it by itself,
a request or a forced second pass does. The method is `value_table`, parameters `max_values` and `bins`.

**One reading.** The accumulator takes the numbers the route reads for the histogram (`CellReader.cells(numbers=True)`, the number
detector of the Scan's configuration, once for each distinct string of a batch), so a field with both analyses reads each cell once
(`FieldRoute.shape` next to `FieldRoute.numeric`). A JSON number is the `Decimal` of the text the reader kept. A number that Python
cannot convert (`UNCONVERTIBLE`) makes the analysis `unrepresentable`.

**Table and grid.** Each distinct number is a key of a table until `max_values` of them exist; then every count goes into a `Grid`
(20.19) of the width of the smallest power of two that holds the range in `deep.bins` bins, and the numbers that follow only widen it.
Counts, extremes, sums and places stay exact whatever the storage; `storage` says which (`table`, `grid`).

**Quartiles and Tukey.** With the table the quartiles are the exact fractions of the ranks (`exact_quantile_fractions`) and the
fences `q1 - k * iqr` and `q3 + k * iqr` (`k` 1.5 and 3) are exact; the numbers strictly below and above are counted by bisection
of the sorted keys. With the grid the quartiles are `binned_quantile_fractions` (an estimate and certain bounds, as for the
histogram); a fence is bracketed by its extreme values over the bounds of `q1` and `q3`, `(1 + k) q1 - k q3` and `(1 + k) q3 - k q1`; a bin counts as `certain` when all
of its numbers are beyond every possible fence and as `possible` when any can be beyond one. The last bin is closed on the right,
so its maximum can touch a fence (the test is strict for it). The two counts are equal with the table.

**Moments.** Skewness `m3 / m2^1.5` and excess kurtosis `m4 / m2^2 - 3` of the population, from centered sums in float64. With the
table they are computed from the table at the end; with the grid the table is centered when it is given up and the numbers that
follow are buffered (8,192 pairs) and merged by Pébay's update (`merge_moments`), so that the result depends on the batches only
by float rounding (tests compare at 1e-6 after rounding to six decimals). They are undefined, with a reason, for fewer than 3
numbers (`too_few_values`), no variance (`no_variance`) or a float64 overflow (`not_representable`).

**Places.** The number of digits after the point as the text is written, from the exponent of the `Decimal` (`12.50` has 2 and a
trailing zero, `1.5E+3` has 0, an integer 0), counted for each distinct string: `places`, `trailing_zero`, `mixed`.

**Views.** `log` places the inner edges of `deep.bins` bins at equal ratios between the bounds of the Scan (`exp` of equal steps of
the logarithm in float64; each edge is the exact fraction of its float), only when the lower bound is positive (`non_positive`
otherwise); `equal_count` is `place_edges` with the strategy `sample_quantile` whatever `deep.bin_strategy` says, with its fallback
to equal widths and its reason. Both are `BinAccumulator`s: the counts are exact over the whole source, `outside` must be 0 and
the extremes are compared with the Scan's. The edges of `equal_count` come from the samples of the Scan, so they follow the order of the rows of
the Scan (a file read backwards has another sample).

**Checks.** The numbers counted are `field.numeric.value.count`; the views check the extremes. A difference is `scan_mismatch`.

**Cost.** Measured on the executor (`lot17/measure_costs.py`, 1 million rows, one process): 106 ns a cell for 30 distinct numbers
(the histogram: 93), 2,326 for 6,000 (1,409), 3,990 to 4,317 for 150,000 to one million (2,270 to 2,393) and the same with the grid.
`NS_PER_CELL` has three tiers by distinct values, `shape_few` 300, `shape` 2,400 and `shape_wide` 2,400 (`shape_tier`, `distinct_band`). The two upper figures are the top of `moderate`, below the measure, on purpose: a class above makes a forced second pass ask (`cpu_over_automatic`) on any file with a numeric column of a few thousand different numbers, so the time estimate is low for such columns by the cost of the number detector that the histogram pays too.
Memory: the table at `MEASURE_ENTRY_BYTES` an entry (plus the sorted copy), the grid, the buffer (`SHAPE_BUFFER_BYTES`) and two views.
`COST_MODEL_VERSION` is 11. The oracle (`lot17/oracle_17.py`, 1 million rows, exact integers) finds no difference for the three
columns, with the table and with the grid.

**Left out.** Exact quantiles of a grid by refining the bin that holds the rank (a bounded third reading with a confirmation): the
table already gives them in one reading up to `max_values`; a reading from the Scan's samples when they hold every distinct value.

### 20.25 The parts of the dates (Insight lot 17b, B4, O54)

`datetime_parts` (`planner/analyzers/parts.py`, `secondpass/parts.py`) applies to the fields `temporal_distribution` applies to
(`date`, a column of datetimes, `mixed` with a complete temporal block) and to a column of times, with one temporal kind. Its utility
is 40 (asked for or forced), the method `calendar_parts`, the parameter `as_of` (`deep.datetime.as_of`, empty when
absent), part of the key.

**One reading.** `CellReader.cells(dates=True)` gives each content string the classification of the date detector of the Scan's
configuration; `FieldRoute.parts` takes it next to `FieldRoute.periods` (`add(moment, text, count)`). A date is placed by the
calendar date as written (`zone: as_written`): the offset of an aware datetime is not converted. A value of another kind than the Scan's is `unplaced`.

**Parts.** `year_months` (the months that occur, `YYYY-MM`, whatever the span: the counts per year and per month of the year are
sums of it and are not stored), `weekdays` (7, Monday is 0, every part present), `hours` (24; those that occur) for datetimes and
times. A time has `hours` only. The placement does not depend on the span of the Scan, which orders aware datetimes as instants.

**After a bound.** With `as_of` the dates whose ordinal is above its own are `after_as_of` (by calendar day, so a datetime of the day is not after).

**Ambiguity.** An `ambiguous` value is counted and never placed in the parts. `simulation` reads its analytical text with two
`DateDetector`s of the Scan's configuration but for `ambiguous_order` (`DMY`, `MDY`) and counts, for each order, the placed values, the
year-months, the days of the week and those after `as_of` (only the day and the month change between the readings). The readings of a text are remembered (16,384 texts). There is no simulation when the configuration
already gave an order, since nothing is ambiguous then.

**Invalid values.** `invalid_reasons` counts the `invalid` classifications by the reason of the detector. Their total is checked against
the date detector of the Scan (`coverage.invalid`, exactly when `not_tested` is 0, else between it and it plus `not_tested`).
This is the A4 lead of lot 13, limited to dates: `residual_values` (20.20) gives the reasons of every replayable detector.

**Checks.** `placed` is the count of the kind in `temporal.kinds`, `ambiguous` that of `temporal.ambiguous`, and `values = count + ambiguous + invalid + unplaced`.

**Empty periods.** The number of empty periods and the longest gap follow from `periods` of `temporal_distribution` (or `temporal.years`)
and are computed at render time, not stored.

**Cost.** Measured as above, with the bins of equal width that the first version had (the year-months cost less): 213 ns a cell for 730 distinct dates (`temporal_distribution`: 172), 250 for 672 ambiguous texts (165),
3,019 for 8,640 datetimes (2,772) and 3,717 for a million distinct datetimes (3,494): the date detector dominates. `NS_PER_CELL` has the
tiers `parts_few` 600, `parts` 2,400 and `parts_wide` 2,400 by distinct strings (`parts_tier`), the last two at the top of `moderate` for the reason given in 20.24. The memory is `PARTS_BYTES` and the
replay of the dates. `COST_MODEL_VERSION` is 11. The oracle on 1 million rows (year-months, weekdays, hours, after the bound,
the two readings) finds no difference.

**Left out.** Minutes and seconds, a conversion to UTC, dates in the future relative to the clock (only an explicit bound).

### 20.26 Ambiguous dates read by the evidence of the column (Insight lot 17c, O55)

The Scan counts as `ambiguous` a numeric date that both `DMY` and `MDY` read (`03/04/2020`) and, as evidence, the unambiguous
dates that only one of them reads (`details.ambiguity.evidence`, 12.6); it applies neither, unless `ambiguous_order` of the
configuration says so. **Decision O55 reverses that for the second pass** (maintainer, 2026-10-12): `inferred_order(field)`
(`planner/facts.py`) is `DMY` when some dates read day-month only and none month-day, `MDY` for the opposite, `None` with both
orders, with none, or when the configuration gave an order. Separators play no part (the evidence is by order) and dates written year
first are in neither count, so they change nothing. The first pass is not touched: its `temporal` block and its counts are as before.

**Smart by default.** The rule is automatic, deterministic (exact counts of the Scan, never time), cheap (the reading the
distribution over time already makes) and named: the plan parameter `date_order` is part of the key and the utility reason
`ambiguous_dates_read_by_evidence` says why, the result carries `resolved` (the ambiguous dates now valid) and `resolution` (`order`, `source: evidence`, the `evidence` by order)
and the Report line says "N ambiguous now valid, read as DMY (proved by M unambiguous dates)". It is explicit when it matters: `deep.datetime.infer_order`
(true) turns it off, and `ambiguous_order` wins.

**Recount.** `CellReader.cells(dates=<order>)` reads the texts with a `DateDetector` of the Scan's settings but for that
`ambiguous_order` (one per order), so the ambiguous values come back `matched` and are placed like the others; the cells are
remembered with that reading. `PeriodAccumulator` and `PartsAccumulator` take the `order`; their checks become `placed = kind count +
ambiguous of the Scan` and `ambiguous = 0`. The Scan's `years_counted` and constant-span answers leave out the ambiguous dates, so
`temporal_distribution` is not `already_satisfied` by them when an order is inferred and the source is read. `datetime_parts` has no
simulation then (nothing is ambiguous).

**Threshold.** `deep.datetime.min_evidence` (3) is the fewest dates that must prove the order (`order_of`), and none may read in the
other; `TemporalFacts` carries the two counts, the settings decide (`date_order`), and the effective order is the plan parameter, so a
change of the threshold changes the key.

**Limits.** `evidence` shows how many dates prove the order, and a column that mixes sources is only ambiguous when both orders occur. The span used to size the periods is that of the unambiguous dates. The Scan alone (`scan`
without `--deep`) still leaves these dates out.

### 20.27 Ambiguous numbers read by the evidence of the column (Insight lot 17d.2a, O56)

`1,234` is ambiguous: thousands under `dot` (1234), a decimal comma under `comma` (1.234). The number detector counts it
`ambiguous` and, as evidence, the numbers that only one convention reads (12.6); before this lot only `ambiguous_convention`
resolved it, and an unresolved one entered no statistic. **Decision O56** (maintainer, 2026-10-12, gate N, scenario B5 of the
evaluation 17d.1) reads them by the evidence of the column in the first pass, so that the `numeric` block, the Report, the smart
sample and the second pass count the same numbers.

**Rule** (`scanner/convention_rule.py`, written once). When at least `min_evidence` (3) unambiguous numbers of a field prove one
convention and none proves the other (`single_reading`, which `order_of` of the dates uses too), the ambiguous numbers are read in
it; under `comma`, the strict decimals `d.ddd` (one to three digits, a dot, three digits, such as `1.250`, which the strict rule
reads 1.25 and the comma convention 1250) are read as thousands. The proof comes from the values only, never from the configuration:
`ambiguous_convention` wins and regroups nothing. A mixed column, or one with fewer proofs, is read as before. Spaces (U+0020,
U+00A0, U+202F) prove nothing alone (`1 234` reads the same under both conventions); their decimal separator decides (`1 234,56`
proves `comma`). The threshold is absolute, with no share: the proof is pure or the column stays as it was. Settings:
`detectors.number.infer_convention` (true) and `detectors.number.min_evidence` (3) in `NumberSettings`, which `currency`,
`percentage` and `quantity` inherit; the Scan counts no number of an amount, and their reading by the second pass is 20.28.

**First pass.** The two readings of an ambiguous number are always N and N / 1000 (one to three digits, a comma, three digits), and
so are those of `d.ddd`. `add_string_measures` keeps both kinds as the integer N in a `ThousandsReadings` (count, sum, sum of
squares, extremes, negatives, multiples of 1,000, and the `(N, count)` pairs of the median in two machine arrays while the table is
complete), only when the rule can decide: both conventions enabled, no `ambiguous_convention`, `infer_convention` on. At the
finalization of the field `DetectorSet.number_convention` reads the evidence of the number detector, decides and writes
`details.ambiguity.resolution`; then `ValueMeasures.read_thousands` adds the kept numbers to the numeric accumulator exactly
(`NumericAccumulator.absorb`):
the ambiguous ones as N under `dot`, N / 1000 under `comma`, left out without a proof; `d.ddd` as N under `comma`, otherwise as
the decimal of the strict rule, so a Scan without a proof is unchanged. A released table drops the pairs and the median is
`limited` as before. Workers finalize the fields they hold: the decision is the same with any number of workers.

**Result.** `resolution` is `{"convention", "source": "evidence", "evidence", "resolved"}`; `resolved` counts the numbers read by
the evidence: the ambiguous ones and, under `comma`, the `d.ddd`. It is written only when `resolved` is at least 1, so a column
that proves a convention but has nothing to resolve keeps `null`. What describes the writing is unchanged: `coverage` (the
ambiguous numbers stay `ambiguous`, unlike a resolution by configuration), `formats` (`1.250` stays `0.0`), `candidates`, the
technical type families and the interpretations. `numeric.count` can therefore exceed `coverage.matched` of `number`.

**Later readings.** The second pass, the smart sample and the explorations of the row sample replay the first pass's reading of a
cell (PASS2-02) and never decide again. `scan_convention(field)` reads the `resolution` of the Scan (`source: evidence`) and
`CellReader.for_field(field)` gives the reader of that convention: a `NumberDetector` whose `ambiguous_convention` is that
convention and, under `comma`, `d.ddd` read as N (`for_sample` for the row sample, below). It serves the routes of the second pass (a worker receives the convention with
its route), the column feeds of the pairs and of the numbers by category, the numbers of the row sample and of the bottom-k sample
that place edges, ranks and views (`boundaries.py`), `column_floats` of the explorations, and the tests of a smart sample. No
analyzer changed: their checks against the Scan (`scan_mismatch`) hold because both sides count the same numbers. The threshold
and the switch are part of the configuration of the Scan, so changing them changes `config_sha256` in the key of every analysis.

**Cost.** One more comparison per matched string number (`format` `0.0`) and per ambiguous one; the accumulators exist only in
fields that hold such numbers. Measured against `76eb1c6` in benchmarks.md (Insight lot 17d.2a).

**Limits.** Dates stay read by the evidence in the second pass only (20.26). No proof is borrowed from another column. A column of
`d.ddd` alone (no proof) is read as decimals, as before. Numbers with a unit: 20.28.

**Stored scans.** The two settings change the configuration of every Scan, so a shared Scan of revision 3 written before them
loads with their defaults and its `config_sha256` no longer matches. `current_scan` treats a fingerprint that does not match
its configuration as a stale cache and scans again (maintainer, 2026-10-12); it raised an error before.

**Native numbers** (maintainer, 2026-10-12): a number of the source's own type (JSON, Excel) is a number already, never read in a
convention; the Scan counts it on its native path, and the evidence only reads strings. The bottom-k sample keeps the type of
each entry, so `distinct_numbers` takes a native as it is. The row sample writes every cell as text: in a field that holds native
numbers (`native_types`), its reader (`CellReader.for_sample`) does not regroup `d.ddd`, so a native `1.250` stays 1.25. A string
`1.500` in such a mixed field is then read 1.5 from the row sample while the Scan counted 1500; only the placement of bin edges
and the scores of the explorations read the row sample there, since a pair of a source that is not CSV is always read from the
source.

### 20.28 Values with a unit read by the evidence of the column (Insight lot 17d.2b, O57)

`1,250 Kg`, `1.250 Kg` and `1 250 Kg` are a number and a unit read by the grammar of the number detector (`AmountReader`), so they
are as ambiguous as the numbers of 20.27: `1,250 Kg` is ambiguous, `1.250 Kg` a strict decimal and `1 250 Kg` 1250. Their numbers
are extracted by the second pass only (20.19, Q7), so the rule is applied there, with the same module (`convention_rule`): no
accumulation joins the first pass and the Scan is not changed.

**Evidence.** Each of `currency`, `percentage` and `quantity` counts, in `details.ambiguity.evidence`, the unambiguous values that
only one convention reads, exactly over the values it tested. The plan reads it (`scan_facts`): `MeasureFacts.convention` is
`NumberRule.of(<settings of the detector in the Scan>).convention(evidence)`, so `infer_convention`, `min_evidence`, the enabled
conventions and `ambiguous_convention` (which wins) are those of the Scan's configuration. A `dot` proof is kept only when there is
something to read (the Scan counted an ambiguous value or left values untested); a `comma` proof is always kept, because it also
reads `d.ddd` as thousands, and the Scan does not count those for the amounts (its evidence leaves them out).

**Plan.** `measure_extraction` writes the parameter `number_convention` (`""`, `dot` or `comma`), which is part of the key, and
the utility reason `ambiguous_numbers_read_by_evidence`. The values the convention resolves count for the applicability and the
choice of the detector (`MeasureFacts.readable` = `matched` + `ambiguous` with a convention), so a column mostly written
ambiguously is no longer `low_coverage`. Costs are unchanged: the tiers follow the distinct values, and the reading adds one
comparison per matched value under `comma`.

**Reading.** `CellReader.measure_detector(detector, convention)` builds the detector with `ambiguous_convention` set (one per
convention, never shared), so the ambiguous values come back `matched` with their candidates; `measure_of(reading, convention)`
marks them `resolved` and, under `comma`, reads a strict `d.ddd` as thousands (`dotted_thousands`, which accepts the affixes of a
value with a unit). The convention is an attribute of `MeasureAccumulator`, so the route, a worker and `derive_from_samples` all
read the same way; the reader of the route is the one of the number detector and is not involved. A number of the source's own
type is never read here (the detector reads strings only).

**Check.** With a convention, the Scan's `ambiguous` values are parsed here and none is left: `parsed + ambiguous + invalid`
equals `matched + ambiguous(scan) + 0 + invalid`, and `resolved` is at least the Scan's `ambiguous`; the currencies and units
counts (parsed plus ambiguous) are unchanged. Without it the check is the one of 20.19. Adaptive detection keeps its tolerance.

**Result.** `resolved` counts the values read by the evidence (the ambiguous ones, and `d.ddd` under `comma`) and `resolution`
(`convention`, `source: evidence`, `evidence` of the Scan's detector) exists only when `resolved` is at least 1, as in 20.27.
`parsed` includes the resolved values; `ambiguous` is 0. The Report summary says how many were read and how many unambiguous
values prove it. `percent_range` counts the resolved percentages too.

**Limits.** The residual values (20.20) replay the Scan's own reading, so an ambiguous value stays ambiguous there. No proof is
borrowed from another detector or column: a column of quantities is proved by the `quantity` detector alone. The second pass stays
at revision 2 (same release).

### 20.29 The Report reads the later analyses (Insight lot 20, O58)

The Report printed one sentence for each result of lots 14 to 17d (the Second pass table, 18.14). Lot 20 lays the results out
with the accuracy of each figure, from the document alone (HTML-01, F01): no source, no recomputation, nothing written to any
format (the Report stays at revision 3 of its family, the second pass at revision 2).

**Cards.** `report_insights.py` turns a `complete` or `limited` result into an `InsightCard` (`report_views.py`: `facts`, `bars`,
`tables`, `notes`; never serialized). One family each: `measures` (values with a unit), `shape`, `parts`, `residuals`,
`duplicates`, `categories` (`category_stats`), and `scan` (what `report_measures.py` derives from the Scan: quartiles of the
lengths, tail of the frequencies, dominant unit, decades, empty periods; shown on the column page only). `dataset_insights` lists
the cards of a dataset by family; `ColumnView.insights` holds those of a column, a pair belonging to both of its columns. The
macro is `templates/insights.html`, shared by the Report (section 12, Insights, before the Second pass; the sections after it
move to 13 to 16) and the column pages (section 12). The Dates section also says, for the periods, how many ambiguous dates the
evidence read (`PeriodCounts.resolution`).

**Accuracy.** Every fact, distribution and table carries its own kind (`exact`, `estimated`, `sample`, `at_least`): a card can
hold exact counts beside an estimated median. `exact_counts` results (storage `grid`) have exact counts, sums and extremes and
estimated quantiles with their certain bounds (`Quantile.lower`, `upper`), and the outliers of Tukey are written as a range
(`certain` to `possible`). The moments (skewness, kurtosis) are float64 with a stated relative error. A distribution is merged
into at most 16 bars by summing consecutive bins (the counts stay exact); the weekday, the hour and the month are not merged
(a year beyond 36 months). A list of values shows 15 rows and a table of categories 25; the document holds the rest and the card
says so when it is bounded.

**Reading the evidence.** The card of the values with a unit says how many ambiguous numbers were read in which convention and by
how many unambiguous values (`NumberResolution`, 20.27, 20.28); the card of the parts of the dates does the same for the order
(`DateResolution`, 20.26) and prints the simulation of the ambiguous dates under each order, which applies nothing.

**Exposure.** The planner already leaves a field with exposure `mask` or `hide` out of the second pass; the cards check it again
at render time (a document can be edited): a hidden or masked column lists no value, only counts.

**Cost model, reviewed with the matrix (lot 20).** Measures in `benchmarks.md`, lot 20. (1) The ceiling of the upper tiers of
`numeric_shape` and `datetime_parts` (2,400 ns, the top of `moderate`, 20.24, 20.25) stays: on the realistic file a forced plan
is estimated between 61 and 239 s and takes 25 s (the model counts one process and the second pass runs in workers), so the
estimate is not low; declaring the measured costs (4,300 and 3,700 ns) puts the tier `high`, which makes `--deep` ask for a
confirmation (`cpu_over_automatic`) for a run of 25 s. `pearson` stays at 1,500 ns for the same reason (measured 2,340 to 2,690).
(2) The utility 40 of the two analyses stays, which keeps them out of an automatic Report: choosing them for the tiers `few` and
`mid` (utility 50) would add 3.0% to the second pass of the realistic file (57 analyses instead of 48, memory unchanged); the
maintainer kept 40 (2026-10-12). (3) `deep.stats.automatic_stats` goes from 8 to 2: in the same session the second pass of the
realistic file takes 10.7 s with 0 pairs, 11.8 s with 2, 15.3 s with 4 and 15.4 s with 8 (the plan only holds 5), because each pair
reads its numeric column through the number detector, which the histogram route does not share; two pairs are the strongest by
score (`type_contrat` against `montant_reclamation` and `prime_annuelle` in the demo), `--deep` still takes the 20 the plan lists.
The key of a result does not depend on the budget, so nothing is computed again. Sharing the reading of a column between routes
is the lever that would give the others back, and is left to a later lot.

**Lots 18 and 19** (JSON, long texts and sensitive fields; drift by position and missing matrix) are not part of this milestone:
they are reported after the Porte E, without any regression (nothing of lots 13 to 17d depends on them). Lot 19 was done after the Porte E was
validated (20.30 to 20.32); lot 18 is still reported (Q9, the exposure policy, is to be decided).

**Limits.** The cards are derived, so a Report written by an earlier build shows them for the results it holds, and a result that
a later build adds (a new kind) is ignored until the renderer learns it, never rebuilt from less. The Second pass table keeps its
sentences, which `result_summary` still produces for every kind.

### 20.30 A column followed by position in the file (Insight lot 19, B9, O59)

`position_drift` (`planner/analyzers/drift.py`, `secondpass/drift.py`) follows a column along the file: the totals of the Scan hide a
column that is exported differently in the last tenth, a field that stops being filled from a record on, a code that appears
late. Its utility is 40 (asked for or forced), the method `slices`, the parameters `slices` (10), `values` (0 or 1) and, with the
values, `max_listed` (`deep.drift.max_listed`), all part of the key.

**Slices.** The records are numbered in file order (a CSV row, a JSON record, an Excel row); the position of a record is its number minus one
and its slice is `p * 10 // records` (`slice_bounds`: the first position of each slice, `ceil(k * records / 10)`), so the slices
differ by one record at most and do not depend on the machine or on how the reader cuts its batches. `FieldRoute.strings` cuts a
batch of a CSV file at the end of a slice (`DriftAccumulator.segments`), so the records it counts together are of one slice, and the
counting of the other analyses of the route does not change. A JSON record carries its own number.

**Presence.** The route hands the accumulator the content values only (`CellReader.content`, the first pass's decision), and a
record has a value for the field or has none: `missing = records - values` per slice. This holds for an empty cell, a blank one, a
null marker, a JSON `null` and an absent key alike, and does not depend on `values.missing` (the definition of the Scan decides what
`missing.count` adds up, not what a value is). The sum of `values` is checked against `values.count` of the Scan, and a slice that
holds more values than records fails the result (`scan_mismatch`): a field repeated in a record (the items of an array) is left out by
the planner (`repeated_field`). The native booleans of a JSON field are values, as in the Scan (`FieldRoute.native` no longer leaves
them out when the field is followed).

**Records the Scan left out.** With a tolerant error policy a record can be excluded; the numbers of the source then have gaps and no
longer give the place of a record among the analyzed ones. The planner leaves every field out then (`records_excluded`, from
`scan.scope.records_excluded`): a wrong slice would be a wrong count. A file with fewer than 100 records is `too_few_records`.

**The values.** `followed` exists when `facts.frequencies` is complete and not truncated (the Scan lists every distinct value with its exact
count) and there are 2 to `deep.drift.max_tracked` of them. With the default `scan.limits.max_listed_frequencies` (100) that
means a column of at most 100 distinct values; a Scan that lists more lets a column of up to 1,000 be followed. The key of a value is the
one of `exact_frequencies` (native type and analytical text, `native_key`), so `007`, `7` and the integer 7 are three values. The
accumulator keeps a list of ten counters per value, up to the number of distinct values of the Scan (more fails the result), and the
table is compared with the listing of the Scan entry by entry (`scan_mismatch`). `first_slice` is the first slice with a count
and `new_values` of a slice counts the values whose first slice it is. The result lists the `max_listed` most frequent (by count, then
text, then type), `other` sums the rest by slice.

**Association.** `missing_association` is the table of presence (a row of values, a row of missing) by slice and `followed.association`
the table of every distinct value by slice, both through `scanner/crosstab.association` (20.13): Cramér's V, bias-corrected
(Bergsma), `stable` or not, with its reason when it is not defined (`single_category` for a column that misses nothing). A column is not
said to drift on a number: the card prints V and says whether the counts were low.

**Exposure.** A field whose exposure is `mask` or `hide` is left out (`sensitive_exposure`), and the card checks it again at render time.

**Cost.** Measured on the executor (1 million rows, one process, the reading of the cell included, `lot19/measure_costs.py`): 106 ns
for a column of 10 values followed, 101 for 30, 121 for 5,000 distinct strings whose presence only is followed, 136 for numbers and 200
for one million distinct identifiers. `NS_PER_CELL` has `drift_presence` 300 and `drift_values` 200, class `low`; the memory is `DRIFT_BYTES` and
`DRIFT_VALUE_BYTES` a value, and the replay of the cells when the values are followed. The routes run in the workers of 20.18
(`PARTS` has `drift`, `route_weight` adds `cell_ns`), so the document does not depend on their number (`test_results_are_the_same_in_workers_and_in_the_process`).
`COST_MODEL_VERSION` is 12.

**Left out.** A statistic of the numbers by slice (the mean, the median), the patterns or the lengths by slice, a cut by value (a date) instead of by position, and
a number of slices other than ten: a file sorted by a date is followed by position, which then stands for time.

### 20.31 The columns that miss a value together (Insight lot 19, B11, O60)

`missing_matrix` (`planner/analyzers/matrix.py`, `secondpass/matrix.py`) counts, for each pair of the columns of a dataset that lack a value, the records
where both do. The method is `bit_sets`, the parameters `columns` (the members of the matrix) and `max_listed`; utility 40, never automatic.

**Members.** `matrix_members(dataset)` (`planner/facts.py`) gives, in document order, the fields that have a value, lack one in some records
(`values.count < record_count`), are not repeated in a record and whose values exposure does not withhold. The planner and the executor
call the same function, so the matrix does not depend on which columns the plan selects, and a plan whose `columns` differs from what the Scan
gives fails (`scan_mismatch`). There is a candidate for each member when there are at least two and at most `deep.missing.max_columns` (100):
the pairs grow with the square of the members, the cap is declared (`too_many_columns`) and the columns that miss nothing do not count, so a
file of 1,000 columns with 8 that miss a value is counted.

**One counting.** The route of a field is not used: the matrix is an accumulator of the dataset that the router feeds
(`Router(matrices=)`) with the rows of a CSV batch or the records of a JSON or Excel source, so the columns are aligned. For each member and
batch `CellReader.content` gives the flags, turned into one integer with a bit per record (`bytes.translate` and `int(..., 2)`, all in C), and
the missing set is its complement in the batch; the records without a value of a column are the `bit_count` of its set and the records
without a value in two columns that of the AND of their sets, for the pairs of the columns that have a missing value in the batch. A source read
one record at a time (JSON, Excel) buffers `PAIR_FEED_ROWS` records. The matrix stays in the process that reads: it holds no route. The state is the
bit sets of one batch and a counter for each pair that overlaps (114 bytes for 4,950 pairs, declared 160).

**Result.** Each candidate gets the `MissingMatrixResult` of its column: `missing` (checked against `records - values.count`), `columns`, `partners` (the members
that lack a value in at least one of the same records), and `listed`, at most `max_listed`, in order of the share of the records that lack a value in either
column where both do (`both / (missing + partner.missing - both)`, compared as a fraction so the order is exact), then `both`, then document order. That
share is the Jaccard index of the two sets of records: it favors columns that are missing together over a column that is merely often missing. Two rare columns that overlap
once can rank high, which is why the counts are always shown beside it. The counts are exact for every pair, listed or not; a
withheld partner never appears (the Report checks it again).

**Cost.** Measured on the executor (300,000 rows, one process, `lot19/measure_costs.py`): 82 ns for a cell of 4 and of 20 columns (1.2 and 6 million cells) and 105 ns
for 100 columns (30 million cells, 4,950 pairs, 3.2 s). `NS_PER_CELL` has `matrix` 200, class `low`; the state is `matrix:<dataset>`, shared by every candidate of the dataset.

**Report.** One card for the dataset (`scope` `dataset`: the pairs, each once, from the partners every column lists) and one for each column (`scope` `column`: its
partners with their counts), see 20.32. It shows that values go missing together, not why.

**Left out.** Triples and larger groups of columns, the records with a missing value in every column of a group, a correlation of the presence of a value with the
values of another column.

### 20.32 The Report prints the drift and the columns missing together (Insight lot 19)

`report_insights.py` adds two families after `categories`: `drift` (`_drift_card`: the counts of the slices, V of the presence, the share of the missing records by slice
as bars, and for the values followed a table of their share in each slice with the others and the first appearances) and `missing` (`_matrix_card` for a column,
`_dataset_matrix_card` for the dataset). `InsightCard.scope` (`dataset`, `column`, `both`) says where a card is printed: the dataset panel (`DatasetView.insights`) or the pages of
its columns (`ColumnView.insights`); the card of the pairs has no column page and a card of one column has no place in the dataset panel, so a dataset of 100 columns does not push 100 cards of
one family in a panel limited to 25. A table whose column of codes is not the first gets a left-aligned header and a minimum width (`.ins td.ins-v`), so that it does not break a name letter by letter on a phone. A withheld column
(an edited document) has no card of the matrix and names no partner, and its values are not listed. The cards are derived at render time and no format changes.

### 20.33 The arrays and the sets of keys of JSON (Insight lot 18, B7, O62)

`array_profile` and `structure_variants` (`planner/analyzers/structure.py`, `secondpass/structure.py`) count what JSON adds to a table. The Scan has the
shortest, the longest and the total of the items of an array field (`arrays`), and for each key below an object the parents that hold it
(`presence.present`); it has no distribution of the lengths and no idea of the keys that go together.

**Arrays.** The reader gives an array an observation of type `array` whose value is its length, so `FieldRoute.array` hands the lengths to
`ArrayAccumulator`: a dictionary length to count, bounded by the Scan's range (`max_length - min_length + 1 <= deep.arrays.max_lengths`, 10,000; wider is
`array_lengths_too_wide`) and by the number of arrays. Every occurrence counts, at any depth (the items of an array of objects, an array in an array), since an
occurrence is an observation and needs no record. The result has the totals, `exact_quantiles` of the histogram (levels 5, 25, 50, 75, 95, exact) and every length. Checked
against the Scan: arrays, empty arrays, items, shortest and longest (`scan_mismatch`). Equal minimum and maximum: `already_satisfied`, `lengths_constant`.

**The root of the records.** A JSON record has no root field in the Scan, yet the keys that records have together are the first thing to know of a JSONL file. The plan names the root `$`
(`ROOT_FIELD`, `root_facts(scan)` one `FieldFacts` for each dataset whose records are all objects, `Analyzer.roots`: only an analyzer that sets it is offered the root, so no other
plan changes) and the executor stands in a `FieldResult` for it (`_root_field`, `model_construct`, id, path, display and native types only). The candidate id is
`structure_variants:<dataset>:$`, the display `$`, a request may name it (`field="$"`) and the Report puts its card in the dataset panel (`scope` `dataset`).

**Sets of keys.** `KeySets` holds, for the objects at one path, the keys the Scan named below it (the fields whose `parent` is the object field, or `None` for the root), in the order of the Scan; a set is
an integer with a bit per key, a dictionary set to count (`max_variants`, 1,000, each counted exactly from its first object: a set met when the table is full is not tracked and counts as
`untracked`, `complete` false, `distinct` a lower bound). `StructureAccumulator` is the sweep of a dataset (`Router(structures=)`, fed like the matrix, one record at a time): a dictionary from a
path to what the observation at that path does, since the observations of a record come in document order, an object starts at its own observation (`type` `object`), the observations of its keys
follow it and the next observation of the same path starts the next object (the items of an array of objects), and the sweep closes the open objects at the end of the record. One lookup of the path for each observation
serves every object of the dataset. A key the Scan never named (a source that is not the one it read) is not marked, and the counts per key fail the check. Checked against the Scan: the objects (`native_types.object`,
`record_count` for the root) and, for each key, the objects that hold it (`presence.present`).

**Left out.** `untracked_paths` (the Scan stopped naming the paths: a set could hold a key it never named), one object, no key, and `uniform_keys` (every child has `presence.absent` 0: one set, which the Scan
already says; an absent value of `absent` counts as varying). A table has no object field and no root: `root_facts` gives nothing for CSV and Excel.

**Result.** `StructureResult`: `objects`, `keys`, `always` (the keys every object has, from the counts per key, so exact even when the sets are not complete), `key_names` (cut at `max_keys`, 30), `distinct`, `complete`,
`untracked`, `listed` (at most `max_listed`, 10, by decreasing count then first appearance: each has `count`, `keys`, `absent` (the keys of `key_names` it lacks) and `absent_total`) and `other_objects`.

**Cost.** Measured on the executor (`lot18/measure_costs.py`, 300,000 records of 4, 16 and 44 fields, one process): the arrays cost what any route on JSON costs, 4,028 ns an array on 4 fields to 10,349 on 44 (a histogram of an integer: 4,814 to
8,731), because the router meets every observation of the record; `NS_PER_CELL` has `array_profile` 300. The sets of keys cost 296 to 365 ns an observation for the root and 180 to 323 for an object of a few keys, so
`structure` 400 plus `structure_field` 350 a field of the dataset, declared at the top of the class `moderate` at most (the estimate is low for a dataset of more than six fields, and the sweep is shared). The memory is
`STRUCTURE_BYTES`, the names of the keys and a set (`STRUCTURE_VARIANT_BYTES` plus a bit a key) for each tracked one. The route is in the process that reads (a JSON source is not shared out, 20.18). `COST_MODEL_VERSION` is 13.

### 20.34 Long texts (Insight lot 18, B8, O63)

`text_profile` and `fingerprint_distinct` (`planner/analyzers/texts.py`, `secondpass/texts.py`).

**Profile.** `TextAccumulator` reads the original strings of a field (`FieldRoute` takes the early branch of `_counted`: no analytical text, no memory of cells, nothing kept of a text) and adds, for each distinct string of a batch with its count, the
words (`len(str.split())`), the lines (`len(str.splitlines()) or 1`), the characters and the decimal digits (`str.translate` for ASCII, a regular expression `\d+` otherwise: Unicode category `Nd`, the set `str.isdecimal` tests). The counters are constant:
power-of-two buckets for the words and lines, tenths of the characters for the digits (11 counts), the extremes and the sums. A text field is one whose longest value reaches `deep.texts.min_length` (80) characters or whose values the Scan sampled as long
texts (`long_text_occurrences`). `texts` is checked against `strings.content`. The state is in `PARTS` (`texts`), so the routes of a CSV file run in the workers.

**Fingerprints.** `FingerprintAccumulator` counts the distinct values by the digest of `scanner/longtext.digest_of` (BLAKE2b, 128 bits, `<native type>\0` then the text in UTF-8 with surrogates kept), a dictionary of 16-byte keys to counts, in the `ExactPool` of the run (the state
of the plan is named like those of the exact sets, so the plan grants the pool its firm bound, and the route stays in the process, like an exact set). When the pool cannot hold the table the field stops: `distinct_limited` (`limited`, `memory_budget`), a lower bound. A JSON integer, number or
boolean is a value too (`native_key`), so `values` is checked against `values.count`, `distinct` against the cardinality the Scan counted or its lower bound. The accuracy is `fingerprint_based` (design 18.6): two values are one when their digests are, probability about 2^-128 for a pair.
`repeated`, `repeated_occurrences` and the `max_listed` (10) most repeated by digest and count (ties by digest), never the text. The analysis applies when a value is above 64 characters (the exact set refuses it, `not_compactable`) or the Scan sampled long texts, and is answered by the Scan when every value is distinct (`distinct` equals `values`).

**Exposure.** Both are blocked for a sensitive field, whatever `deep.sensitive`: a digest of a phone number or an address is found by brute force, and the profile would add nothing the masks do not say.

**Cost.** Measured (150,000 rows, one process): the profile 2,266 ns for texts of 230 characters, 3,136 for 260 and 7,055 for 1,000, `text_base` 400 plus `TEXT_NS_PER_CHAR` 7.0; the fingerprints 801, 1,035 and 2,241 for the same texts (550 plus 1.7 ns a character, the hash dominating, and the table growing for 150,000 distinct texts). Both are declared at the top of `moderate`
at most, so the estimate is low for texts above 300 characters. An entry of the table measured 101 bytes for a count of 1 to 3 and 133 above 256 (`FINGERPRINT_ENTRY_BYTES` 100, 130, 180). The memory of the profile is `TEXT_BYTES`, whatever the texts
(`test_text_profile_memory_does_not_grow_with_the_texts`: 1,200 texts of 55 kilobytes, a peak under 4 MB); the batch that the reader holds is the reader's, as for every analysis.

### 20.35 Sensitive columns without a value (Insight lot 18, B10, Q9, O61)

`sensitive_forms` (`planner/analyzers/forms.py`, `secondpass/forms.py`) and the opening of `exact_distinct` to a masked or hidden field. The decision and its risks are in O61; the maintainer set the whole to **off by default**: `deep.sensitive.enabled` is `false`, and then `ExactDistinct.assess` keeps `sensitive_exposure`, `SensitiveForms.relevant` is false (so no candidate appears) and the plans are what they were.

**What the Scan already holds.** For a masked field `values.cardinality` is a raw, exact count while it is complete, `frequencies` lists masks with exact counts (up to `max_listed_frequencies`), and the detectors keep `versions` of the addresses and `regions` of the numbers. The second pass adds an exact distinct count where the Scan stopped at a bound, the tail of the masks, and the classes.

**Masks.** `FormsAccumulator` counts the mask (`exposure.mask`) of the analytical text of each content string (the domain of the Scan's `frequencies`), keyed by native type and mask, tracked from the first occurrence up to `deep.sensitive.max_tracked` (10,000; the values with another mask are `untracked`, `complete` false). Checked against the Scan: `values.count`, every mask the Scan lists with its count and, when it lists them all and none is untracked, their number. The result merges the types of one mask.

**Classes.** For a field that `ip_address` or `phone` read (`FieldFacts.classified`, the first detector with matches, part of the parameters), the detector of the configuration the Scan recorded (`CellReader.replay_detector`) classifies the analytical texts, and `class_of` gives the class of a matched value from a closed list: `ip_class` (`detectors/ip.py`: version and range, the ranges written out so that the class does not follow the version of the library, a fast path for dotted addresses), `phone_class` (`detectors/phone.py`: the zone of a French number, `fr_01` to `fr_09`, and for a North American number only `nanp_geographic`, `nanp_toll_free` and `nanp_premium`). The values the detector does not read, and the native numbers, are `unclassified`, which is not suppressed (it is the Scan's `not_matched`).

**The floor.** `floored(items, min_count, max_listed)`: an item is listed when at least `min_count` (5) values take it and it is among the `max_listed` first; the others are summed up, and while that sum is above 0 and below `min_count` the least frequent listed item joins it (complementary suppression: a lone small bucket would be a figure about a few values). It applies to the masks and to the classes. The count of distinct masks and the value totals are not suppressed (the Scan says them).

**Exposure.** `hide` gets `exact_distinct` only (`hidden_exposure` for the masks). The document never holds a value: `test_no_value_of_a_sensitive_column_is_in_the_document`, with 2 workers, searches the serialized document for the values and for fragments. No count is about a position, a row or another column: every analysis that has one keeps `sensitive_exposure` (`blocked()`, `matrix_members`).

**Cost.** Measured (500,000 rows, one process): 693 to 957 ns for an email (analytical text and mask), 2,493 for an address and 3,737 for a phone number with the class (the dotted addresses took 6,591 through `ipaddress` before their own path). `forms` 1,000 and `forms_class` 2,800 declared at the top of `moderate` at most. An entry of the table measured 202 bytes for a mask of 25 characters (`FORMS_ENTRY_BYTES` 120 on top of the text). The route runs in the workers (`PARTS` `forms`). `exact_distinct` of a masked column measured 386 to 654 ns, as for any column.

**Left out.** A class for a detector other than `ip_address` and `phone`, the area code of a North American number, the region of an address, a mask of a hidden field.

### 20.36 The Report prints the lot 18 cards (Insight lot 18, O64)

`report_insights.py` adds the families `structure` (`_arrays_card`: the totals, the median and the span of the lengths and the bars of the lengths; `_structure_card`: the counts, the table of the most frequent sets with the keys each lacks), `texts` (`_texts_card`: words, lines, digits and the three bar charts; `_fingerprint_card`: the distinct count with the accuracy `fingerprint` and the table of the digests) and `forms` (`_forms_card`: the masks and the classes). `InsightKind` has `fingerprint` (`report_labels.FINGERPRINT`, `.acc-fingerprint`, `SecondPassRow.kind`), and `result_summary` has a sentence for each result. The card of the sets of keys of the records has `scope` `dataset` and no field (the root `$` has no column page);
the cards of an array or object field are printed in the dataset panel, since the columns of the report are the leaves.

**Exposure again, at render time.** A document can be edited, so `_forms_card` prints a mask only when masking it changes nothing (`mask(form) == form`: a value does not pass), a class only when it belongs to `IP_CLASSES` or `PHONE_CLASSES`, and nothing for a field whose exposure is `hide`; `_fingerprint_card` lists no digest for a hidden field. `test_a_document_edited_to_hold_a_value_is_not_printed` edits the JSON of a Report and checks it. No format changes.

### 20.37 The exact character map (lot C2)

The analyzer `character_profile` (version 1, `available`) gives the exact map of 9.2b.
It concerns every field with content strings (`facts.strings_content`) unless the Scan
lists no character (`limits.max_top_characters` 0), and `blocked` stops a field
that exposure withholds. It is already answered (`satisfied`, `map_in_samples`,
`satisfied_by` `derived/characters/<dataset>/<field>`) when the samples list every
distinct value, since the map of the Scan is then `exact`. Otherwise it reads the
original strings once, in the route of the field (`CharacterAccumulator`, the same
`CharacterCensus` as the Scan), and its result `character_profile` (`CharacterProfileResult`) has the members of `CharacterMap` with `basis` `exact`. `values` is
checked against the content strings of the Scan (`scan_mismatch` otherwise); a field
that passes the bounds of the tables is `limited` (`character_limit`) without a result.

Cost model (version 16): `NS_PER_CELL["characters"]` 350 and `CHARACTER_NS_PER_CHAR` 25 a
character, at most the top of `moderate`; memory from 16 KiB to 8 MiB. Utility 40: below
the automatic threshold, so the map is exact only when asked for or with `--deep`. The
plan parameter is `top`, the size of the lists, which the Scan's setting gives. The Report
shows the exact map in place of the Scan's when the second pass has one (`report_sections.character_view`).

### 20.38 The order of two dates (lot S3b)

`date_order` (`planner/analyzers/date_order.py`, `planner/orders.py`, `secondpass/orders.py`) counts, for a pair of date
columns of a dataset, the records where the first date is after the second. It is a `PairAnalyzer` (`relations: "orders"`,
`directed`): the first column is the one expected to come first, and its id is `date_order:dataset:first>second`. Measured
on the 100,000-row case: `date_debut` and `date_fin` have 22 broken records among 69,105 compared, and nothing in the Scan
or in the other analyses said so (the class `date_start_after_end` was kept by chance, 0 of 8 seeds at 100 rows).

**Exploration (`orders.explore_dataset`).** On the usable rows of the row sample (20.12; fewer than `explore_min_pairs` (30)
are too few), the date columns (`technical_type` `date`, one temporal kind among `date`, `datetime_naive` and
`datetime_aware`, not withheld, not repeated) are read with the date detector, the ambiguous dates in the order of the
evidence of the field (`TemporalFacts.inferred`). A pair is compared on the rows where both have a date of the same kind;
it is listed when the earlier column is on or before the later one in at least `min_share` (0.99) of them and the other
order does not hold as well. The score is that share (rounded to six decimals); the utility is that share from 0 to 100,
so the pair is chosen by itself (from 45). `max_columns` (50) and `max_work` (1,000,000, pairs times rows) bound the work,
`max_candidates` (20) the pairs written in the plan, and the block `relations.orders` (`ExploredOrders`) counts what was
left out (`mixed_kinds`, `sensitive_exposure`, `repeated_path`, `not_in_sample`, `too_few_values`, `column_budget`) and
the pairs without enough rows. A request names the earlier column first; an explicit pair is scored from the sample when it
can be and is not applicable only when a column cannot be put in order.

**Counting (`OrderAccumulator`).** One accumulator for each pair, fed by the rows of a batch (`add_rows`) or by the
records of a JSON or Excel source (`add_record`, buffered by `PAIR_FEED_ROWS`) through the channel of the matrix of missing
values (`Router.matrices`, typed `RowAccumulator`). A string is read once (`DateSide`: the cells of the reader, the order of
the evidence of the field, memo of `REPLAY_MEMO_ENTRIES`). A record is compared when both columns hold a date of the same
kind; the others are counted by the first reason that applies: `missing`, `not_a_date`, `ambiguous`, `other_kind`. The
pairs stay in the process (20.18). `records` is checked against the Scan (`scan_mismatch`); the planner leaves a pair out
when the Scan excluded records (`records_excluded`), as for the drift (20.30). The result `date_order` lists the first
`max_listed` (10) broken records in file order with their number and the two ISO dates; all counts are exact.

**Cost.** `NS_PER_CELL["date_order"]` 5,000 (4.9 microseconds a row for the pair, measured with 1, 6 and 12 pairs on the
100,000-row base: 0.49 s a pair), `COST_MODEL_VERSION` 17; the states are a counter, the result and the replay of each
column. It always reads the source.

**In `smart`.** A target `date_order` of the `quality` family for each pair whose result has `broken` > 0: base
`candidate_anomaly`, optional, exact frequency `broken`, source `second_pass`, covered by a row whose two dates are
comparable and out of order (`_OrderTests`, the same readings as the accumulator). Measured on the case: the class is kept
by 8 of 8 seeds at 100 rows, where none was. The 5 broken rows whose dates stay ambiguous are not seen.

**Left out.** A card of the Report for the order of the dates, chains (a date before a second that is before a third),
tolerance (a date allowed to be a few days late), and the comparison of dates of different kinds.

### 20.39 Typos of a category (lot S5)

`smart/near.py` finds, in the exact values of a text column, the groups of a frequent value and the rare values one edit
away from it (`Longueuuil` for `Longueuil`): the typos of a category, which no other target names because each is a value
seen once or twice (`value_rare` is one target per column). `near_groups(table)` is a pure function of a table of
`(text, rows)`: a value is frequent from `MIN_FREQUENT` (10) rows, rare up to `MAX_RARE` (2) rows and `MIN_LENGTH` (4)
characters (and at most `MAX_LENGTH` 64: a longer text is a sentence, and the index would hold a thousand copies of it), and a frequent value must have `MIN_RATIO` (10) times the rows of its neighbour. An edit is an insertion, a
deletion, a substitution or the exchange of two neighbouring characters (`one_edit`); texts that fold alike (case, accents,
spaces; `fold`) are variants and belong to `variant_groups`. A rare value joins the most frequent value within one edit (a tie
goes to the text that sorts first); candidates come from an index by deletion of one character, so the cost does not grow
with the square of the values. A group lists 20 neighbours at most, the most frequent first; groups are sorted by the rows of
their neighbours, then by the text of the frequent value, so the result does not depend on the order of the table.

**Source.** `_Builder.near_source`: the list of the Scan when it holds every value (`samples.selection` `all`, complete
cardinality, strings with exact counts), or the table `exact_frequencies` of the second pass when the list is truncated,
with at most `smart.max_exact_values` values either way. A target of the list has `source` `scan`, `evidence` `exact` and
names its entries by their `id`; one of the table has `source` `second_pass`, `origin` the analysis and names its entries by
their position. Both carry `params` `of` (the frequent value) and `entries` (the neighbours, comma separated), so the evaluator
needs no settings. A column with one mandatory target per value (`listed_whole`) has none; a column whose values have targets
from the exact table (`exact_value`, 2 each) has one more per group.

**Target.** `near_value`, family `quality`, base `near_value` (4), optional, `frequency.count` the rows of the neighbours. The
evaluator (`Evaluator._near_value`) registers the position of the target under each neighbour (`tests.exact` by original
text, `tests.analytic` by analytical text), so a row with any of them covers it; an entry that is not there makes the target
unresolved (`reference_missing`).

**Budget.** `share_near` makes the targets once every column is known: `smart.near_share` (0.08) of the rows asked for, at
most `smart.near_groups` (100) in the dataset and `smart.near_groups_per_column` (10) in one column, shared between the
columns in turn (the heaviest group of each first), none when the size is below `NEAR_MIN_MANDATORY_SHARE` (0.75) of the
mandatory targets, and only the hard limits without a size. What the limits leave out is added to `dropped` of the family
`quality` in the summary of the plan. Measured on `cases/sample-injected-errors` (12 seeds, `ville`): rows with a typo of
the sample, with the groups and without, 6.3 and 6.3 at 100 rows, 11.3 and 8.8 at 150, 13.1 and 9.7 at 200, 20.5 and 13.6 at
400; the classes kept do not fall (20.4 and 20.1 at 150). The rule of 75% comes from 100 rows, where every weight from 3 to 8
cost 0.4 to 3 classes of anomalies. The weight 4 is the smallest that gains at 150 rows (2 and 3 gain half a row); from 5 up a share of 0.10 loses `city_case_variant` on some seeds at 150.

**Left out.** Two edits, a typo that changes the length by more than one character, the neighbours of a number or a date, a
group that names the frequent value in the report, and a target per rare value.

### 20.40 The extra copies of whole rows (Unique ID lot 6, UID-012, T33)

`duplicate_rows_count` (`planner/analyzers/copies.py`, `secondpass/copies.py`, `dedup/count_only.py`) counts the rows that repeat an earlier row,
exactly, with the engine of Dedup and without writing a file. The Scan counts them too (`records.duplicates`), bounded by `limits.max_tracked_records`;
this is for the file where that count is `limited`. The contract of use is `docs/dev/report/identifier-uniqueness.md` 6.6; the decision is the ADR
`2026-10-24-dedup-count-only-for-deep`.

**Engine.** `count_extra_copies(source, csv=, limits=)` reads the CSV with `csv_records.open_records` (strict, as `analyze_dedup`), keys each row with
`canonical_key` (`full_decoded_csv_row_v1`) and counts in `MemoryRowStore`, or in `TieredRowStore` when the disk is allowed. It keeps no `RecordMarks`.
`CopyLimits` has `memory_budget_mb` (the accounted table; with the disk forbidden the count stops there, `memory_budget`), `disk_budget_mb`
(`estimate_disk_bytes` of the key bytes and distinct rows; `disk_budget`) and `max_rows` (`row_limit`). A stop leaves `extra_copies` and
`duplicate_groups` as lower bounds (the first `k` records hold at most the copies of the file), no digest, and `status` `limited`; a count to
the end has the SHA-256 of the whole file from the same reading. A file or size that changed during the reading is `source_changed`.

**Plan.** The candidate belongs to the dataset under the field `$`. `Analyzer.rows` makes the planner offer it `rows_facts(scan)`: for a CSV with one
dataset, `rows_duplicates` (the state of the Scan's count: `complete`, `limited`, `disabled`) and `row_bytes` (mean bytes of a record). `assess`: `satisfied`
(`copies_exact`) when the Scan is exact, `not_applicable` when it was set not to count or left records out, else `applicable` with the three ceilings as
parameters (part of the key of the result). The memory is the reader plus the table up to `memory_mb`; `NS_PER_CELL["rows"]` (6,000) is the nanoseconds a
record costs, measured at 2,095 in memory and 5,812 on disk (300,000 records of 6 columns), so the CPU class (that of a cell of the record, 20.42) is above the automatic limit
for a table of two columns. `COST_MODEL_VERSION` was 18 here; see 20.42.

**Execution.** Outside the router and the workers: `_count_copies` (executor) calls `count_copies`, which checks the source before (size), counts, and checks the
SHA-256 after an exact count (`StaleSource`), then the records against `record_count` and the Scan's lower bound against the count (`scan_mismatch`). The
result `DuplicateRowsResult` (`kind` `duplicate_rows`) holds `accuracy`, `identity`, `calculation_version`, the counts, `storage` and the SHA-256. The
second-pass document is revision 4.

**Report.** `identifier_uniqueness/facts.py` reads the result as the third source of `E` (`deep.duplicate_rows_count`); `report_deep.py` prints one line of it.

**Left out.** Sharing the reading with the router (decided against in lot 8, 20.42), a count per column (cahier 5.4), other formats than CSV. The automatic choice is 20.42.

### 20.41 The analytical distinct count (Unique ID lot 7, UID-013)

`analytical_distinct` (`planner/analyzers/analytical.py`, `secondpass/analytical.py`) counts the distinct analytical values of a field exactly: the
output of the enabled `nfc`, `trim` and `collapse_whitespace` stages, the domain of the Scan's `analytical_distinct(field)`. It is a separate analyzer from
`exact_distinct`, which counts the original values (21) and is read by name in `report_classification`: one id per domain keeps a count of one from being
taken for the other (T19). The decision is in the contract `docs/dev/report/identifier-uniqueness.md` 6.1.

**When.** The Scan has the analytical count only while its table lives; a released table gives `limited` for every stage. The original count does not give it
when a stage changed a value. `FieldFacts` carries `analytical_distinct` (the Scan's exact count, if any) and `analytical_changed` (an enabled analytical
stage with `changed > 0`). `assess`: `satisfied` (`distinct_exact`) when the Scan has the count, `not_applicable` for `no_values`, `sensitive_exposure`
(unless `deep.sensitive.enabled`), `long_texts_only`, `not_compactable` (as `exact_distinct`) and `stages_unchanged` (then the original count is the analytical one),
else `applicable`, method `compact_set`, parameters `key` (and `exposure`). It subclasses `ExactDistinct` for the sizes; the state key has its own prefix
(`exact_set:analytical:`) so two analyses of a field hold two sets, and the minimum is the fixed size only (the original values the Scan proved bound the
analytical count from above, not from below). Utility 40, automatic only for an identifier candidate (20.42). `NS_PER_CELL["analytical_distinct"]` is 2,000 (20.41 measured at lot 7).

**Execution.** `AnalyticalSet` (an `ExactSet`) is fed by `FieldRoute.analytical`: `Router._counted` leaves the "original values only" path for the cell path,
where `Cell.text` is the analytical text the first pass computes (`CellReader.analytical`), and adds the texts merged by value (`add_texts`), so a pool is charged once
per text. A JSON integer, number or boolean enters through `add_native` as it does in the original set: a string `"123"` and the integer `123` stay two values, as in the
Scan's stages (a changed string only merges with an unchanged string). The set shares the pool and the stop of the exact sets (`memory_budget`, a lower bound, `distinct_limited`);
it is not moved to a worker (a route with an exact set stays in the process).

**Checks.** `values` equals the Scan's count. `changed`, the occurrences whose analytical text is not the string, lies between the largest and the sum of the
Scan's counters of the enabled analytical stages (`stage.changed`, occurrences of content strings): a reading that normalizes otherwise fails with `scan_mismatch`.

**Result.** `AnalyticalDistinctCount` (`kind` `analytical_distinct`, `stages`, `values`, `distinct`, `redundant`, `unique`, `changed`), domain `analytical`; a stop is
`DistinctLimited`. The second-pass document stays at revision 4 (not published yet).

**Report.** `identifier_uniqueness/facts.py` `_distinct` orders the exact counts: the Scan, the second pass analytical (`deep_analytical_count`, same base, `complete`, same
values and stages), the second pass original. The first is `UniquenessFacts.distinct`, the others `distinct_alternatives`. The rule compares them: two usable exact counts
that differ are `evidence_conflict` with `measure: id_cardinality`; an analytical count above an exact original one (stages changed) is `inconsistent_measures`, since
normalizing only merges values. A stopped count is never `D`.

**Left out.** The criteria of the planner are 20.42; the other formats' fingerprints for long values (`fingerprint_distinct` counts the original ones), a count per
casefold or accent key.

### 20.42 The planner and the uniqueness of an identifier (Unique ID lot 8, UID-011)

The two analyses of lots 6 and 7 (`duplicate_rows_count`, `analytical_distinct`) are chosen by the planner when they settle the uniqueness of an identifier
and the budgets allow it. The decision is the ADR `2026-10-24-unique-id-planner-criteria`; the contract of use is `docs/dev/report/identifier-uniqueness.md` 6.8.

**Candidate.** `FieldFacts.uniqueness_candidate` (from the Scan alone): classification `identifier/id`, `positions_complete` (every position has a value, not under an
array), no record left out (`excluded == 0`) and two records at least. A raw `unique_id` is not a candidate (`E = 0` follows from `D = N`). The rows of a table carry
`rows_candidates` (how many columns are candidates), `rows_distinct_known` (one has the Scan's exact analytical count) and `rows_proved` (a valid Dedup report proves the copies).

**Utility.** `AUTOMATIC_IDENTIFIER_SCORE` (50, above `AUTOMATIC_MIN_UTILITY` 45) for `analytical_distinct` on a candidate (reason `identifier_uniqueness`) and for
`duplicate_rows_count` on a dataset with a candidate whose Scan count is `limited` (reason `identifier_copies`); 40 and never automatic otherwise. Memory, CPU
class and cells decide as for any analysis.

**Order and dependency.** `_decide` takes the analyses of whole rows (`Analyzer.rows`) last. `Analyzer.gives_distinct(facts)` says whether a selected analysis gives the
exact analytical distinct count of a candidate (`exact_distinct` when no stage changed a value, `analytical_distinct`); `try_select` records the datasets that have one.
An automatic `duplicate_rows_count` needs `rows_distinct_known` or such a dataset, else it is rejected `distinct_unknown`: a count of the copies without a distinct
count settles nothing. A request or a forced plan ignores the dependency.

**CPU class of the rows.** `NS_PER_CELL["rows"]` is the nanoseconds of a record, so `DuplicateRows.estimate` sets `Costs.cpu` to `cpu_class_for(rows / dataset_fields)`: the class
of the share of a cell, as the classes mean. `cell_ns` stays per record, which `estimate_time` multiplies by the records. Three columns or more is `moderate`, two columns
`high` (not automatic, and a forced run asks), one column `high`. `COST_MODEL_VERSION` is 20. The automatic count is expected to stay in memory (a table larger than estimated meets the ceilings of `deep.copies`, the disk included): the table (`records * (row_bytes + 160)`) must fit
the automatic memory (128 MiB), which the measures of the contract (12.1) put at about 500,000 records of 50 bytes.

**Proof.** `plan_analyses(..., proved_copies=frozenset(datasets))` (also `plan_second_pass`, `plan_chain`): `rows_facts(scan, proved)` marks the rows and the analyzer answers
`satisfied`, `copies_proved`, `satisfied_by: "dedup report"`. The Report computes it with `identifier_uniqueness.facts.proved_copies(scan, dedup_report, source_dir)` before it plans (explicit
option, then the colocated `<stem>.dedup.json`); a refused proof is not looked at there and stays in `evidence.rejected`.

**Cache (CACHE-02 to CACHE-05, cahier 12.5).** The key of a result holds the base of the Scan, the analyzer and its version, the dataset, the field, the method and the parameters.
`DuplicateRows.version` is `dedup.calculation.CALCULATION_VERSION` and `AnalyticalDistinct.version` its own `CALCULATION_VERSION`: a change of what the count means is a new key. The base
holds the source SHA-256 and the configuration (so the normalization stages), the parameters of the copies hold the three ceilings. `reusable_results` (executor) also keeps a
`limited` result of `DETERMINISTIC_STOP` (`duplicate_rows_count`): its ceilings are bytes and records in the key, so the same key stops at the same place. A stopped set of values is not
kept (the memory the plan granted is not in the key). A Dedup report is not part of the second-pass document; the derived object is rebuilt with the summary.

**Left out.** Sharing the reading with the router (decided against: the strict CSV reading of Dedup is not the router's), a budget of its own for the automatic count or the disk in an automatic
run (the measures of 12.1 of the contract show that, with the default Scan limit of 2,000,000 records, the count of the copies is automatic only when that limit was lowered), a count of the copies per column.

## 21. Original value domain (O32)

Bottom-k, patterns and smart sampling rest on original values, decoded but
before NFC, trim, whitespace collapse, casefold and accent removal: `00123`,
`123` and ` 123 ` are three values. The detectors, the frequency listings, the
lengths and the statistics keep the analytical value of section 10, and every
block names its domain (`original` or the versioned normalization pipeline), so
two populations are never confused (`telephone`: the original cardinality and
the diversity of the exposed shapes are different things).

Exposure applies after the calculation (12.8). A masked or hidden sample cannot
give back the originals to a process outside the scan; the document declares
that capability as missing (`kept < of`, 18.9), and the second pass reads the
source when it needs them. Since lot 2b `values.samples` and the KMV estimate
are in this domain: the table keys are raw decoded values, a string keeps its
text, other native types their canonical text. `frequencies`, lengths and
statistics keep the analytical value. Structural patterns could be computed before exposure and kept without
keeping the value; the inference of 18.12 does not do it: it reads the samples
of the finished scan, so a field that exposure masks or hides has no inferred
pattern (`not_applicable`, reason `exposure`).
