---
title: Report JSON files
description: Turn a JSON file into an interactive HTML report and a JSON profile with tabalyst report, one view per collection of records.
---

`tabalyst report` reads JSON files as well as CSV files:

```console
tabalyst report orders.json
```

This creates `orders.report.html` (the report), `orders.report.json` (the
profile) and `executions.json` beside `orders.json`. The `.report` part keeps
the profile from replacing the source. `-o` and `-d` work as for CSV files.

## Datasets

Tabalyst finds the records of the file as `tabalyst scan` does: a top-level
array is one collection, and in a top-level object every array reachable
through objects, such as `customers` in `{"customers": [...]}`, is a
collection. Each collection is a dataset of the report, such as
`$.customers[]`. The values of the document outside the collections form the
dataset `$`, shown only when there are some.

When the file has several datasets, a **Dataset** selector in the report
navigation switches between them. Each dataset has its own overview, columns,
issues and data sample.

To choose the collections, list them in the `scan.json.collections` setting of
a [configuration file](../reference/configuration.md) passed with `--config`.
See [Scan CSV and JSON files](scan-files.md) for how collections are found.

## Columns

Every field holding strings, numbers, booleans or nulls is a column, named by
its path from the record:

| JSON record | Columns |
| --- | --- |
| `{"id": 1, "address": {"city": "Paris"}}` | `id`, `address.city` |
| `{"tags": ["a", "b"]}` | `tags[]` |
| `{"orders": [{"total": 3}]}` | `orders[].total` |

Objects and arrays themselves are not columns, unless the scan setting
`json.flatten.max_depth` keeps them whole: at that depth, an object or an array
is one column of type `complex` and its content is not analyzed. A field absent from a record is
missing, like a null or an empty string. In the data sample, an absent field
shows `absent`, and the values of a field under an array are joined with `, `.

## Structure

The **JSON structure** section lists every path of the records, objects and
arrays included, such as `orders`, `orders[]` and `orders[].total`, with:

- the JSON types found at the path;
- presence: the share of parent objects holding the field, and how many do
  not;
- for arrays, their lengths (minimum, maximum, mean) and how many are empty;
- the role of the path: a column, a container, or a collection analyzed as
  its own dataset.

CSV reports have no structure section: every row has the same columns.

## Detectors and formats

The **Detectors** section lists, for each column of CSV and JSON reports, what
the scan detectors recognized: emails, phone numbers, dates, numbers and the
other built-in detectors, with the share of values they matched and the
formats they found. The detector marked **primary** gives the column its
semantic type.

The structure of the profile is described in the
[JSON profile reference](../reference/json-profile.md).
