---
title: Chart pages of a report
description: What the chart pages that tabalyst report --details writes show, starting with the UpSet plot of the combinations of missing values, how to read them, and why they load Apache ECharts from a CDN.
---

`--details` writes, beside the report, the pages of each column and the **chart
pages**: interactive charts of what the second pass counted exactly. The first one
draws the combinations of columns the records lack a value in.

```console
tabalyst report customers.csv --details
```

```text
customers.html
customers/charts-missing.html
customers/col-01-id.html
...
```

`--details` runs the [second pass](../scan/deep.md) as `--deep` does: it asks first
when it is costly, `--yes` skips the question, and outside a terminal a costly pass
stops with exit code `3` without `--yes`. With `{"deep": {"mode": "off"}}` in the
configuration, `--details` is an error.

## Missing values: `charts-missing.html`

One section per dataset of the report, with the anchor of the dataset
(`charts-missing.html#rows` for a CSV file). Each section shows:

- **Three figures**: the records with every value, those that lack at least one,
  and the combinations seen.
- **The blocks**: the largest groups of columns that go missing together, the same
  sentences as the card of the report, for example:

```text
date_reclamation, montant_reclamation and reclamation_status go missing together: 85,760 records lack all three, at least 97.1% of the records that lack any one of them.
```

- **An UpSet plot.** The bars at the top count the records of each combination;
  the dots below name its columns; the bars on the left count the records that lack
  each column. Each record is in one combination only, so the bars at the top add up
  to the records that lack a value. The plot draws the first 20 combinations; sort
  them by records or by number of columns, and show every combination, those of two
  columns or more, or those that hold one column. On a narrow screen it becomes one
  bar per combination.
- **The tables**: every combination the second pass lists, with its columns, records
  and share, then the columns that lack values, each linked to its column page. The
  tables hold every figure of the plot.

A combination is the exact set of columns a record lacks a value in: a record that
lacks a phone and a reference and has every other value is in the combination
*phone, ref*, not in *phone* nor in *ref*. Missing means an empty cell, a blank one
or a null marker of the configuration, as the scan counts it. The counts are exact.
When a file has more combinations than `deep.missing.max_patterns`, the records of
the later ones are counted together and the page says so. See [Combinations of
missing values](../scan/deep.md#combinations-of-missing-values).

The report links to the page from the *Columns missing together* card of the
dataset and from its navigation; a column page links to it when the column lacks
values. No page is written when no dataset has two columns that lack values; the
command says why:

```text
Warning [customers.csv]: no chart of the missing values for rows: fewer than two columns lack a value
```

## A library from a CDN

The chart pages draw with [Apache ECharts](https://echarts.apache.org/), loaded from
jsDelivr. The address names one version and the page checks the file against its
hash, so it cannot be swapped; no data of the report is sent, and the page asks the
browser not to send its address. The report itself and the column pages load
nothing from outside and read without a network.

Without a network, or behind a proxy that blocks the CDN, each chart shows a message
in its place and the tables stay: they hold the same figures.
