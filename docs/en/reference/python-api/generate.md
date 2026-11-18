---
title: "Python API: Generate"
description: Generate synthetic datasets, build reproducible benchmark populations and list available anomaly profiles with the Tabalyst Generate Python API.
---

`tabalyst.build_generate_plan()` and `tabalyst.generate_datasets()` plan and
produce synthetic datasets from Generate packages or packaged examples.
`tabalyst.list_available_anomaly_profiles()` inspects the catalog of anomaly
profiles.

```python
import tabalyst

# Plan and generate the insurance reference dataset with ground truth
plan = tabalyst.build_generate_plan(
    example="insurance",
    anomaly_profile="rare_events",
    rows=100_000,
    seed=42,
    output_dir="artifacts/insurance_run",
)
result = tabalyst.generate_datasets(plan)
print(f"Created {len(result.paths)} files.")
```

## Functions

### `tabalyst.build_generate_plan()`

Validate a Generate definition or package and plan every artifact before
writing.

```python
plan = tabalyst.build_generate_plan(
    definition_path=None,
    example="insurance",
    output=None,
    output_dir="out",
    rows=10000,
    seed=42,
    as_of_date="2026-09-16",
    anomaly_profile="format_vs_business",
    force=False,
    output_profile="default",
    relational=False,
    row_order="default",
    english=False,
)
```

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `definition_path` | `str \| Path \| None` | `None` | Path to a package directory or its `dataset.yaml`. |
| `example` | `str \| None` | `None` | Packaged example: `"crm"`, `"insurance"`, or `"computer"`. |
| `output` | `str \| Path \| None` | `None` | One CSV file destination (requires single clean CSV or single altered file with changes). |
| `output_dir` | `str \| Path \| None` | `None` | Directory for all planned artifacts. |
| `rows` | `int \| None` | `None` | Number of generated rows. |
| `seed` | `int \| None` | `None` | Root random seed for deterministic reproducibility. |
| `as_of_date` | `str \| None` | `None` | Reference date in `YYYY-MM-DD` format. |
| `anomaly_profile` | `str \| tuple[str, ...] \| None` | `None` | Profile name or comma-separated list of profiles to inject. |
| `force` | `bool` | `False` | Overwrite existing files. |
| `output_profile` | `str \| None` | `None` | Output column profile. Computer: `"compact"`, `"standard"`, `"extended"`. Insurance: `"default"` (34 cols), `"extended"` (44 cols), `"complete"` (51 cols), or flattened profiles (`"flattened"`, `"flattened-extended"`, `"flattened-complete"`). |
| `relational` | `bool` | `False` | Insurance: generate 4 relational tables (`clients`, `contrats`, `reclamations`, `paiements`) with ground truth. |
| `row_order` | `str` | `"default"` | Insurance row ordering: `"default"`, `"branch"`, `"chronological"`, `"agency"`, `"shuffled"`. |
| `english` | `bool` | `False` | Insurance: translate column names to English and localize categorical values. |
| `validate_only` | `bool` | `False` | Validate configuration without creating artifacts. |

Returns a `GeneratePlan` (or `ComputerPlan` for the Computer example).

### `tabalyst.generate_datasets()`

Execute a validated generation plan, writing CSV files and ground-truth
artifacts atomically.

```python
result = tabalyst.generate_datasets(plan, on_progress=None)
```

| Parameter | Type | Default | Meaning |
| --- | --- | --- | --- |
| `plan` | `GeneratePlan \| ComputerPlan` | required | Plan created by `build_generate_plan()`. |
| `on_progress` | `Callable[[GenerateProgress], None] \| None` | `None` | Optional callback reporting generation stage and row progress. |

Returns a `GenerateResult` object:
- `result.paths`: tuple of `Path` objects written.
- `result.row_counts`: dictionary mapping dataset identifiers to written row counts.
- `result.anomaly_counts`: dictionary mapping dataset/profile keys to changed cells count.
- `result.artifacts`: tuple of planned `GenerateArtifact` instances with their roles.

### `tabalyst.list_available_anomaly_profiles()`

List available anomaly profiles, target datasets, and minimum row thresholds.

```python
# List profiles for the Insurance example
profiles = tabalyst.list_available_anomaly_profiles(example="insurance")
for p in profiles["insurance"]:
    print(p["id"], p.get("min_rows"))

# List profiles across all built-in examples
all_profiles = tabalyst.list_available_anomaly_profiles()
```

Returns a dictionary mapping package identifiers to lists of profile descriptors.

### `tabalyst.validate_generate_package()`

Validate that a Generate package directory or `dataset.yaml` complies with package
specifications without planning outputs.

```python
validation = tabalyst.validate_generate_package("path/to/package")
if not validation.valid:
    print(validation.errors)
```

## Related pages

- [CLI: tabalyst generate](../cli/generate.md), for the command line interface.
- [Insurance customers overview](../../generate/insurance.md).
- [Insurance ground truth files](../../generate/insurance-ground-truth.md).
- [Insurance rare events](../../generate/insurance-rare-events.md).
