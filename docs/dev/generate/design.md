# Tabalyst Generate design

This is the implementation contract for Tabalyst Generate. The definition
format is experimental during beta. The first release is to include packaged
`crm` and `insurance` examples; neither is evidence that Report detects every
business rule represented in the data.

## Command and service boundary

```text
tabalyst generate DEFINITION.yaml (-o FILE.csv | -d DIR) [options]
tabalyst generate --example {crm|insurance} (-o FILE.csv | -d DIR) [options]
```

The two definition sources are exclusive; exactly one destination is required.
Options are `--rows N`, `--seed INTEGER`, `--as-of-date YYYY-MM-DD`,
`--anomaly-profile NAME`, and `--force`. Explicit options override `defaults`
without editing the YAML. `-o` is valid only for one clean CSV. Multiple CSVs
or any selected anomaly profile require `-d`. Nothing writes beside the YAML
or into the current directory by default. `--example` reads YAML packaged in
the installed wheel.

`build_generate_plan(...)` loads and validates the definition, resolves
overrides, determines every artifact, and checks all output paths before work.
`generate_datasets(plan)` stages, verifies, and publishes the artifacts. The
Typer adapter only presents these service operations and their errors. The
result reports published paths, row counts, and anomaly counts. A service
accepts a local path or packaged example name, never an unvalidated YAML
object.

## Definition version 1

The root mapping requires `definition_version: 1`, a safe `id`, and a nonempty
`datasets` list. Allowed root keys are `definition_version`, `id`, `defaults`,
`csv`, `schemas`, `entities`, `cohorts`, `datasets`, and `anomaly_profiles`.
Unknown or repeated keys, custom YAML tags, recursive aliases, multiple
documents, and oversized input are errors with a file and location where
available. All mappings and scalar types are checked strictly. Resource paths
cannot refer to arbitrary local files, and Python expressions are forbidden.
The loader bounds file bytes, collection sizes, column counts, and row counts.

Each dataset has a unique filename-safe `id` and exactly one mode: direct
`columns`, a reference to `schemas.<id>.columns`, or `combine`. A generated
dataset has a positive integer `rows`. Schemas contain ordered columns with
unique names. Each column specifies its physical `type`, a `generate.kind`
with validated parameters, optional dependencies, and natural missingness.
Column dependencies must form an acyclic graph. Execution may use topological
order; CSV order stays as declared. Supported kinds are introduced by lot:
elementary generators in lot 2, entity references and conditional/relative
values in lot 3. Cohorts and anomaly operations arrive in lot 4. A lot 1
definition may be validated and planned without being executable yet.

`combine.inputs` is a nonempty ordered list of generated dataset identifiers.
Unknown, repeated, or cyclic references fail. Inputs must have compatible
headers. Combining preserves the textual source values and may add a declared
provenance column. Anomaly profiles have unique safe identifiers and reference
declared datasets. Merely declaring a profile changes no generated value;
selection with `--anomaly-profile` starts a separate, logged mutation pass.
Normal source variants and cohorts belong to the clean data.

`--rows N` changes a single generated dataset to N rows. For one terminal
combine, it changes the combined total and apportions N to generated inputs
using their declared row counts as weights. Largest remainders win; tied
remainders use stable dataset-id order. If an input would receive zero, move
one row from the largest allocation above one, breaking ties by id. N smaller
than the number of inputs fails. The Insurance weights 200000, 25000, 50000
give 2182, 273, 545 at N=3000. With multiple independent outputs and no
single terminal combine, `--rows` is ambiguous and fails. Nonpositive rows,
invalid dates, and unknown profiles fail before any write.

## Artifacts and publication

Without a selected profile, every dataset has one clean `<dataset-id>.csv`.
For each target of a selected profile, add
`<dataset-id>.<profile-id>.csv`,
`<dataset-id>.<profile-id>.changes.csv`, and
`<dataset-id>.<profile-id>.summary.json`.
Names never include row counts. Insurance therefore plans four clean CSVs and,
when its combined dataset is targeted, three more artifacts.

Planning detects collisions among all artifacts, existing outputs without
`--force`, collisions with the definition or resources, invalid destinations,
and a directory used as a file. `--force` only permits replacement after all
checks pass. Writers prepare every artifact in temporary files on the target
volume and verify them before the first final publication. A generation failure
leaves no new final file. Each publication uses atomic per-file replacement;
with `--force`, preserve old targets in backups first. If publication fails,
restore the previous state as far as possible and report final and backup
paths requiring inspection. Whole-batch atomicity under publication failure
is not promised.

CSV is UTF-8 with LF endings, stable column and row order, locale-independent
formats, and correct CSV escaping. With identical definition, resources, seed,
Tabalyst version, and Python minor version, CSV bytes must match on supported
systems. Summary paths and timestamps do not have this guarantee. Independent
random streams derive from a root seed and canonical identifiers per dataset,
entity, column, and operation; Python `hash()` and shared global RNG state are
not used.

## Delivery lots

Lot 1 implements strict loading, structural and semantic validation, planning,
safe staging/publication, service, and CLI. It must fail clearly if execution
requires a generator or profile operation not yet implemented. Lot 2 supplies
elementary values and CSV reproducibility; lot 3 adds entities, dependencies,
conditions, and combine; lot 4 adds cohorts and measured anomalies; lot 5
proves the CRM example; lot 6 completes Insurance and both packaged examples.
Examples and user documentation must describe only implemented behavior at
each stage. The prototype's YAML loader, CSV writer, and tests are migration
references, not the public format or safety contract.

## Lot 3 implementation state

An entity declares `id`, `count` (at most 100,000, with at most one million
generated cells), `generator` (`company` or
`person`), and ordered `columns` using the same column grammar as datasets.
`generator` identifies the entity role; values come from its declared columns.
Entity columns may depend on one another but cannot reference another pool.
Pools are generated once per execution from entity-specific random streams and
shared by all datasets. No external reference table is bundled at this stage.

`reference` names an entity and one of its fields with the same physical type.
All reference columns to one entity in a dataset row select the same member.
Selection uses a seeded shuffled cycle per dataset and entity. In each complete
cycle every member occurs once; for N rows and P members, each occurs either
`floor(N/P)` or `ceil(N/P)` times. If N is less than P, only N members appear.
This guarantee concerns the selected member; column `missing` can suppress an
individual output value. Datasets select independently, while a member's
fields remain identical wherever it is selected.

`depends_on` names declared columns and must be acyclic. Evaluation uses
dependency order; CSV headers retain definition order. A `conditional`
generator declares `from`, `cases` (source text to scalar output), and a scalar
`default`; its source must appear in `depends_on`. `relative_date` declares
`from` and an integer day `offset`, with optional `format`; it also requires a
declared dependency of date or datetime type. A missing source yields a missing
relative date. Source dates use canonical ISO values. Neither generator
evaluates expressions.

`combine` reads its generated inputs in declared order and preserves their
values and row order. An optional `source_column` is appended last and takes
each input's `source` value or dataset id. Input headers and physical types
must match. It is staged with the other outputs before any publication.

The packaged `crm` and `insurance` YAML files remain development fixtures;
the complete CRM and Insurance examples arrive in lots 5 and 6.

## Lot 4: clean cohorts and measured anomalies

`cohorts` is an optional list of weighted `{id, weight}` objects. For each
generated row, a dedicated seeded stream selects one cohort; a generated
dataset may instead set `cohort` to a declared id to use it for every row.
Entity pools also select cohorts independently. A cohort's optional `values`
maps string column names to replacement text. Its optional `formats` maps
string column names to maps of exact source text to replacement text. These
declared replacements occur in the clean generation pass, before the column's
natural `missing` probability. A column-level `cohort` makes that column
present only in rows of the named cohort. Cohorts are selected separately from
all column value streams, so adding an unrelated column does not change the
cohort sequence. A fixed dataset cohort does not change entity pool cohorts.

Selecting `--anomaly-profile` adds a separate pass over each targeted staged
clean CSV. Operations run in YAML order. Each operation names a `column` and a
`rate` from 0 to 1. The engine selects exactly `round(rows * rate)` source
rows with its own seeded stream. Optional `when: {column: text}` limits the
mutation to rows whose current value matches; ineligible or unchanged requests
are counted as skipped. Selection is independent per operation, so one row
may receive several changes. The supported operations are:

| `kind` | Parameters and behavior |
| --- | --- |
| `set_missing` | Clear a nonempty cell. |
| `replace` | Set `value` to a literal string if different. |
| `duplicate` | Copy a different, nonempty clean value from one of the first 1,000 preceding rows of the same column. |
| `format` | Apply `value`: `upper`, `lower`, `strip`, `date_slash`, or `phone_spaces`. |
| `swap` | Exchange `column` and the second column named by `value` when they differ. |

Each targeted dataset gets its untouched clean CSV, altered CSV, changes CSV,
and summary JSON. The changes CSV has one record per changed cell with the
one-based CSV record number (header is record 1), operation index,
before/after text and cause. The
summary gives definition id/version, effective seed and date, Tabalyst version,
row count, requested/applied/skipped counts per operation, affected rows,
events, and changed cells. Natural missing values and no-op mutation requests
are never reported as introduced defects. All four outputs are staged before
publication. The clean CSV has identical bytes whether or not the profile is
selected.

## Lot 2 implementation state

Direct datasets and schema-backed datasets can now stream elementary columns:
`constant`, `sequence`, `choice`, `integer`, `decimal`, `boolean`, `date`,
`datetime`, and `text`. `choice.weights` are positive relative weights;
`missing` is an independent per-column probability. `date` and `datetime`
default to a range from 1970-01-01 through `as_of_date` (the end of that day
for datetime). Decimal values use a bounded scale, defaulting to 2. Numeric
bounds and individual choice weights are limited to one trillion. The
elementary random streams are SHA-256-derived from seed, dataset id, column
name, and operation. Rows are streamed into the staged CSV file.

The packaged `crm` planning fixture is executable as one simple clean CSV.
The packaged `insurance` fixture now exercises `combine`. Neither fixture is
the final public demo definition.

## Lot 3R: packaged common references

The `common` generator is an additive version-1 kind. It has no user-supplied
resource path. Its parameters are `provider`, `group`, and `field`. `group` is a
safe id shared by columns that must read the same per-row result. Columns in a
group must use identical provider parameters except `field`; all fields are
strings. One SHA-256-derived random stream per dataset/entity and group keeps
groups independent of column order. Entity pools can use the same kind and
remain shared across datasets.

Providers and their optional parameters:

| Provider | Fields | Parameters |
| --- | --- | --- |
| `person` | `first_name`, `family_name`, `sex`, `salutation`, `language` | `profile: fr`, `en`, or `mixed` (default) |
| `address` | `street_number`, `street_type`, `street_type_position`, `street_name`, `street_direction`, `street_direction_position`, `street`, `unit_type`, `unit_number`, `unit`, `city_id`, `city`, `province_code`, `province_name`, `postal_prefix`, `postal_code`, `country_code`, `language` | `profile: fr`, `en`, or `mixed` (default); optional `province` code; `unit_probability` and `direction_probability` in `[0,1]` |
| `contact` | `email`, `phone` | Required `first`, `last`, `province`, plus optional `language`: names of declared string columns, each also in `depends_on` |

The packaged, UTF-8 CSV tables are in `generate_resources/{people,geography,addresses,contact}`.
All 13 fixed schemas, positive weights, profiles, safe domains and geographic
links are checked when execution first needs them. The tables are loaded once
per execution. The manifest `generate_resources/SOURCES.md` records provenance,
licensing and replacement of two uncertain prototype tables. The city and
postal prefix are selected together within a province. Prefixes are synthetic
and only match Canadian syntax; addresses are not asserted deliverable. Phone
area codes are synthetic and linked to provinces, with reserved `555-01xx`
line numbers. Email provider language profiles are respected when a `language` source is provided. Email addresses always use `.example` domains and are unique
within each generated dataset or entity pool. Missingness on a column can
suppress one of a group's outputs; dependent contact values then use the
visible input fields. The representative definition is
`examples/generate/input/common-references.yaml`; it is a development fixture,
not the final CRM or Insurance example.

The runtime keeps only the current row's group results and the set of issued
emails; entity pools remain bounded by the lot 3 contract. Identical
definition, seed, resources, Python minor version and Tabalyst version yield
identical CSV bytes.

## Lot 5: CRM development demo

The packaged and visible `crm.yaml` definitions are identical. They generate a
single `crm-contacts` CSV with 26 columns and 400 shared synthetic accounts.
Contact names and account locations use the packaged common references;
contact email and phone depend on the selected account province. The account
names are generic sequence labels, rather than real businesses. The clean data
has natural missingness; selecting `dirty_realistic` injects separate, logged
changes for reachability, company-name case, country, industry, lead source and
selected pipeline fields. On 2026-10-05, the maintainer approved the configured
20,000 rows, the CRM audit narrative and the generic account labels for the
public example. This is approval of the example design, not a release.

The CRM demo is evidence for what the current Scan and Report actually show:
column missingness, value frequencies, category fragmentation and normalization
variants. The mutation summary measures applied operations and skipped requests.
Scan and Report do not currently evaluate cross-column CRM business rules,
including stage/probability or chronological consistency. Such relationships
may be illustrated as data examples but must not be described as detected
issues in the Report.

## Lot 6: Insurance example

The visible and packaged `insurance.yaml` files are identical. Three branch
datasets use one 33-column schema and are combined in Principal, Ontario,
Quebec order. The combined `filiale` column is appended last by the generic
`combine` contract. `--rows 3000` produces 2,182, 273 and 545 branch rows.
The default 275,000 combined rows follow the declared 200,000/25,000/50,000
weights. The `dirty_realistic` profile targets only the combined CSV, so it
produces seven artifacts in total, four of them clean.

The `insurance` generator kind is limited to the 33 named fields and a shared
`group`. It requires a dataset `source` of `principal`, `ontario` or `quebec`.
One group result is generated per row, with stable dataset/group random state.
The provider uses the packaged common person, address and contact references
and seven Insurance tables. Table headers, weights, product coverage, amounts,
status policies and agency/city links are validated on use. The Insurance
tables are synthetic project data, with provenance in
`generate_resources/insurance/SOURCES.md`.

Branch-specific client identifiers and dates retain the prototype's formats.
Amounts have two decimal places; claims are optional and tied to product
probabilities. The new dataset is not a byte-for-byte reproduction of either
the prototype or `examples/input/insurance-customers.csv`. The existing public
3,000-row CSV has the same 34 column names but places `filiale` first, uses
different values and remains unchanged. This provider models a pedagogical
export, not actuarial rates or comprehensive insurance validation.
