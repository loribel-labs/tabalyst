---
title: "Python API: sampling"
description: The Python functions that write a smaller CSV file - sample_csv, generate_samples and the two steps of a smart sample - with their parameters, return values and examples.
---

`tabalyst.sample_csv()` samples one CSV file and `tabalyst.generate_samples()`
several. Sampling reads CSV files only. The command is
[`tabalyst sample`](../cli/sample.md).

```python
import tabalyst

sample = tabalyst.sample_csv(
    "customers.csv", method="random", rows=1000, seed=42
)
print(sample.output, sample.sample_rows)
batch = tabalyst.generate_samples(
    ["*.csv"], method="first", rows=100, output_dir="samples"
)
```

## tabalyst.sample_csv()

```python
tabalyst.sample_csv(
    source,
    *,
    method,
    rows=None,
    percent=None,
    field=None,
    seed=None,
    output=None,
    delimiter=",",
    encoding="utf-8-sig",
    force=False,
    max_strata=100_000,
)
```

Returns a `tabalyst.SampleResult` with `source`, `output`, `method`,
`source_rows`, `sample_rows`, `sample_rate`, `field`, `seed`, `encoding` and
`delimiter`. A stratified sample also gives `fields` (the columns, as a tuple)
and the balance of its strata: `strata_known`, `strata_selected` and
`strata_uncovered` (the strata that got no row). They are `None` for the other
methods.

- `source`: the CSV file.
- `method`: `"first"`, `"last"`, `"random"` or `"stratified"`, or a
  `tabalyst.SampleMethod`.
- `rows`, `percent`: the size of the sample, as a number of data rows or a
  percentage rounded up to a whole row. Give exactly one.
- `field`: the field that defines the strata, or a list of fields whose
  combinations define them; required by `"stratified"`.
- `max_strata`: the most strata a stratified sample may hold, 100,000 by
  default. More raise `tabalyst.InputError`.
- `seed`: makes a random or stratified selection reproducible.
- `output`: the output filename; by default `<stem>.sample.csv` beside the source.
- `delimiter`, `encoding`: how the CSV file is read and written.
- `force`: replace an existing sample file. A source is never replaced.

## tabalyst.generate_samples()

```python
tabalyst.generate_samples(
    input_specs,
    *,
    method,
    rows=None,
    percent=None,
    field=None,
    seed=None,
    output=None,
    output_dir=None,
    delimiter=None,
    encoding=None,
    config_path=None,
    force=False,
    max_strata=None,
    confirmed=False,
    on_progress=None,
)
```

Returns a [batch result](index.md#batch-functions) whose successes hold a
`SampleResult` each. `input_specs` are CSV files or non-recursive glob patterns,
`output` names the file of a single source and `output_dir` the folder of the
samples, named `<stem>.sample.csv`. `delimiter` and `encoding` default to the
configuration files in `config_path`, then to the built-in defaults. The other
parameters are those of `sample_csv()`.

`max_strata=None` is the default limit of 100,000; give a number to change it and
to allow a stratified sample that a stored scan shows may make too many strata.

## Smart samples

`method="smart"` in `generate_samples()` writes a smart sample and its
[report](../../sample/format.md). `field` is not used. The sample needs the scan of
the file: the stored one is reused, and otherwise the file is scanned first.
The function never asks anything. When the selection is costly it raises
`tabalyst.SelectionConfirmationRequired` before reading any source again, with the
estimate in `.confirmation`; call it again with `confirmed=True` to run it.

```python
import tabalyst

try:
    batch = tabalyst.generate_samples(
        ["customers.csv"], method="smart", rows=1000
    )
except tabalyst.SelectionConfirmationRequired as asked:
    print(asked.confirmation.estimate)
    batch = tabalyst.generate_samples(
        ["customers.csv"], method="smart", rows=1000, confirmed=True
    )
result = batch.successes[0].result
print(result.report, result.smart.covered, result.smart.evaluable)
```

A `SampleResult` of a smart sample also has `report` (the path of the report) and
`smart`, a summary with `targets`, `evaluable`, `covered`, `weighted_share`,
`mandatory`, `mandatory_covered`, `reserve_rows`, `passes`, `scan_ran` and
`duration_seconds`. `tabalyst.prepare_smart_samples()` does the first half (scan,
plan, estimate; it returns a preparation whose `requires_confirmation` and
`confirmation` you can read) and `tabalyst.execute_smart_samples(preparation,
confirmed=False)` the second. `tabalyst.plan_sampling()` gives the
[plan](../../scan/plan.md#smart-sample-plan) alone.
