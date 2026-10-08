# Scan and JSON work: mapping

Reference table of the Scan and JSON work (lot 0, 2026-10-06). It compares the
requirements of the specification with the code at commit `0acf126` (Tabalyst
0.6.2 published, Scan format 0.2.0 revision 2 not yet published). Identifiers
`Dxx`, `BK`, `PERF` and the others are those of the specification; the
decisions that settle them are `O26` to `O33` in [design.md](design.md). The
lot plan itself is kept privately; the lot names below are the ones the
contract tests use (`tests/scan/test_contract_*.py`).

Status: **Done** (exists, kept), **Modify** (exists, changes), **Add** (new).

## Requirements, code today and lots

| Requirement | Today | Status | Lot |
| --- | --- | --- | --- |
| First pass fast and bounded in memory (D01, PERF-05) | Bounded tables, global value and record budgets, batches, workers (design 11, 13) | Done, guarded by the baselines | all |
| Exact counts, presence, lengths histogram, numeric statistics | Exact, no Welford (design 9.1 to 9.5) | Done | |
| Four rates and their denominators (A03) | `report_profile.py`, now documented in design 9.11 and pinned by tests | Done | 0 |
| Run instrumentation (PERF-01) | `run`: `started_at`, `duration_seconds`, `timings` (`reading`, `analysis`, `finalize`, `other`), `workers`, `peak_memory_bytes` | Modify: add planning, second pass, serialization, render | 6a, 7a, 5 |
| Diagnostic counters of the sampler (PERF-02, PERF-03) | Done at 2c: `BottomKSampler.counters`, `LongTextSampler.hashed_texts` and `hashed_bytes`, written in `run.counters.sampling` only on request (`scan(counters=True)`, `tabalyst scan --counters`); a counter that is not measured is not written | Done | 2c |
| Cardinality envelope (5.7) | `values.cardinality`: `status`, `value`, `reason`, `limit`, `lower_bound` | Modify: `domain`, `accuracy`, thresholds, `upper_bound` (Done at 1a); `estimate` (Done at 2b: KMV, held within the certain bounds) | 1a, 2b |
| Tracking limit T and sample size K separate (O28) | `max_distinct_per_field` 100,000 (kept as T); `max_samples` 100 becomes K, default 10,000 (Done at 1a, cap 100,000, K at most T) | Modify | 1a |
| JSON Schema of the base and validator of invariants (20.3, A01) | None | Done at 1a: `scanner/schema.py`, `scanner/validation.py`, committed `schemas/tabalyst.scan.schema.json` (design 19.7) | 1a |
| Bottom-k of distinct values (D04, D05, BK) | Done at 2b: `values.samples` is `all` or `bottom_k` (`k`, `hash`, `threshold`; entries with `id`, `count_accuracy`, `identity_accuracy`); `uniform_distinct` and `first_seen` removed. State in `ValueProcessor` (`scanner/valuesample.py`, design 18.3) | Done | 2a, 2b |
| KMV estimate (7.3) | None | Add: `kmv_estimate` and `BottomKSampler.kmv()` Done at 2a; Done at 2b: published in `values.cardinality.estimate` | 2a, 2b |
| Original domain (D25, O32) | Samples and the estimate use the original value (Done at 2b, A18); frequency listings, lengths and statistics keep the analytical value (Q5) | Done at 4a: patterns are inferred from the original samples | 2b, 4a |
| Long texts (D06, LONG-01 to LONG-05) | Done at 2c: a value above `max_stored_value_length` still releases the table (`value_too_long`) and goes to a small bottom-k with preview, lengths, truncation flag and digest identity (`scanner/longtext.py`, `values.samples.long_texts`, design 18.6); the estimate adds the values and the long texts | Done | 2c |
| Global memory budget (MEM-01 to MEM-06) | Done at 2c: `max_tracked_values` and `max_tracked_records` stay; the samples have a budget in bytes with sub-budgets (`scanner/memory.py`, `limits.max_sample_memory`), requested and effective sizes in the document, batches bounded by size (design 18.10, 13) | Done | 2c |
| Samples by length (D07, LEN-01 to LEN-06) | Exact length histogram | Done at 3a: `scanner/lengthsample.py` (`LengthStrataSampler`), `values.samples.by_length` with ids shared with the sample and a pool, `other`, `partial` accuracy for a late stratum, sub-budget of an eighth, limits `max_samples_per_length` and `max_length_strata` (design 18.7, 18.9, 18.10); histogram Done | Done | 3a |
| Row sample start, middle, end (D12, ROW-01 to ROW-11) | `records.preview`: first rows only | Done at 3b: `scanner/rowsample.py` (`RowSampler`, `RowPriority`), `records.sample` with first rows, a bottom-k of the interior by a priority of the position, last rows, projected cells of the same row, `interior_rows` scope, byte budget `records.sample.max_bytes`, the Report keeps the header only (design 18.11); `records.preview` stays for the Report page until lot 5 | Done | 3b |
| Pattern inference (D08) | Declarative patterns and shape signatures as detectors | Done at 4a: `scanner/patterninfer.py`, `derived.patterns` (grammar 1, candidates, exclusive classification, overlaps, exclusions), settings `scan.pattern_inference`, `run.timings.derived`; the Report carries `derived` (design 18.12) | 4a |
| Exhaustive pattern validation (D08) | None | Add | 7c |
| Observations, quality, limits (section 16) | Report issues only; scan has diagnostics | Add shared blocks | 4b |
| Adaptive normalization (16.1) | Stage cardinalities derived from the raw table | Modify: no false exhaustiveness | 4b |
| Report as a superset of the Scan (D18, D20, D21, O29) | Done at 1b: `tabalyst.report` document, the Scan base at its paths plus the `report` block; copies of facts removed (the pages read them through views until 1c) | Done (1b), pages on the base (1c) | 1b, 1c |
| Common loader (A02, A11) | Done at 1b: `scan_document.load_document` and `load_base` read a Scan or a Report (`scan_reuse.load_scan` still reads Scan documents) | Done | 1b |
| Reduced Report samples (O27) | Done at 1b: `values.samples` has `kept` and `of`; the Report keeps the 100 values it uses | Done at 1c: `report.value_examples.kept_per_column` (design 19.4b) | 1b, 1c, 5 |
| Cache identity (CACHE) | Source SHA-256, configuration hash, engine version (`scanner/identity.py`) | Done, extended for the second pass | 7a |
| Planner (D11) | None | Add | 6a, 6b |
| Second pass, histograms, medians (D02, D09, D10, D22) | None | Add | 7a |
| Exact distinct of short identifiers (D03) | Exact only up to the tracking limit | Add | 7b |
| Relationships (D13, D14) | None | Add | 8a, 8b |
| Stratification help (D16, D17) and smart sampling (D15) | `tabalyst sample` modes only | Add | 9, 10a, 10b |
| Explore access (D24) | Private DuckDB layer `projects/` | Adapted (1d): reads the Scan base only | 1d |
| HTML from JSON alone (D19, F01) | `render_report` reads the profile | Modify with the new sections | 1c, 5 |
| Atomic writes (5.4, F05) | `write_text_atomic` | Done | |
| Exposure after calculation (VAL-06) | `mask`, `hide`, `show` gate at finalization | Done, extended to samples at 2b: `kept < of` declares withheld originals, no threshold for a sensitive field | 2b |
| Large integers in the HTML (F06, Q6) | Not decided | Decide before stability | 5 |

## Instrumentation names

The specification names (PERF-01) against the fields available today:

| Specification | Today |
| --- | --- |
| `total_seconds` | Not recorded by the scan; the command total is measured by the baseline script |
| `pass1_seconds` | `run.duration_seconds` |
| `read_parse_seconds` | `run.timings.reading` (hashing included) |
| `scan_core_seconds`, `detectors_seconds` | Together in `run.timings.analysis`; with workers it is the time the main process spends on it, waiting included |
| `post_processing_seconds` | `run.timings.finalize` |
| `planning_seconds`, `pass2_seconds` | Later lots |
| `serialization_seconds`, `render_seconds` | Not recorded in the document, which cannot know its own write time; the command summary reports them |

`timings` parts add up to `duration_seconds`; they are wall-clock seconds of
the main process and are never summed with worker time.

## Consumers of the Scan model

| Consumer | Reads | Concern for the work |
| --- | --- | --- |
| `scanner/` (engine, values, measures, workers, records, structure) | Builds the models | Hot path: guarded by the baselines |
| `report_profile.py`, `models.py` (profile) | `ScanResult` fields | Copies of facts to remove (1b, 1c); the rates keep their meaning |
| `templates/report.html`, `templates/column.html`, `static/` | Profile fields, including `scan_details`, `string_profile`, `date_profile`, `numeric` | Done at 1c: the pages read the base through `report_views` (`ColumnView.field`); HTML identical to 1b; browser check at desktop and mobile |
| `reporting.py`, `service.py` | Profile and `ScanResult` | Common loader (1b) |
| `scan_reuse.py`, `shared_scan_service.py`, `scan_service.py` | Scan documents, identity, staleness | Revision refusal kept (A06); loader and second pass identity |
| `inspector/resolution.py` | Configuration resolved for JSON sources | Unchanged |
| `projects/` (`_codec`, `_validation`, `_queries`, `_generation`, `_publication`, `_staging`, `_session`) | Models, invariants, codecs | Adapted (1d): `validate_database` runs `check_scan`; no codec or schema change |
| `sampling.py`, `sampling_service.py` | Scan for `stratified` and later `smart` | Chain with the planner (9, 10a) |
| `cli/scan.py`, `cli/` | Options, output | `--deep`, `--plan`, `--yes` (6b, 7a) |
| `examples/output/`, copies for the site | Report JSON and HTML | Regenerate each lot; follow-up in `tabalyst-studio` |
| `tests/scan/`, `tests/test_reporting.py`, `tests/browser/report.cjs` | Everything above | Contract tests gated by lot |

## Ambiguities resolved in lot 0

- The r2 work is committed (`0acf126`), not only staged.
- Release 0.6.2 is published (PyPI and tag `v0.6.2` on `7add824`). Revision 2
  of the Scan format is unpublished; the Report profile is still at revision 1.
- The `execution` block of the specification is the `run` block (O33).
- The specification calls the Report a superset of the Scan; with reduced
  samples (O27) it stays autonomous for rendering but is not a valid input to
  replan.
- "Read-only" baseline: the `csv-read` floor (PERF-04) and `report --scan`
  from a Scan document, which touches no source.
- T (`max_distinct_per_field`, 100,000, unchanged) and K (`max_samples`, 10,000) are separate settings (O28, amended 2026-10-07).
