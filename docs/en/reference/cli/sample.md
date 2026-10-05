---
title: "CLI: tabalyst sample"
description: Every option of tabalyst sample and examples of first, last, random and stratified CSV samples, with fixed sizes, percentages and seeds.
---

```console
tabalyst sample INPUT... --sample-method METHOD [OPTIONS]
```

Creates `<stem>.sample.csv` beside each CSV source, or in the folder of `-d`,
without modifying the source. Choose exactly one size: `--rows` or `--percent`.
See [Tabalyst Sample](../../sample/index.md).

## Options

| Option | Description |
| --- | --- |
| `INPUT...` | One or more CSV files or non-recursive glob patterns (required) |
| `--sample-method METHOD` | Required: `first`, `last`, `random` or `stratified` |
| `--rows N` | Number of data rows to select |
| `--percent X` | Percentage of data rows to select, rounded up to a whole row. Exclusive with `--rows` |
| `--field TEXT` | Field that defines the strata, required by `stratified` |
| `--seed N` | Seed that makes a random or stratified selection reproducible |
| `-o`, `--output PATH` | Output CSV filename, for a single input. Not with `-d` |
| `-d`, `--output-dir PATH` | Folder for samples named `<stem>.sample.csv` |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md) |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `-f`, `--force` | Replace an existing sample file; a source is never replaced |
| `--help` | Show the options and exit |

## Examples

```console
tabalyst sample customers.csv --sample-method first --rows 1000
tabalyst sample customers.csv --sample-method last --rows 1000
tabalyst sample customers.csv --sample-method random --percent 5 --seed 42
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
tabalyst sample customers.csv --sample-method first --rows 100 -o test.csv
tabalyst sample *.csv --sample-method random --percent 5 -d samples/
tabalyst sample data.csv --sample-method random --rows 100 --delimiter ";" --encoding cp1252
```

Sample accepts CSV files only; there is no Excel or JSON sample.

## Exit codes

| Code | When |
| --- | --- |
| `0` | Every sample was written |
| `1` | A sample could not be written |
| `2` | Invalid options |
| `4` | A source is missing, unreadable or invalid |
