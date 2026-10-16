# Tabalyst project instructions

## Project scope

Tabalyst is a beta toolkit for understanding unfamiliar structured data. Its
current Report workflow is:

```text
CSV/JSON -> Scan -> global JSON profile -> interactive HTML report
```

Tabalyst is presented as beta until its first stable 1.0 release. The JSON
format remains experimental during beta. The Report profile starts a new
`0.2.0` format family at revision 1; Scan and Inspect also start at `0.2.0`
revision 1.
Breaking changes are allowed and migration
support is not yet required. Record format changes in the relevant changelogs.

## Source of truth

- This repository is the public source of truth for Tabalyst code and public documentation.
- Keep private strategy, personal notes, confidential data and unpublished research in `tabalyst-gb`, not here.
- The sibling `../tabalyst-gb` is the private starting point for the maintainer's
  AI requests. For work originating there, read `../tabalyst-gb/AGENTS.md` and
  `DOCS/README.md` (the five repositories) and its relevant `DOCS/` pages for
  intent and decisions. Verify product behavior
  against this public repository before changing code or public documentation.
- Do not commit secrets, credentials or real sensitive datasets.
- The sibling repository `tabalyst-studio` holds the documentation site
  (`docs.tabalyst.com`), public website (`tabalyst.com`), brand guidelines and
  DNS references. It consumes this repository: the documentation site imports
  `docs/en/` and `docs/fr/`, and the website copies
  `examples/showcase/insurance-customers/` and the demos whose `demo.json` says
  `publish.site: true`. The website
  only advertises features documented in this `README.md`. When a change affects
  the CLI, the public API, the report or the demos, mention the follow-up needed
  in `tabalyst-studio` (see its `AGENTS.md`), but do not edit it unless asked.

## Tabalyst ecosystem

- All Tabalyst Git repositories live in the parent folder `D:\GIT` (also an
  Obsidian vault). Overview: `../tabalyst-gb/DOCS/README.md` (private, in French).
- `tabalyst-gb`: starting point for managing the whole ecosystem; private, in
  French, holding personal notes and reflections, sometimes untidy.
- `tabalyst`: the only public repository today, English first, source of truth
  for the product.
- `tabalyst-studio`, `tabalyst-lab`, `tabalyst-apps`: private, in French, each
  for a specific need.
- Point to the repositories' `README.md` files rather than copying their content.

## Language

- Use English for source code, public documentation, report labels and user-facing project content.
- Conversation language may follow the user's preference.
- Keep technical names and JSON field names stable once documented.

## Architecture

- `src/tabalyst/report_profile.py`: report profile built from a Scan result,
  without file or presentation concerns.
- `src/tabalyst/models.py`: Pydantic models serialized to the experimental JSON profile.
- `src/tabalyst/report_views.py`, `report_sections.py`, `report_labels.py`: what the
  report pages read from the document (observations, limits, patterns, row sample,
  qualified counts), computed at render time, and the words they print. See
  `docs/dev/scan/design.md` 18.14. `report_relations.py` builds the Relationships
  section (tables of a category against a feature, correlations) from `analyses`.
- `src/tabalyst/report_insights.py`: the insight cards of the report (values with a unit, shape of
  the numbers, parts of the dates, values left out, repeated values, numbers by category, and the
  measures derived from the Scan), each figure with its accuracy, computed at render time from
  `analyses` alone; `templates/insights.html` is their macro, shared by the report and the column
  pages.
- `src/tabalyst/scan_reuse.py`: scan documents reused by the report, with the
  staleness rule.
- `src/tabalyst/scanner/pearson.py`: the arithmetic of the Pearson correlation
  (stable co-moments, Chan merge, Fisher interval), shared by the exploration of
  the row sample and the second pass (`docs/dev/scan/design.md` 20.12).
- `src/tabalyst/scanner/convention_rule.py`: the rule that reads ambiguous
  numbers by the evidence of their column, decided once by the first pass and
  read back by every later reading (`CellReader.for_field`); `order_of` of the
  dates shares its purity rule (`docs/dev/scan/design.md` 20.27). The values with
  a unit take their convention from the plan (`MeasureFacts.convention`,
  parameter `number_convention`; 20.28).
- `src/tabalyst/scanner/planner/`: registry of analyzers and planner of the
  second pass (`docs/dev/scan/design.md` 20.5); `src/tabalyst/plan_service.py`
  is its boundary for the CLI and the API.
  `costmodel.py` holds the calibrated sizes, budgets and CPU classes (20.2),
  `secondpass.py` the time estimate and the confirmation (20.3). `relations.py` explores the pairs of numeric columns
  on the row sample and bounds that work (20.12); `crosstabs.py` does the same for the tables of a
  category against a feature (20.13). `PairAnalyzer` (`analyzer.py`) is what both pair analyzers
  implement; `samplerows.py` and `identifiers.py` hold what the two explorations share.
  `stratification.py` and `stratmodels.py` are the advice on stratified sampling the plan can carry
  (20.14); it is not an analyzer.
- `src/tabalyst/scanner/features.py`: the classes of a category and of the features of a column
  (`pattern`, `length`, `prefix`) and the pattern classifier shared with the validation;
  `scanner/crosstab.py` the arithmetic of a table of counts (purity, Cramér's V), shared by the
  exploration and the second pass (20.13).
- `src/tabalyst/scanner/stratify.py`: the arithmetic of stratification shared by `sampling.py` and the
  advice (classic allocation, saturating product of cardinalities; 20.14).
- `src/tabalyst/scanner/smart/`: the targets and the plan of a smart sample (`SamplingPlan`: targets by
  family, monotone capped weights, sizes, reserve, candidate budget, readings of the source; 20.15). It
  reads a Scan and a current second-pass document, never the source. The selection of the rows (lot 10b,
  20.16) is in the same package: `evaluate.py` (tests on a row), `select.py` (bounded pool, greedy cover),
  `execute.py` (the guarded reading), `estimate.py` (time, confirmation), `result.py` (the report
  `tabalyst.sample`); `src/tabalyst/smart_service.py` is its boundary for the CLI and the API.
- `src/tabalyst/sample_page.py`: the web page of a smart sample, rendered from its report `tabalyst.sample`
  alone (`templates/sample.html`; `--no-html`).
- `src/tabalyst/scan_page.py`: the web page of an explicit `tabalyst scan` (the report rendered from the Scan
  alone; 16.8). Scans another command makes by itself write none.
- `src/tabalyst/source_guard.py`: checks before and after a second reading of
  a source (plan against Scan, readable source, digest at the end; 20.6).
- `src/tabalyst/scanner/secondpass/`: executor of the second pass (one reading,
  replay of the first pass's reading of a cell, exact histograms and
  quantiles, the exact distinct count of the original values and the exact
  frequencies, the patterns counted on every occurrence and the dates per
  period) and its document `<stem>.deep.json` (`docs/dev/scan/design.md`
  20.4 and 20.7 to 20.10); `src/tabalyst/deep_service.py` is its boundary for the CLI
  and the API. `secondpass/parallel.py` runs the routes of the fields of a CSV file
  in worker processes (20.18). `secondpass/drift.py` follows a field by slice of records and
  `secondpass/matrix.py` counts the records that lack a value in several columns at once (20.30, 20.31).
  `secondpass/structure.py` counts the lengths of the arrays (`ArrayAccumulator`) and the sets of keys of the
  objects and of the records (`KeySets`, swept by `StructureAccumulator`, which the `Router` feeds record by record)
  of a JSON source (20.33); `secondpass/texts.py` the words, lines and digits of long texts and their 128-bit
  fingerprints (20.34); `secondpass/forms.py` the masks and classes of a masked sensitive field without a value, with
  a floor (decision O61, 20.35). `planner/facts.root_facts` gives the root of the records, the field `$`, to the
  analyzers that set `roots`. `exact_distinct` is the one analysis that also reads a masked or hidden field.
- `src/tabalyst/report_chain.py`: the second pass inside Report (who decides,
  plan, confirmation, run, the `analyses` member; design 20.11);
  `src/tabalyst/deep_store.py` writes the second-pass document beside its Scan
  and holds `ConfirmationRequired`. `report_deep.py` is what the HTML reads of it.
- `src/tabalyst/config.py`: validated configuration and defaults.
- `src/tabalyst/service.py`: reusable analysis boundary for the CLI and future API adapters.
- `src/tabalyst/batch.py`: glob resolution, output planning, collision
  protection and atomic writes shared by the commands.
- `src/tabalyst/report_service.py`, `sampling_service.py`, `scan_service.py`:
  batch planning and execution of each command.
- `src/tabalyst/progress.py`: presentation-neutral engine progress events.
- `src/tabalyst/reporting.py`: JSON-to-HTML rendering without CSV access.
- `src/tabalyst/inspector/`: Tabalyst Inspect, built in lots (JSON kind first,
  then Excel): document models, the JSON event pass and the selection rule.
  `excel_inspect/` is the Excel kind (sheets and named tables as candidates);
  its contract is `docs/dev/inspect/excel.md`. Its contract is
  `docs/dev/inspect/design.md`; its tests in `tests/inspect/` are enabled lot by
  lot. `choices.py` holds what the command line says about collections: the
  `--collection` short forms, the commands to copy when a source is ambiguous
  and the file slugs of `report --all-collections`.
- `src/tabalyst/scanner/readers/excel_*.py`: the Excel reader, the workbook
  helpers (`excel_common.py`) and the header rule shared by Inspect and the reader
  (`excel_table.py`).
- `src/tabalyst/cli/`: thin command adapters, error presentation and terminal
  output management.
- `src/tabalyst/templates/` and `src/tabalyst/static/`: report presentation.

Read `README.md`, `docs/dev/architecture.md` and the relevant configuration or
format changelog (`docs/en/report/`, `docs/en/scan/` or `docs/en/inspect/`) before changing shared behavior.

Tabalyst Scan, the future core analysis engine (`src/tabalyst/scanner/`), is
built in lots. Before working on it, read `docs/dev/scan/design.md` (the contract).
The lot plan, status and sessions live in the private `tabalyst-gb` repository
(`IN-PROGRESS/tabalyst-scan-plan.md`). Its
contract tests in `tests/scan/` are enabled lot by lot.

## Development workflow

Use the existing patterns and keep changes focused. Preserve user changes already
present in the working tree. Use `apply_patch` for manual edits and avoid unrelated
refactors.

Every source file (`.py`, `.js`, `.cjs`, `.css` under `src/`, `tests/`,
`scripts/`) starts with the MPL-2.0 header. The benchmarks live in the private
`tabalyst-lab` (`benchmarks/`). Run
`python scripts/license_headers.py` after adding files; `tests/test_license_headers.py`
fails when a header is missing.

Never create test, benchmark or screenshot output inside the checkout (an
`artifacts/` or `pytest-*` folder there breaks Obsidian). Always use the external root
`D:\GIT.test\tabalyst\artifacts` (see `docs/dev/architecture.md`).

After Python changes:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

After report JavaScript or CSS changes, regenerate a report and run the browser
regression check described in `docs/dev/architecture.md` at desktop and mobile sizes.
After every project modification, regenerate the public demos with
`.\.venv\Scripts\python.exe examples\tools\regenerate.py --fresh` (the steps of each
demo are in its `examples/showcase/<id>/demo.json`; see `examples/README.md`). Use the
`insurance-customers` demo for browser checks.

The lists of demos and dataset users in the `examples/` READMEs are generated from the manifests
(`examples/tools/make_index.py`, run by `regenerate.py`; `--check` fails when one is stale): never edit
them by hand, add a `demo.json` or a `case.json` instead.

Progress logs and work-in-progress requests are kept in the private
`tabalyst-gb` repository (`IN-PROGRESS/`), not here; record meaningful work
there. Update
`docs/en/report/profile-changelog.md` only when the JSON structure or
semantics change. Update release notes in `docs/dev/releases/` for release
milestones.

For release preparation, also update the private release status and feature
summaries in `../tabalyst-gb/DOCS/` and note the work in its progress log.
Check the documentation and website changes in `../tabalyst-studio` against
the public README and released tag. Keep prepared, committed, tagged and
published states distinct in all three repositories.

## Code documentation

These rules apply to code written or modified from now on. Do not mass-fix
existing code to comply; fix what a change touches.

**Types**

- Every function, method and class attribute has complete type annotations
  (parameters and return).
- No `Any` unless a comment justifies it.
- The code must pass `mypy` (or `pyright`) with no new error.

**Docstrings**

- Required for modules, classes and public functions (no `_` prefix). Optional
  for private functions unless their behavior is not obvious.
- Format: a one-line summary, then only what the signature does not tell:
  side effects, raised exceptions, assumptions about the data, edge cases.
- Do not repeat types or describe parameters whose name and type are enough.
- Every module starts with a docstring of one to three lines describing its
  responsibility (after the license header).

**Comments**

- A comment explains why, never what: a business constraint, a workaround, a
  performance decision, a trap not to "fix".
- No comment that paraphrases the code.
- Never delete a "why" comment without understanding its reason; when in doubt,
  ask.

**Synchronization**

- Any change of signature or behavior updates the related docstring and
  comments in the same change.
- A docstring or comment that became wrong is fixed or removed, never left in
  place.

**Tests as documentation**

- Every new public behavior comes with at least one test.
- Test names describe the expected behavior, in English (for example
  `test_returns_mixed_when_no_majority_type`).
- Before considering a task done: run the tests, the lint and the type check.

**Architecture decisions**

- Structuring decisions are recorded in `docs/dev/adr/` (one short file per
  decision: context, decision, consequences). It is maintainer documentation,
  never published.
- Read the existing ADRs before proposing an architecture change; do not
  reverse a recorded decision without saying so explicitly.

## Documentation

`docs/` holds the sources of the public documentation site (docs.tabalyst.com,
built by `tabalyst-studio` from the latest release tag) and the maintainer
documentation. See `docs/README.md`.

- `docs/en/`: user documentation, published, organized by tool:
  `get-started/`, `report/`, `inspect/`, `scan/`, `sample/`, `reference/` and
  `about/`. Every section has an `index.md`: the menu opens it when its title is
  clicked. URLs follow the pattern `/tool/subject/` with short, stable slugs;
  titles can be long. The sidebar order is set in `tabalyst-studio`
  (`src/navigation.ts`); add a new page there too.
- `docs/fr/`: a single page, the French translation of the Overview, whose links
  lead to the English pages. Tabalyst documents in English only during the
  beta; keep this page in sync with `docs/en/index.md` and do not translate
  other pages.
- `docs/dev/`: maintainer documentation, never published.

Writing rules for `docs/en/`:

1. English is the only documentation language during the beta.
2. Never translate commands, CLI options, JSON keys, module names, file paths or
   product names.
3. "Tabalyst" is always one word with a capital T only. "Tabalyst" is the
   toolkit; "Tabalyst Report" is a tool included in it; users always install
   Tabalyst, never "Tabalyst Report".
4. Every page is self-contained: an AI may retrieve a single page or section.
5. Put the essentials first on each page (what it does, command, result), then
   details.
6. No essential content in images or JavaScript-only components. Prefer plain
   `.md` over `.mdx`.
7. Only document what is available in the latest release published on PyPI.
   Document a feature in the same change that implements it, so the docs ship
   with the release.
8. Slugs are in English. Link pages with relative `.md` paths.
9. Use the terms of `docs/en/reference/glossary.md`.
10. Pages start with a `title` and `description` frontmatter and have no `# H1`.
    The `description` is one sentence that says what the page answers: it feeds
    `llms.txt` and search results.
11. Code blocks never need a sideways scroll when it can be avoided, and the
    care depends on what the block is:
    - **Output** (what a command prints, an error, a diagram): tag it `text`.
      The documentation site wraps `text` blocks, so a long line is fine; show the
      output as it is, verbatim, and do not wrap it by hand. A diagram must fit in
      80 characters, since wrapping would break it.
    - **Code to copy** (`console`, `python`, `json`): it is copied as written, so
      never break a command with a line continuation (it differs between shells)
      and never wrap it. Keep lines at 70 characters or less when that costs
      nothing: shorter file names, the short form of an option
      (`--collection Costs`), one argument per line inside the parentheses of
      Python, indentation in JSON. A line that cannot be cut, such as a hash or
      one JSON Lines record, stays as it is and the block scrolls. Abbreviate a
      hash in an example (`"sha256": "ece53017..."`).
    - Check a page at desktop width after editing: output must not scroll.

When a user-facing behavior changes, update the matching page in `docs/en/`.
The contents of `docs/en/` and `docs/fr/` are licensed under CC BY 4.0
(`docs/LICENSE`); the code stays MPL-2.0.

## Design rules

**Smart by default, explicit when costly.** Applies to every command, API and
future tool.

- An automatic mode (for example the deep pass chosen by `tabalyst report`)
  runs an extra operation only when its benefit is established and its cost is
  low. The decision uses deterministic budgets (memory in bytes, cells to
  process, number of columns), never measured wall-clock time, so the same file
  gives the same result on any machine. Estimated time only feeds messages and
  warnings.
- Forcing an operation (`--deep`) whose estimated cost passes the thresholds
  (several minutes, or memory beyond the budget) shows the estimate and asks the
  user to confirm before starting. A batch asks once, with the total.
- Outside an interactive terminal (script, pipe, CI) never ask: stop with an exit
  code and a message unless `--yes` is given. `--force` keeps its meaning
  (overwrite an existing output).
- The Python API never prompts: it returns the plan with `requires_confirmation`
  and the estimate, and executes only with an explicit parameter.
- Never run a long operation silently. An automatic operation is named in the
  progress output and in the result, with what it added or skipped and why.
- `tabalyst scan` is never automatic: it stays the fast first pass. Only
  `--deep` forces the deeper pass there.

## Versioning

- Application versions use PEP 440, for example `0.1.0a1`.
- Git release tags use the matching `v` prefix, for example `v0.1.0a1`.
- The Report JSON profile, Scan document and Inspect file each use
  `format_version: "0.2.0"` and their own monotonic `format_revision`.
- `executions.json` has its own `schema_version`.

Never create a commit, tag, push or release unless the user explicitly requests it.
