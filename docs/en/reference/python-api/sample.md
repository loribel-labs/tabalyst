---
title: "Python API: sampling"
description: The Python functions that write a smaller CSV file - sample_csv and generate_samples - with their parameters, return values and examples of first, last, random and stratified samples.
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
)
```

Returns a `tabalyst.SampleResult` with `source`, `output`, `method`,
`source_rows`, `sample_rows`, `sample_rate`, `field`, `seed`, `encoding` and
`delimiter`.

- `source`: the CSV file.
- `method`: `"first"`, `"last"`, `"random"` or `"stratified"`, or a
  `tabalyst.SampleMethod`.
- `rows`, `percent`: the size of the sample, as a number of data rows or a
  percentage rounded up to a whole row. Give exactly one.
- `field`: the field that defines the strata; required by `"stratified"`.
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
)
```

Returns a [batch result](index.md#batch-functions) whose successes hold a
`SampleResult` each. `input_specs` are CSV files or non-recursive glob patterns,
`output` names the file of a single source and `output_dir` the folder of the
samples, named `<stem>.sample.csv`. `delimiter` and `encoding` default to the
configuration files in `config_path`, then to the built-in defaults. The other
parameters are those of `sample_csv()`.
