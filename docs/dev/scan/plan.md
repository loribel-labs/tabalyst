# Tabalyst Scan plan

How Tabalyst Scan is built: lots, their status, the model and effort to use,
and how work moves from one conversation to the next. The contract is
[design.md](design.md); measurements are in [benchmarks.md](benchmarks.md).

Every lot must leave the project releasable: tests and lint green, demos
regenerated, documentation consistent with what is released.

## Status

| Lot | Title | Status | Model | Effort | Branch |
| --- | --- | --- | --- | --- | --- |
| 0 | Design, contract tests, baseline benchmark | Done | Opus 5.5 | High | `scan/phase-0` |
| 1a | Engine core and CSV reader | Done | Opus 5.5 | High | `scan/phase-1` |
| 1b | JSON reader, collections and structural limits | Done | Opus 5.5 | High | `scan/phase-1` |
| 2a | Values, frequencies, limits and statistics | Done | Sonnet 5 | High | `scan/phase-2` |
| 2b | Normalization version 1 and variant groups | Next | Sonnet 5 | High | `scan/phase-2` |
| 3a | Detector framework, technical type, ported detectors | Planned | Opus 5.5 | High | `scan/phase-3` |
| 3b | Priority 1 catalogue, patterns, sensitive values | Planned | Sonnet 5 | Medium | `scan/phase-3` |
| 4 | `tabalyst scan` command, configuration layers, documentation | Planned | Sonnet 5 | Medium | `scan/phase-4` |
| 4-fr | French translation of the lot 4 documentation | Planned | Sonnet 5 | Low | `scan/phase-4` |
| 5a | Report built on Scan, parity on the demos | Planned | Opus 5.5 | High | `scan/phase-5` |
| 5b | JSON sources and new sections in the report | Planned | Opus 5.5 | Medium | `scan/phase-5` |
| 5c | Scan reuse, streaming duplicates, pandas removal | Planned | Sonnet 5 | High | `scan/phase-5` |
| 6 | Measure, set targets, optimize | Planned | Opus 5.5 | High | `scan/phase-6` |
| 7.x | Extensions, one lot each | Planned | See lot 7 | - | `scan/<topic>` |

Status values: Planned, Next, In progress, Done, Blocked. The session that
works on a lot updates this table.

### Gates

The maintainer validates before the next lot starts:

- **Gate 0**, before 1a: the Proposed decisions of the design register
  (design.md section 1) become Accepted or are amended. Passed on 2026-09-26:
  all accepted without change.
- **Gate 1**, after 1b: reader contract, paths and presence semantics. The
  items to validate are listed in the lot 1b notes.
- **Gate 3**, after 3a: detector contract and ambiguity handling.
- **Gate 4**, before releasing `tabalyst scan`.
- **Gate 5**, before removing the pandas engine in 5c.

## Why these models

- **Opus 5.5, high effort** where an error spreads to everything built later:
  the design, reader contracts and presence semantics (1a, 1b), the detector
  contract (3a), the report migration (5a) and optimization choices (6).
- **Sonnet 5** where a written contract and failing tests already define the
  work: measures (2a, 2b), catalogue detectors (3b), the command and its
  documentation (4, 4-fr) and the pandas removal (5c). If a Sonnet session
  finds that the contract itself is wrong, it stops, records the problem in
  this file and proposes an Opus session to amend the design.
- Model and effort are chosen in the app's selector before sending the first
  message of the conversation.

## Conversations

- **One conversation per lot.** Never start a second lot in the same
  conversation: a fresh session reloads `AGENTS.md`, this plan and the design,
  whereas a long conversation is eventually compacted and loses detail.
- **The repository is the memory.** Decisions go to design.md, status and next
  steps to this file, history to `docs/dev/progress.md`. Nothing needed later
  may exist only in a conversation.
- **A lot too large for one conversation** stops at a coherent point, with
  tests green and the "Notes" of the lot updated with what remains; the next
  conversation continues the same lot with the same prompt.
- **Branches and worktrees.** One branch per phase, as in the table. The app
  can open a session in a worktree on that branch. Commits, merges, tags and
  pushes happen only when the maintainer asks.
- **Parallel sessions** are allowed only where marked below, each in its own
  worktree. Everything before 3b is sequential because each lot depends on the
  previous contract.

## Session ritual

At the start:

1. Read `AGENTS.md`, this plan (the lot's section) and design.md.
2. Mark the lot In progress and add it to `ENABLED_LOTS` in
   `tests/scan/conftest.py`.
3. Propose the plan of the lot before editing anything.

At the end:

1. `.\.venv\Scripts\python.exe -m pytest` and
   `.\.venv\Scripts\python.exe -m ruff check .` pass, with the lot's contract
   tests enabled.
2. Regenerate both public demos with the commands in `examples/README.md`.
3. Update this plan (status, notes), design.md section 17 if the contract
   changed, and `docs/dev/progress.md`.
4. Run `/code-review` on the lot's changes and address the findings.
5. Propose a commit message; commit only if asked.
6. Propose the next conversation: lot, model, effort, branch and the starting
   prompt below, in the maintainer's conversation language.

## Starting prompt

```text
Tabalyst Scan, lot <ID>: <title>.
Read AGENTS.md, then docs/dev/scan/plan.md (lot <ID>) and docs/dev/scan/design.md.
Follow the session ritual of plan.md: enable lot <ID> in tests/scan/conftest.py,
propose your plan for the lot before editing, then implement until its contract
tests pass. At the end, complete the ritual and propose the next conversation.
```

## Lots

### Lot 0: design, contract tests, baseline

Done on 2026-09-26: design.md, contract tests for lots 1a to 3b (skipped until
enabled), benchmark tooling in `benchmarks/` and the baseline in
benchmarks.md.

### Lot 1a: engine core and CSV reader

- `tabalyst.scanner` package, `scan()` API, result models, `ScanConfig` with
  the complete schema of design section 15, hard caps and fingerprint.
- Paths: segments, display syntax and its parser (design section 4).
- Reader protocol and stream items; streaming CSV reader with SHA-256 computed
  while reading, strict and tolerant policies, positional identities.
- Engine, structure and presence counters, string categories, `missing`,
  `values.count`, diagnostics collector, scan status and scope.
- Done when: `tests/scan/test_scan_csv.py` passes. Reuse the CSV error
  messages of `ingestion.py` and `sampling.py` where they apply.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 1b: JSON reader, collections and structural limits

- Add `ijson` to the dependencies; verify wheels for Python 3.11 to 3.14 in CI
  (the pure-Python backend is the fallback).
- JSON reader with its own path stack; automatic and explicit collections;
  document, collection and scalar datasets; root field; arrays block.
- Structural limits: `max_fields`, `max_depth`, `max_record_observations`.
- Done when: `tests/scan/test_scan_json.py` passes. Then gate 1.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 2a: values, frequencies, limits and statistics

- Raw frequency tables keyed by native type, cardinality with proven bounds,
  global budget, long values, listings, samples, first and last values.
- String characteristics and lengths, exact numeric statistics, booleans,
  `not_applicable` measures, `measures_limited` diagnostic.
- Done when: `tests/scan/test_scan_measures.py` passes.
- Done on 2026-09-26; contract changes recorded in design section 17.

### Lot 2b: normalization version 1 and variant groups

- Stages, change counters that continue after table release, stage
  cardinalities, variant groups.
- Done when: `tests/scan/test_scan_normalization.py` passes.

### Lot 3a: detector framework, technical type, ported detectors

- Detector base class, registry, coverage, evidence, interpretations,
  isolation of failures, shape classifier.
- Execution modes: per distinct value while tables are complete, streaming with
  memoization afterwards (design section 13).
- Technical type inference ported from `analysis.py`.
- Ported and extended detectors: numbers (strict rule, then dot and comma
  decimal conventions with ambiguity), dates (current strict formats, ISO
  date-times and times, English and French month names), textual booleans,
  enumeration candidates.
- Done when: `tests/scan/test_scan_detectors.py` passes. Then gate 3.

### Lot 3b: priority 1 catalogue, patterns, sensitive values

- First, in one session: `detectors.md` (one short specification per
  detector, design section 12.9), the pattern detector and the exposure gate
  (`tests/scan/test_scan_patterns.py`).
- Then catalogue families, which may run as parallel sessions in separate
  worktrees: email and URL; phone (CA, US, FR); postal codes (CA, US ZIP);
  currency and percentage; UUID and IP addresses.
- Each detector adds its own positive, negative, variant and overlap tests.

### Lot 4: `tabalyst scan` command, configuration layers, documentation

- `tabalyst scan INPUT... [-o | -d] [--config] [--collection] [--force]`,
  default output `data.scan.json`, atomic writes (design section 16.3).
- Shared batch planning with `report` and `sample`, progress by bytes read.
- `scan` section in `tabalyst.json`, configuration layers and merge rules;
  top-level `tabalyst.scan()` and `tabalyst.generate_scans()`.
- Documentation in `docs/en/`: how-to, scan format reference and changelog,
  configuration, glossary, known limitations; README. Note the follow-up needed
  in `tabalyst-studio`. Then gate 4 and release preparation.

### Lot 4-fr: French documentation

- Translate the lot 4 pages to `docs/fr/` with the glossary. Can run in
  parallel once the English pages are merged.

### Lot 5a: report built on Scan

- Adapter from `ScanResult` to the report, profile format revision 3, parity
  tests on both demos, decision on how the report presents date ambiguity and
  evidence (design section 12.6).

### Lot 5b: JSON sources and new report sections

- `tabalyst report data.json`, sections for detectors and formats,
  normalization variants, limits and structure; browser checks at desktop and
  mobile sizes; a public JSON demo in `examples/`.

### Lot 5c: reuse, duplicates, pandas removal

- `tabalyst report --scan data.scan.json` with the staleness rule (O12).
- Duplicate records in streaming under a budget.
- Remove `ingestion.py`, the pandas parts of `analysis.py` and the pandas
  dependency after gate 5.

### Lot 6: measure, set targets, optimize

- Scan benchmarks next to the baseline, including 10 million rows, wide files,
  long strings and deep JSON; targets decided with the maintainer (O19).
- Fast paths, adaptive detection with explicit `not_tested`, mergeable states
  as preparation for parallelism.

### Lot 7: extensions

One conversation per topic, each starting with a short design addition:
catalogue waves 2 to 5 and profiles (Sonnet 5, medium); Excel, XML, database
and API readers, exact quantiles, parallel execution and plugins (Opus 5.5,
high, for their design).

## Notes

Lots record here what remains when a conversation stops before the lot is
done, and anything the next lot must know.

- Lot 0: the current report engine resolves date ambiguity from evidence in
  the same column; Scan exposes that evidence without applying it (design
  section 12.6). Lot 5a must decide how the report presents it.
- Lot 1b, for gate 1 (the maintainer validates or amends):
  - Provisional choices of lot 1a: the `name` of an items field is `"[]"` and
    of the root field `"$"`; `missing.components.absent` is `null` for items
    fields and counts as 0 in `missing.count`; a field's `parent` is `null`
    for top-level fields even when the root field is listed;
    `RecordExcluded.index` counts every record read, so indices of analyzed
    records have gaps after exclusions.
  - Decided with the maintainer during lot 1b: duplicate keys make a record
    malformed (fatal, or `duplicate_key` exclusion); a UTF-8 byte order mark
    is accepted and reported as `utf-8-sig`.
  - Lot 1b choices: JSON `element` locations are 0-based; the `max_fields`
    lower bound is `max_fields + 1`; `max_record_observations` counts emitted
    observations only; explicit collections are always listed, with
    `json_collection_not_found` when absent; `DatasetOpened.container`,
    `Record.depth_truncated` and `Notice` extend the reader contract.
  - Still open: the CSV reader keeps the default `csv.field_size_limit`
    (131,072 characters), so a longer cell is a fatal quoting error, and JSON
    strings have no length bound while reading. Recommendation: one bounded,
    configurable `limits.max_value_length` shared by CSV and JSON (fatal, or a
    `value_too_long` exclusion under the tolerant policy) rather than raising
    the process-wide `csv` limit.
- Lot 1b, for lot 2a, settled in lot 2a: a lone surrogate escape (the JSON
  text `"\ud800"`) makes the source invalid. The pure-Python backend is
  checked by the reader; the compiled backend rejects lone low surrogates and
  replaces lone high ones with `"?"`, a documented limitation (design 5.2).
- Found in lot 2a, to fix before `tabalyst scan` is released (lot 4 at the
  latest): the compiled `ijson` backend crashes the Python process
  (segmentation fault) on a JSON integer of more than 4,300 digits, Python's
  `sys.int_max_str_digits` limit; the pure-Python backend raises a parse
  error, which becomes an `InputError`. Options: report upstream, and reject
  such integers before parsing or fall back to the pure-Python backend.
- Lot 2a, for lot 2b:
  - `normalization.py` already computes the analytical value (`nfc`, `trim`,
    `collapse_whitespace`); lot 2b adds the stage counters, stage
    cardinalities and variant groups. The value tracker (`values.py`) computes
    per-value facts once per distinct value while the table is complete, then
    per occurrence through a bounded cache after release: stage change
    counters should be facts too, so they continue after release.
  - `measures_limited` looks at `values.cardinality` and `numeric`; add the
    normalization envelopes when they exist.
- Lot 2a, still open with the `max_value_length` question of gate 1: `first`
  and `last` keep whole values, even beyond `max_stored_value_length`.
- Lot 1a, for lot 6: indicative measure, not a benchmark row: 1 million rows
  of `synthetic-1m.csv` in about 13 s with 77 MB peak memory, counters only.
  Each cell creates one `Observation`; a CSV fast path is an option for lot 6.
- Lot 2a, for lot 6: indicative measure, not a benchmark row: 1 million rows
  of `synthetic-1m.csv` in about 40 s with value measures (13 s with counters
  only in lot 1a), 100,000 rows in about 4 s. Most of the time is per-distinct
  facts of high-cardinality columns (characteristics, analytical value, number
  parsing). The global budget finds the largest table by scanning the fields,
  O(fields) per release.
- Lot 1b, for lot 6: indicative measure, not a benchmark row: 200,000
  records of 25 MB of JSON (about 11 observations each) in about 2.5 s with
  about 1.3 MB of traced peak memory, compiled `ijson` backend, counters only.
