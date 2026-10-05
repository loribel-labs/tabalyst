---
title: Report JSON and JSONL files
description: Turn a JSON file into an interactive HTML report and a JSON profile with tabalyst report, one view per collection of records.
---

`tabalyst report` reads JSON files as well as CSV files:

```console
tabalyst report orders.json
```

This creates `orders.report.html` (the report), `orders.report.json` (the
profile) and `executions.json` beside `orders.json`. The `.report` part keeps
the profile from replacing the source. `-o` and `-d` work as for CSV files.

## JSONL files

Files ending in `.jsonl` or `.ndjson` hold one JSON object per line. They are
reported the same way, as one dataset `$[]` whose records are the lines:

```console
tabalyst report events.jsonl
```

This creates `events.report.html` and `events.report.json`. A line that is not
valid JSON, is not an object, holds an object with a duplicate key or is longer
than `scan.limits.max_line_bytes` is excluded and counted; the report lists it
in its *excluded records* issue, with the physical line numbers. The report
is then partial and the command prints a warning. Set `errors.policy` to
`strict`, in the `config` of an [Inspect file](../inspect/json.md#jsonl-and-ndjson-files)
or in `scan.errors.policy`, to stop at the first such line instead. Blank
lines are ignored, and a file without any record line is an error.

## Dataset

The report analyzes one **collection** of records, chosen by
[Tabalyst Inspect](../inspect/json.md): a top-level array, or an array inside
a top-level object, such as `customers` in `{"customers": [...]}`. It is the
dataset of the report, such as `$.customers[]`. When the source has no Inspect
file, Tabalyst inspects it by itself and uses the collection it selects. The
values outside the collection are not analyzed.

When several arrays are equally plausible, or the file has no collection of
objects, the report stops with exit code `2` before analyzing anything and lists
the candidates. Run `tabalyst inspect data.json` and set
`config.structure.dataset_path` in the file it writes, or pass the collection
with `--collection`, which outranks the Inspect file:

```console
tabalyst report data.json --collection products
tabalyst report data.json --collection '$.catalog.products[]'
```

The command that stops lists one ready-to-run command per collection. To report
all of them in one command, use `--all-collections`, which writes
`data.<collection>.html` and `data.<collection>.json` for each array (add `-d` to
choose the folder):

```console
tabalyst report data.json --all-collections -d reports
```

A collection is written as a path, `$.catalog.products[]`, or in the short
form without `$` and `[]`, `catalog.products`: the keys that lead to the array.
The root array of a file is `$[]`, or `.` in the short form. A key made of
digits, such as the category in `groups.121`, is accepted as it is; any other
key that is not a plain identifier is quoted, as in `["my key"]`.

A JSON file whose only content is a single object, a
number or an array of plain values has no collection.

To report on several collections of one file, pass `--collection` once for
each, or list them in the `scan.json.collections` setting of a
[configuration file](../reference/configuration.md) passed with `--config`. The
report then has one dataset per collection, and a **Dataset** selector in the
report navigation switches between them. Each dataset has its own overview,
columns, issues and data sample. Rules set in the Inspect file, such as the
flatten depth, apply to the source whichever way the collections are chosen.

## Columns

Every field holding strings, numbers, booleans or nulls is a column, named by
its path from the record:

| JSON record | Columns |
| --- | --- |
| `{"id": 1, "address": {"city": "Paris"}}` | `id`, `address.city` |
| `{"tags": ["a", "b"]}` | `tags[]` |
| `{"orders": [{"total": 3}]}` | `orders[].total` |

Objects and arrays themselves are not columns, unless the flatten depth
(`config.flatten.max_depth` of the Inspect file, or the scan setting
`json.flatten.max_depth`) keeps them whole: at that depth, an object or an array
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
[JSON profile reference](json-profile.md).
