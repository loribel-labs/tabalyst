---
title: "CLI: tabalyst sample"
description: Every option of tabalyst sample and examples of first, last, random, stratified, stratified-balanced and smart CSV samples, with fixed sizes, percentages and seeds.
---

```console
tabalyst sample INPUT... (--sample-method METHOD | --smart) [OPTIONS]
```

The recommended use:

```console
tabalyst sample customers.csv --smart --rows 1000
```

Creates `<stem>.sample.csv` beside each CSV source (and, for `smart`, `<stem>.sample.json`, its [report](../../sample/format.md), and `<stem>.sample.html`, a page that shows it), or in the folder of `-d`,
without modifying the source. Choose exactly one size: `--rows` or `--percent`.
See [Tabalyst Sample](../../sample/index.md).

## Options

| Option | Description |
| --- | --- |
| `INPUT...` | One or more CSV files or non-recursive glob patterns (required) |
| `--smart` | Recommended. Shortcut for `--sample-method smart`: keeps every value of the columns with few values, at the cost of a scan (reused when current) and a second reading. Not with another `--sample-method` |
| `--sample-method METHOD` | `first`, `last`, `random`, `stratified`, `stratified-balanced` or `smart`. One of `--sample-method` and `--smart` is required |
| `--rows N` | Number of data rows to select. An error with `stratified-balanced`. With `stratified`, at least the number of strata |
| `--percent X` | Percentage of data rows to select, rounded up to a whole row. Exclusive with `--rows`. An error with `stratified-balanced` |
| `--per-value N` | Only with `stratified-balanced`, where it is required: the most rows kept from each stratum (all of a smaller one). The size of the sample is the sum of `min(N, rows of the stratum)`. An error with any other method |
| `--field TEXT` | Field that defines the strata, required by `stratified` and `stratified-balanced`. Repeat it to stratify by the combinations of several fields. An error with any other method |
| `--max-strata N` | Most strata a stratified sample may hold (default 100,000). A file with more stops with an error, and nothing is written. Given explicitly, it also allows a run that a stored scan shows may make too many strata. Only with `stratified` and `stratified-balanced` |
| `--seed N` | Seed that makes a random, stratified, stratified-balanced or smart selection reproducible. With `smart` it defaults to the seed of the scan. An error with `first` and `last`, which keep the file order |
| `-o`, `--output PATH` | Output CSV filename, for a single input. Not with `-d` |
| `-d`, `--output-dir PATH` | Folder for samples named `<stem>.sample.csv` |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md) |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `-f`, `--force` | Replace an existing sample file; a source is never replaced |
| `-y`, `--yes` | Only with `smart` (an error otherwise): start a costly selection without asking. Outside a terminal a costly selection needs it |
| `--no-html` | Only with `smart` (an error otherwise): write the JSON report but not its web page |
| `--help` | Show the options and exit |

## Examples

The recommended sample, which keeps every value of the columns with few values:

```console
tabalyst sample customers.csv --smart --rows 1000
tabalyst sample customers.csv --smart --percent 1 --seed 7
```

The other methods:

```console
tabalyst sample customers.csv --sample-method first --rows 1000
tabalyst sample customers.csv --sample-method last --rows 1000
tabalyst sample customers.csv --sample-method random --percent 5 --seed 42
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
tabalyst sample customers.csv --sample-method stratified --field province --field language --rows 1000
tabalyst sample customers.csv --sample-method stratified-balanced --field province --per-value 100 --seed 42
```

Output location and CSV format:

```console
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
| `2` | Invalid options, including an option the chosen method does not read |
| `3` | A costly smart selection needed a confirmation that could not be asked or was declined; nothing was started |
| `4` | A source is missing, unreadable or invalid |
