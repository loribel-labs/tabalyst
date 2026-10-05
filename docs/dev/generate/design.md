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
