# Generate package contract: Computer, CRM, and Insurance

This is the accepted design contract for the Generate package format. Computer,
CRM and Insurance now use it in the development checkout. The published 0.6.2
release still reads `definition_version: 1`; this document does not describe a
released format. See [`design.md`](design.md) for the historical v1 contract.
The development CLI and API reject v1 definitions after the Insurance migration.

## Run the development packages

Install this checkout in an isolated environment. CRM, Insurance, and Computer
have one package each under `src/tabalyst/generate_examples/`. Select them with
`--example crm`, `--example insurance`, or `--example computer`. A custom
package can still be passed as a directory or its `dataset.yaml`. Keep the
output directory outside the source package.

```console
tabalyst generate --example computer --validate-only
tabalyst generate --example computer -d OUTPUT_DIR/clean --rows 10000 --seed 42 --output-profile extended
tabalyst generate --example computer -d OUTPUT_DIR/dirty --rows 10000 --seed 42 --anomaly-profile dirty_realistic
tabalyst generate --example computer -d OUTPUT_DIR/units --rows 10000 --unit-style localized
tabalyst generate --example computer -d OUTPUT_DIR/selected-units --rows 10000 --output-profile extended --unit-columns memory_gb,display_size_in,battery_wh,weight_kg
tabalyst generate --example computer -d OUTPUT_DIR/unit-mix --rows 10000 --anomaly-profile unit_variants
tabalyst generate --example computer -d OUTPUT_DIR/unit-mix-extended --rows 10000 --output-profile extended --anomaly-profile unit_variants_extended
tabalyst generate --example crm -o OUTPUT_DIR/contacts.csv --rows 500
tabalyst generate --example insurance -d OUTPUT_DIR/insurance --rows 3000 --anomaly-profile dirty_realistic
```

With `-d`, Computer writes `computers-en.csv`, `computers-fr.csv`, and
`computers.meta.json` (see the next section for `-o` and one locale). The two CSVs project the same internal offer; only
localized labels differ. The default `compact`, `standard`, and `extended`
profiles contain 40, 70, and 111 columns. `--request FILE` accepts a JSON
object with `rows`, `seed`, `as_of_date`, `generation_profile`,
`output_profile`, `market`, `locales`, `unit_style`, `unit_columns`, and `anomaly_profile`.
Explicit CLI options override that
request. The development CLI also accepts `--market ca|us` and
`--locales en,fr`. `--unit-style localized` presents measurements with
localized units in both clean CSVs; the default `numeric` keeps the existing
numeric cells. `--unit-columns` selects a comma-separated subset of measured
columns and implies `localized`; a JSON request accepts a list. Selected
columns must belong to the output profile. Computer supports
`dirty_realistic`, `dirty_stress`, `unit_variants`, and
`unit_variants_extended` anomaly profiles.

The service boundary is `tabalyst.build_generate_plan(...)` followed by
`tabalyst.generate_datasets(plan)`. For a Computer package, use
`package_path` or pass the directory as the first argument:

```python
from tabalyst import build_generate_plan, generate_datasets

plan = build_generate_plan(
    example="computer",
    output_dir="OUTPUT_DIR",
    rows=10000,
    seed=42,
    output_profile="extended",
)
result = generate_datasets(plan)
print(result.paths)
```

Planning validates the inputs and all destinations before writing. Existing
artifacts require `force=True` in the API or `--force` in the CLI. Generation
stages outputs and restores previous files on publication failure as far as
possible; whole-batch atomicity is not promised. Both interfaces reject an old
`definition_version: 1` file with `PACKAGE_FORMAT`. There is no automatic
conversion: author a `dataset.yaml`, `catalog.yaml`, and schemas, then verify
the domain outputs against the old definition before release. The published
0.6.2 release still accepts the old definition and does not support packages.

### Destinations, locales, anomaly profiles, progress and workers

Since 0.7.3 the Computer package accepts both destinations:

- `-d DIR` writes `computers-<locale>.csv` for each requested locale and
  `computers.meta.json`; with anomaly profiles it also writes, per locale and
  profile, `computers-<locale>.<profile>.csv`, `.changes.csv` and
  `.summary.json`. `--locales` takes `en`, `fr` or `en,fr` (default `en,fr`).
- `-o FILE.csv` writes one file in one locale (default `en`; two locales are an
  error). With one anomaly profile the file holds the errors and
  `FILE.changes.csv` lists the changed cells. The clean copy, the summary and
  the metadata are built in a scratch folder beside the output and not
  published.
- `--anomaly-profile` and the request key `anomaly_profile` take one name, a
  comma-separated list, or (request only) a JSON list. Several profiles need
  `-d`, each name once. The rows are generated once and each profile makes its
  variant with its own random streams, so a variant is byte for byte what a run
  with that profile alone writes. The metadata of one profile keeps its layout
  (`request.anomaly_profile`, `anomalies.<locale>`); with several, they sit in
  `request.anomaly_profiles` and `anomalies.<locale>.<profile>`, and
  `GenerateResult.anomaly_counts` is keyed `<locale>/<profile>`.
- Unknown anomaly and generation profile names list the available names.

`generate_datasets(plan, on_progress=...)` reports `GenerateProgress(stage, done,
total, elapsed_seconds)`: rows for Computer (stages `Generating rows` and
`Injecting errors (<locale>[, <profile>])`, about 200 events per stage, per span
with workers) and one step per file for the other packages. The result carries
`seconds`, `timings` (`rows`, `errors`, `publish`; empty for other packages) and
`workers`. The CLI shows a rewritten line on a terminal (`--no-progress` hides
it) and always ends with a timing line.

From 5,000 rows the rows are rendered by worker processes
(`generate_computer_parallel.py`; `--workers N`, default one per spare processor
up to 6, 1 in a frozen program). A worker renders spans of row numbers to part
files beside the outputs and the parts are appended in row order, so the files
do not depend on the number of workers. The workers reuse the subprocess helper
of Scan, not `multiprocessing`: a calling script needs no main guard. The
decision is in ADR `2026-10-29-generate-computer-workers-and-single-file`.

## Package identity and files

A package is a directory containing `dataset.yaml` and `catalog.yaml`.
`dataset.yaml` declares:

- `format: tabalyst.generate.package` and `format_version: "0.1.0"`;
- a stable ASCII snake-case `id` and an independent SemVer `package_version`;
- defaults, generated and combined datasets, ordered output schemas, entity
  pools, cohorts, generation profiles, output profiles, and anomaly profiles;
- a relative path to `catalog.yaml`.

`catalog.yaml` is required even when it declares no tables. It identifies each
CSV by a stable table ID, a relative path, a schema under `schemas/`, and one
role: `dictionary`, `entity`, `relation`, `weighted_relation`, `constraint`, or
`resource`. Large value lists stay in CSV; manifests and schemas hold rules.
Schemas declare ordered columns, physical types, required cells, uniqueness,
foreign keys, bounds, and allowed operations. Table schemas may share base
definitions. Output schema order does not depend on evaluation order.

The package must have no executable expressions, Python callbacks, or
user-supplied plugins. A packaged internal provider may implement business
logic that the declarative primitives cannot express. Its name, version,
parameters, returned fields, dependencies, and resources must be declared and
validated before generation. An unknown provider fails. The current `common`
and `insurance` providers are migration cases, not special package formats.

Package and request are separate. A request selects a dataset and supplies
rows, seed, `as_of_date`, generation and output profiles, locales, and an
optional anomaly profile. Explicit command or API overrides take precedence
over request values, then package defaults. No default depends on the current
clock. A request cannot name an output within its source package.

The normative model has two dataset modes: `generated` and `combine`. A
generated dataset evaluates a typed, acyclic sequence of column operations and
optional catalog selections. The allowed operation families are elementary
values, entity references, conditional and relative values, catalog selection,
derivation, and registered provider groups. A `combine` dataset declares
ordered generated inputs and an optional provenance column; it preserves input
CSV values and row order. Unimplemented operation families fail during
planning, as in the current staged Generate development.

The loader must reject unknown keys and operations. The following shows the
manifest shape; it is not an executable fixture until its referenced schemas
and tables exist:

```yaml
# dataset.yaml
format: tabalyst.generate.package
format_version: "0.1.0"
id: mini_computer
package_version: "0.1.0"
catalog: catalog.yaml
defaults: {rows: 10, seed: 42, as_of_date: "2026-09-30"}
datasets:
  - id: computers
    mode: generated
    row_source: catalog_steps
    schema: schemas/computers.yaml
    steps:
      - id: select_type
        kind: select
        output: computer_type_id
        source: computer_type
        candidate_column: id
output_profiles:
  compact: [product_id, sku, computer_type, memory_gb]
```

```yaml
# catalog.yaml
tables:
  computer_type:
    role: dictionary
    file: data/computer_type.csv
    schema: schemas/dictionary.yaml
  generation_memory:
    role: weighted_relation
    file: data/generation_memory.csv
    schema: schemas/generation_memory.yaml
```

The accepted manifest grammar is:

- `dataset.yaml` accepts only `format`, `format_version`, `id`,
  `package_version`, `catalog`, `defaults`, `entities`, `cohorts`, `datasets`,
  `generation_profiles`, `output_profiles`, and `anomaly_profiles`. Only
  `entities`, `cohorts`, and the three profile collections may be absent.
- A generated dataset requires `id`, `mode: generated`, positive `rows`,
  `row_source`, and `schema`; it may declare `source`, a fixed `cohort`, and
  `steps`. `row_source: columns` evaluates the column operations in its output
  schema, including CRM's typed generators and Insurance's provider group.
  `row_source: catalog_steps` requires a nonempty `steps` list. A combine
  dataset requires `id`, `mode: combine`, ordered `inputs`, and may declare
  `source_column`; it has no rows, row source, or steps of its own.
- `schemas/*.yaml` for output declares an ordered `columns` list. A column has
  `name`, physical `type`, and one of `from` (an internal field) or `generate`
  (a typed value operation); `depends_on`, `missing`, and `cohort` keep the v1
  semantics. An optional `label_table` on a `from` column renders an internal
  ID through that table's `en` or `fr` label. A provider result is read by
  `generate: {kind: provider, name: ..., group: ..., field: ...}`. The
  registered provider schema validates remaining parameters. Entity pool
  columns use the same grammar. The finite built-in value kinds include the
  v1 elementary and dependent kinds plus `stable_id`: it hashes an ordered
  list of named internal fields, with explicit `prefix` and digest length.
  Reserved inputs `dataset_id`, `seed`, and `row_index` support unique offer
  IDs. A schema may define intermediate columns omitted from every output
  profile, such as `configuration_id` and `variant_id`; their values remain
  available to dependent operations. No user expression is evaluated.
- `catalog.yaml` accepts only `tables`. Each table has `role`, `file`, and
  `schema`. A table schema declares `type`, an ordered `columns` mapping with
  `type`, `required`, optional `unique`, `references`, and bounds, plus an
  optional composite `unique` list. `references` names `table.column`.
- A catalog step has unique `id`, `kind`, and `output`. `kind: select` also
  requires `source` and `candidate_column`. Optional `where` maps a source
  column to an already selected internal field; `filters` intersects other
  relation tables by the same rule; `weight_column` names a positive source
  column, or candidates are initially uniform. `influences` lists other
  weighted tables, each with `candidate_column` and `where`. Missing influence
  rows contribute factor 1. `kind: derive` requires `from_table`, `selected`
  internal ID, and `column` to copy; it cannot draw randomness. These are the
  only catalog step kinds in the first implementation.
- `generation_profiles` map profile IDs to defaults and scoped constraints;
  a catalog step can use the reserved execution field `generation_profile_id`
  in an influence relation. It is available before the first selection step
  and never appears in the selected row. A missing profile weight contributes
  factor 1, as for other influences.
  `output_profiles` map IDs to ordered column-name lists. Computer's three
  lists are projections of the canonical register below. `anomaly_profiles`
  retain the v1 target/operation semantics. Unknown dataset, table, field,
  profile, step, or provider names fail before execution.

Step dependencies form a directed acyclic graph. A `where` or `selected`
reference must name a prior internal field, except that `where` may use the
reserved `generation_profile_id` context. Output schema order never changes
this evaluation order. The `where` mapping uses equality on canonical IDs,
never localized labels. For Computer, generation relations delimit candidates;
`filters` additionally intersect compatibility relations. One selected row
must resolve to one canonical candidate ID, and duplicate candidate IDs in a
single candidate set are rejected rather than silently changing their weight.

## Loading, validation, and limits

Use the strict YAML rules already established for Generate v1: reject repeated
keys, custom tags, recursive aliases, multiple documents, unexpected types,
and oversized files with a source location where possible. All resource paths
are relative to the package, checked after normalization and real path
resolution. Absolute paths, traversal outside the package, and symlinks that
escape it fail. Plan every output against every input and resource before
writing; `--force` never permits overwriting an input.

CSV is UTF-8, comma-delimited, with unique headers. An empty cell means an
absent value; `none` is reserved for an actual domain category. Supported
reference-table types are `string`, `integer`, `number`, `boolean`, and
`date`. Output schemas also retain `decimal` and `datetime` from v1 for the
CRM/Insurance migration. Decimal separator is `.`, dates are `YYYY-MM-DD`,
datetimes use the v1 canonical ISO form, and booleans are `true`/`false`.
Catalog IDs and internal selected values use lowercase ASCII snake case.
Dataset artifact IDs retain the current filename-safe form, which also allows
hyphens, so `crm-contacts` and `insurance-principal` keep their output names.
Existing CRM and Insurance output column names remain as published. Localized
dictionary entries require `id`
and `en`; `fr` is also required when a package offers French output. Technical
numeric values are stored in typed columns, never parsed from IDs or labels.

Initial upper bounds are 1 MiB per YAML file, 128 CSV tables, 64 MiB total
reference CSV bytes, two million reference cells indexed, 64 datasets, 256
columns per dataset, 32 profiles, and 10 million requested rows. These are
input safety limits, not performance promises; generated output bytes are
streamed and do not count toward the reference budget. The first loader lot
must check the three packages against these limits and return to this contract
before increasing a limit that blocks a required case.

Validation has four levels: parse CSV, apply schema, resolve references, and
check generation feasibility. Reject duplicate IDs and relation pairs,
unknown foreign IDs and constraint values, orphaned required entities,
nonfinite or nonpositive weights, required generations without any CPU,
memory, storage, or display, and dependency cycles. Errors contain a stable
code, file, row, and column when known. Reference errors also identify the
referenced table and ID. Static feasibility checks all reachable generations;
the engine checks each dynamic row before it is published. `--validate-only`
does not imply that every possible requested combination is feasible.

## Execution boundary and providers

The loader returns an indexed `DatasetPackage`. `build_generate_plan()` resolves
a typed `GenerationRequest`, validates the package and effective options,
plans every artifact, and checks collisions. `generate_datasets(plan)` stages,
verifies, and publishes. The CLI remains a thin adapter. Providers are
registered in the engine, not loaded by path from a package. Each provider
declares its parameter and resource schema, validates before execution, and
produces one typed result for a dataset/entity group and row index. All fields
in the group read that same result. Resource provenance and redistribution
rights are recorded with the package. The initial registry names are
`common.person`, `common.address`, `common.contact`, and `insurance`; the three
common names preserve the present provider roles. Entity pools are built once per run and
shared by their dependent datasets. A generated record holds stable IDs and
typed values; rendering and localization happen after all choices.

The final CLI accepts a package directory, its `dataset.yaml`, or a packaged
`--example crm|insurance|computer`. Computer can also be loaded by local package
path. `--request FILE` is optional. `-o` names exactly one
clean CSV without a companion; `-d` is required for multiple CSVs, metadata,
or anomalies. A validation-only call needs no destination and writes nothing.

In the Computer development lot, `--request FILE` reads a bounded UTF-8 JSON
object with optional `dataset`, `rows`, `seed`, `as_of_date`,
`generation_profile`, `output_profile`, `market`, `locales`, and
`unit_style`, and `anomaly_profile` keys. The
effective value order is explicit CLI/API option, request, then package default.
Computer currently requires `dataset: "computers"` and paired `en`/`fr` locales;
it offers `compact`, `standard`, and `extended` output profiles. It accepts `ca` and `us` markets. A Computer
run requires `-d`; its destination cannot be inside the source package.

```text
tabalyst generate --example computer -d computer-output/ --rows 10000 --seed 42
tabalyst generate --example computer --validate-only
tabalyst generate --example crm -o crm-contacts.csv
tabalyst generate --example insurance --rows 3000 -d insurance-output/
```

The proposed service shape is `build_generate_plan(package_path=...,
request=..., output_dir=..., overrides=..., force=False) -> GeneratePlan`,
`generate_datasets(plan) -> GenerateResult`, and
`validate_generate_package(path) -> ValidationResult`. It accepts a local
package path or packaged example name, never an unvalidated YAML mapping. The
result reports paths, row counts, and anomaly counts. The v1 reader coexisted
during early development lots; after lot 10 the CLI and API reject `definition_version: 1` with
an explicit format error. There is no automatic converter or fallback reader.

Computer's clean run produces `computers-en.csv`, `computers-fr.csv`, and
`computers.meta.json` under `-d`. The metadata records format and package
versions, resource digests, effective request, output counts and profiles,
engine version, and Python version. With an anomaly profile, six more files
appear: `computers-{en,fr}.PROFILE.csv`, `.changes.csv`, and `.summary.json`.
The metadata records the selected anomaly profile, artifact names, and changed
cell counts. Each journal identifies the row, operation, column, before and
after values, and cause. Its summary distinguishes requested, applied, and
skipped rows for every operation. The two locale passes select the same rows
and mutate only fields with shared values; clean CSV bytes are unchanged.
For `unit_variants`, the same cells are selected in EN/FR, and the journal
records `GB` in English or `Go` in French.
Paths or timestamps in metadata have no
byte-stability guarantee. All outputs are planned before writing. Writers
stage and verify every artifact before first publication; generation failure
leaves no new final file. Publication uses per-file atomic replacement and
best-effort restoration, as in the existing Generate contract. Whole-batch
atomicity under publication failure is not promised.

Computer declares explicit anomaly profiles. `dirty_realistic` requests
missing memory capacity (2.5%) and CPU model (1.5%), slash-formatted release
dates (2%), nonnumeric current prices (1%), misspelled stock status (1.5%),
zero VRAM on dedicated GPUs (4%), and zero stock with `in_stock` status (3%).
`dirty_stress` requests the same operations at 12%, 8%, 10%, 6%, 8%, 18%,
and 15%, respectively. Rates are fractions of all rows; conditional rules
apply only when their `when` predicate holds, so their applied rates can be
lower. Both profiles also end with three `unit_gb` operations on memory,
storage and GPU VRAM (8%, 5% and 3% in `dirty_realistic`; 15%, 10% and 6% in
`dirty_stress`), the `unit_variants` operations, so a dirty file always mixes
numbers and values with a unit. They only use columns of the `compact` profile.
Each operation's rate and condition live in `dataset.yaml`. The
reference catalogs, component selections, real model and generation names,
generation profiles, and segment weights remain clean and unchanged.

`unit_style: localized` formats 14 physical measures at export time: memory,
storage and GPU VRAM in `GB`/`Go`; CPU clock, display size, refresh rate and
brightness, NPU throughput, battery, adapter power, weight and dimensions with
their stated units. A value such as `4` in `memory_gb` becomes `4 GB` in EN
and `4 Go` in FR. The CSV column names stay stable, but these cells become
text; use the default numeric style when numeric analysis is needed. The
internal values and reference tables remain numeric. Metadata records the
selected style and suffix map. The `unit_variants` anomaly profile instead
adds localized units to a requested 8% of memory, 5% of storage and 3% of
GPU VRAM cells in altered CSVs, with a change log and measured summary.
`unit_variants_extended` requires the `extended` output profile and adds
localized suffixes to all 14 measured columns. Its requested rates are 8%
for memory, 5% for storage, 3% for GPU VRAM, 4% for CPU clock and display
size, 3% for refresh rate, 2% for brightness and NPU throughput, 3% for
battery and adapter power, 4% for weight, and 2% for each dimension. Empty
measurements can be skipped; summaries report applied counts. Anomaly
injection expects numeric clean values, so choose the default numeric style
with these profiles.

## Computer selection contract

Computer uses distinct `computer_type`, `form_factor`, and `product_segment`
taxonomies; the brand, family, model, and generation hierarchy; CPU, GPU,
memory, storage, display, OS, and color catalogs; six hierarchy compatibility
relations and two technical compatibility relations;
seven generation-weight tables; and eight influence tables:
`cpu_memory_weight`, `gpu_memory_weight`, `gpu_storage_weight`,
`product_segment_memory_weight`, `product_segment_display_weight`, and
`product_segment_storage_weight`, plus profile weights by computer type and
segment. Computer offers `balanced`, `consumer`, `business`, `gaming`,
`creator`, `workstation`, `enterprise`, `mixed`, and `portable_only` generation
profiles. The profile weights multiply the neutral base type weight; `mixed`
has no preference rows and `portable_only` restricts output to laptops. The
only v0.1 constraint action is `exclude`.
The catalog uses real product and edition names with stable IDs and
English/French labels. Component combinations, weights, specifications, and
offers are illustrative fixtures, not claims about manufacturer SKUs.

Selection order is type, segment, brand, family, model, generation, form
factor, CPU, GPU, memory, storage, display, OS, color, then commercial values.
For each field, intersect catalog relations and compatibility rules; apply
active exclusions; multiply its positive base generation weight by every
applicable influence factor; then normalize relative weights for selection.
A missing influence row means factor 1, never exclusion. Weights need not sum
to 1 or 100. Candidate order is canonical by stable ID.
The output subcategory is derived from the selected type, form factor, and
segment; its category comes from the subcategory dictionary. A segment alone
can apply to several machine types.

A constraint's `scope_id` is `global` or a generation-profile ID. Both scopes
apply to a selected profile. Matching exclusions are idempotent. Check a
constraint when both fields are known. Before a choice, reject a candidate
that conflicts with an earlier choice in either condition/target direction.
The `constraint` CSV schema has exactly `scope_id`, `condition_field`,
`condition_id`, `target_field`, `target_id`, and `action` (all required strings).
Fields name catalog step outputs; IDs name canonical selected values, and
`action` is `exclude`. `filters` and `influences` are lists of mappings with
`source`, `candidate_column`, and `where`. The former intersects candidates;
the latter reads `weight` from a `weighted_relation` table. A missing matching
influence row leaves the factor at 1. Multiple matching influence rows for
one candidate and context are invalid.
For conditions involving a future choice, use deterministic, bounded
lookahead over remaining domains so no impossible row is emitted. If no valid
completion exists, fail with `GENERATION_IMPOSSIBLE_CONFIGURATION` and the
relevant dataset, generation, fields, and IDs; never retry indefinitely. A
constraint on a derived field resolves to its canonical source ID. Later
commercial fields require an explicit rule rather than dependence on CSV
column order.

The initial engine caps a row's lookahead at 100,000 visited nodes and reports
`GENERATION_SEARCH_LIMIT` if that bound is reached; it never treats a truncated
search as proof of impossibility. Weighted draws use exact rational weights
reduced to the smallest integer ratio. SHA-256 hashes length-prefixed UTF-8
parts to seed a local stream for each decision.

One internal record is rendered twice. Only declared localized labels differ
between EN and FR; IDs, SKU, numeric values, dates, booleans, currency, and
row order match exactly. An unlocalized field retains identical text. The
first milestone delivers the 40-column `compact` profile. `standard` adds 30
columns and `extended` 41 more, preserving the register order and strict
inclusion. The appendices fix the exact sets.

`configuration_id` derives from generation, CPU, GPU, memory, storage, and
display IDs. `variant_id` adds color, OS, and market. `sku` is a stable code for
the variant; `mpn` is a fictional manufacturer variant identifier. The same
configuration, variant, SKU, or MPN can recur. `product_id` identifies one
inventory offer: it derives from dataset ID, seed, and row index and is unique
within the run and identical across locales. Canonically encoded SHA-256 with
prefixes and at least 128 encoded bits supplies stable digest IDs; corpus
checks detect collisions. Prices and stock describe the offer at its market
and `as_of_date`. Currency comes from market; `0 <= current_price <=
list_price`, stock is nonnegative, and status agrees with quantity. An offer
of the same variant may have a different price or stock. Dates are ISO and
bounded by `as_of_date`; ratings and review counts obey their ranges.

The lot 6 internal Computer derivation joins selected IDs to the CPU, GPU,
memory, storage, display, OS, and generation tables. CPU and GPU brand,
family, and model come from explicit catalog columns; storage capacity comes
from numeric `capacity_gb`, never from its display label. Display touch is a
typed catalog boolean. The development
fixture accepts `ca`/CAD and `us`/USD markets. Synthetic list price combines
the selected component capacities and an offer-specific increment; a separate
discount draw yields 0, 5, 10, or 15 percent. Stock is an integer from 0 to
50, with `out_of_stock` exactly when it is zero. Release dates lie between
January 1 of the selected model year and `as_of_date`; a reference date before
that model year fails. Review counts are 0 to 500, with no rating at zero
reviews and a rating from 3.0 to 5.0 otherwise. These are fixture rules, not
claims about real products or market distributions. The internal derivation
does not yet render localized labels or write CSV.

The lot 7 development writer projects that derived record to the declared
40-column `compact` profile. It writes EN and FR from the same internal row,
localizing only dictionary labels, with UTF-8 and LF bytes. The package fixture
declares `output_profiles.compact`; lot 11 adds `standard` while `extended`
remains reserved for lots 12–14. The writer accepts
caller-supplied paths and emits a deterministic metadata JSON with effective
request, output counts and profile, package resource SHA-256 digests, engine
version, and Python minor version. Service/CLI planning and publication belong
to lot 8.

Independent SHA-256-derived streams use the root seed, dataset ID, row index,
decision ID, and relevant context IDs. No Python `hash()` or shared global RNG
state. Adding an unrelated column must not change earlier decisions. With
identical package and resource bytes, effective request, Tabalyst version, and
Python minor version, CSV bytes must match on supported systems. A different
package, provider, or engine version can change them. One million rows is a
streaming benchmark target, without a time SLA. Pools and uniqueness registries
must use bounded storage or a constructive identity rule; the generator must
not retain all output rows.

## Migration and parity gates

CRM lot 9 originally had a visible copy. Its sole maintained package is now
`src/tabalyst/generate_examples/crm/`. The common package loader validates its
manifest and generated column schemas. The column execution engine preserves
the existing 400-account pool, shuffled-cycle references, 26-column order,
cohorts and measured anomaly pass. At 500 rows with seed 42 and
`dirty_realistic`, all four output files match the frozen YAML v1 scenario byte
for byte. The transitional v1 reader remains for Insurance through lot 10.

| Existing v1 capability | Package representation | Required parity |
| --- | --- | --- |
| Definition defaults and CLI overrides | Versioned package plus typed request | Same effective defaults and override order; final v1 rejection. |
| Direct/ordered schema columns and nine elementary kinds | Generated dataset column operations | CRM 26 columns, Insurance 33 branch and 34 combined columns; same order and significant formats. |
| Dependencies, `conditional`, `relative_date`, `missing` | Acyclic operation graph | Same dependency and missingness semantics in fixtures. |
| CRM pool of 400 accounts and `reference` | Shared entity pool and grouped reference | Coherent account fields and the existing shuffled-cycle `floor/ceil` balance. |
| `common` person/address/contact | Registered internal provider and declared resources | Coherent geographic links, safe `.example` email, unique emails. |
| Weighted or fixed cohorts and clean aliases | Package cohorts before natural missingness | CRM pipeline/cohort behavior and stream independence. |
| Insurance `combine` and `source_column` | Ordered combined dataset | Default 200000/25000/50000, at `--rows 3000` 2182/273/545; `filiale` last. |
| Insurance business provider and seven tables | Registered internal provider and resources | Branch links, IDs/emails unique across branches, coherent amounts, dates, status. |
| Anomaly profile, five operations and `when` | Separate selected mutation pass | Unchanged clean CSV with/without profile, measured events and skips, seven Insurance artifacts. |
| Staging, collision checks, `--force` | Shared planner and publisher | Input protection, no new final on generation failure, best-effort restoration. |
| Packaged examples | One source per domain under `src/tabalyst/generate_examples/`, included in wheel/sdist | CLI and API work outside checkout; old YAML is rejected after lot 10. |

Freeze a v0.6.2 comparison before each migration: headers, counts, allowed
values, cohort proportions, entity links, uniqueness, branch sequence, anomaly
operations, and measured totals. Compare row invariants where semantics allow
and distributions with predeclared tolerances at the same volume and seed.
Byte identity across v1 and the package format is not required. Record and
obtain acceptance for any substantive functional difference before deleting
the v1 reader. The separate `examples/datasets/insurance-customers.csv` demo is
not a byte or value parity target.

## Reference fixture and delivery gates

The miniature Computer package has two types, segments, brands, families and
models; one generation per model; two choices each for CPU, GPU, memory (16 and
32 GB), storage, display, OS, and color. One branch excludes 16 GB for a GPU;
another offers weights 1:3. Seed 42, ten rows, and two locales form a snapshot.
Invalid fixtures cover old YAML, path escape, duplicate header/ID or relation,
unknown FK, zero or nonfinite weight, orphan, missing required component,
unknown constraint value, dependency cycle, empty candidate set, future-field
impossibility, and output collision. Examples must include actual CSV escaping,
such as `"13,3 po"`, and expected error coordinates.

Lot 1 implements parsing and limits; lot 2 references, indexing, and static
feasibility; lot 3 random streams, weights, and constraints; lots 4–7 Computer
catalog, derivation, localization, profiles, and streaming; lot 8 integrates
service, CLI, and local demo; lots 9–10 migrate CRM and Insurance and remove
the v1 reader; lots 11–14 complete the profiles and benchmark; lot 15 aligns
user documentation and demos with released behavior. No public user guide is
updated merely because this design is accepted.

The original lot 4 package had two entries at each hierarchy level and 3:1
type weights. The current package covers six computer types and includes
component choices, CSV rendering, and a `portable_only` profile. Its weights
are test distributions, not market estimates.

## Computer column register

`compact` (40 columns, in order):

```text
product_id,sku,brand,product_family,model,generation,model_year,computer_type,form_factor,product_segment,cpu_brand,cpu_family,cpu_model,cpu_cores,cpu_threads,gpu_brand,gpu_family,gpu_model,gpu_type,gpu_vram_gb,memory_type,memory_gb,storage_type,storage_gb,display_size_in,display_type,display_resolution,display_refresh_rate_hz,operating_system,color,weight_kg,currency,list_price,current_price,stock_quantity,stock_status,release_date,rating,review_count,market
```

`standard` contains these 30 additional columns:

```text
mpn,product_category,product_subcategory,cpu_architecture,cpu_max_clock_ghz,display_brightness_nits,display_touch,display_finish,os_family,npu_tops,ai_pc_class,wifi_standard,bluetooth_version,ethernet_speed,usb_a_ports,usb_c_ports,hdmi_ports,battery_wh,power_adapter_w,chassis_material,camera_type,keyboard_layout,biometric_type,discount_percent,price_tier,condition,warranty_period,product_age_months,product_lifecycle_status,language
```

The development `standard` fixture joins category and subcategory through the
selected segment, CPU architecture/clock/NPU through the selected CPU, display
brightness/finish through the selected display, and connectivity, ports, power,
chassis, camera, biometrics and warranty through the selected generation's
`standard_specs` row. `none` is an actual value for absent Ethernet, camera,
biometrics or NPU class; an inapplicable desktop battery is an empty cell.
`ai_pc_class` requires at least 40 NPU TOPS. `product_age_months` is computed
from release date and `as_of_date`; `price_tier` is synthetic and
market-adjusted. `language` describes the market offer (`en_fr` for `ca`, `en`
for `us`), so it is identical in both localized CSVs.

`extended` contains these 41 additional columns:

```text
display_aspect_ratio,display_hdr,display_color_gamut,npu_brand,npu_family,copilot_plus_pc,cellular_type,docking_support,thunderbolt_ports,displayport_ports,ethernet_port,card_reader_type,memory_slots_total,memory_slots_used,m2_slots_total,m2_slots_used,upgradeability_level,width_mm,depth_mm,height_mm,chassis_finish,microphone_type,speaker_configuration,keyboard_type,trusted_platform,product_generation,popularity_level,sales_rank,conversion_rate,seller_type,warehouse,units_sold_30d,return_rate,seller,promotion_type,promotion_status,lowest_price_30d,highest_price_30d,average_price_30d,price_change_30d_percent,shipping_availability
```

The final 16 extended fields describe synthetic offers at `as_of_date`, not
observed market activity. Generation class follows product age; sales and
popularity use deterministic offer streams, with out-of-stock sales limited to
five units in the trailing period. Conversion and return rates are bounded
synthetic fractions. Seller and warehouse belong to the selected market, and
shipping availability follows stock. A nonzero discount has an active
promotion; zero discount has no promotion. The 30-day price summary is derived
from the current price and up to two earlier synthetic snapshots. Before a
product has been available for 30 days, only its current price contributes.
The change percentage compares current price to the oldest available snapshot.
All prices use the offer's market currency. Seller, seller type, warehouse,
promotion and shipping labels come from the package dictionaries and are
localized without changing their underlying IDs or numeric values.

The complete 111-column register fixes the output order. Each profile is a
projection of this order, rather than appending its additional fields:

```text
product_id,sku,mpn,brand,product_family,model,generation,model_year,computer_type,form_factor,product_segment,product_category,product_subcategory,cpu_brand,cpu_family,cpu_model,cpu_architecture,cpu_cores,cpu_threads,cpu_max_clock_ghz,gpu_brand,gpu_family,gpu_model,gpu_type,gpu_vram_gb,memory_type,memory_gb,storage_type,storage_gb,display_size_in,display_type,display_resolution,display_refresh_rate_hz,display_brightness_nits,display_aspect_ratio,display_touch,display_finish,display_hdr,display_color_gamut,os_family,operating_system,npu_brand,npu_family,npu_tops,ai_pc_class,copilot_plus_pc,wifi_standard,bluetooth_version,ethernet_speed,cellular_type,docking_support,usb_a_ports,usb_c_ports,thunderbolt_ports,hdmi_ports,displayport_ports,ethernet_port,card_reader_type,memory_slots_total,memory_slots_used,m2_slots_total,m2_slots_used,upgradeability_level,battery_wh,power_adapter_w,color,weight_kg,width_mm,depth_mm,height_mm,chassis_material,chassis_finish,camera_type,microphone_type,speaker_configuration,keyboard_type,keyboard_layout,biometric_type,trusted_platform,currency,list_price,current_price,discount_percent,price_tier,condition,stock_quantity,stock_status,warranty_period,promotion_type,promotion_status,lowest_price_30d,highest_price_30d,average_price_30d,price_change_30d_percent,release_date,product_age_months,product_generation,product_lifecycle_status,rating,review_count,popularity_level,sales_rank,units_sold_30d,conversion_rate,return_rate,market,language,seller,seller_type,warehouse,shipping_availability
```

## Development corpus audit and volume measurement

The local Computer package includes models across six computer types and
exercises the full 111-column register. Its illustrative configurations and
weights are not a representative sample of the computer market. The
`compact`, `standard`, and `extended` projections have 40, 70, and 111 columns,
respectively, and the tests require strict inclusion in register order.

`tabalyst-lab/benchmarks/computer_corpus.py` audits every declared CSV/YAML resource, its
digest in metadata, both localized CSVs, row identity, selected offer invariants,
distributions, and three synthetic numeric correlations. Its 10,000-row
thresholds check laptop weight, type coverage, compatibility rules, and expected
directions of memory/price, reviews/sales, and sales/rank. These are fixture
checks, not market claims or performance promises.
The benchmark mode samples the generation process tree's resident memory with
`psutil`, then runs the audit and saves `audit.json`. Run it with the development
environment and an output directory outside the checkout:

```console
python ../tabalyst-lab/benchmarks/computer_corpus.py src/tabalyst/generate_examples/computer EXTERNAL_OUTPUT_DIR --rows 10000
python ../tabalyst-lab/benchmarks/computer_corpus.py src/tabalyst/generate_examples/computer EXTERNAL_OUTPUT_DIR --rows 10000 --audit-only
```

Use a fresh output directory for each generation run. Timing includes package
validation, staging, and publication, but excludes the subsequent CSV audit.
The measured memory is sampled peak resident memory of the Python process tree;
it is not a formal upper bound between samples. Larger runs stream CSV rows but
produce two substantial output files. Keep their results and all Scan/Report
outputs outside the checkout.
