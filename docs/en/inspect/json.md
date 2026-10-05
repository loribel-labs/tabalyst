---
title: Inspect JSON and JSONL files
description: Let tabalyst inspect find the collection of records of a JSON, JSONL or NDJSON file, then edit the Inspect file to choose how scan and report read it.
---

Use `tabalyst inspect` to see how Tabalyst understands a JSON or JSONL file
before you scan it, and to change that understanding when it is wrong.
**Tabalyst Inspect** reads the file once, finds which array holds the records,
and writes the answer in a small JSON file beside the source:

```console
tabalyst inspect orders.json
```

```text
Inspect: orders.json-inspect.json
Selection: $.customers[] (the only eligible collection)
```

The Inspect file is named after the full source name plus `-inspect.json`:
`orders.json-inspect.json`, `events.jsonl-inspect.json`,
`events.ndjson-inspect.json`. Its last section, `config`, holds the rules that
`tabalyst scan` and `tabalyst report` apply to this source. The other sections
describe what Inspect found; Tabalyst replaces them each time it inspects. The
structure of the file is in the [Inspect format](format.md).

`tabalyst inspect` accepts files ending in `.json`, `.jsonl` and `.ndjson`, or
non-recursive patterns, and, for workbooks, `.xlsx` and `.xlsm`
(see [Inspect Excel workbooks](excel.md)). Nothing else is accepted: a CSV file
is refused with exit code `2`. It never modifies the source.

## Inspect is optional

`tabalyst scan` and `tabalyst report` work on a JSON file without it. When the
source has no Inspect file, they inspect it themselves, keep the result in
Tabalyst's local storage and use the collection it selects:

```console
tabalyst report orders.json
```

Run `tabalyst inspect` when you want to see or change the rules, or when
Inspect cannot choose.

## When Inspect cannot choose

A JSON file can hold several arrays. Inspect selects a collection only when
that choice is clear:

- the root of the file is an array;
- only one array holds objects; or
- one array holds at least 10 times more objects than the next one.

Otherwise nothing is selected, and `tabalyst scan` and `tabalyst report` stop
with exit code `2` before analyzing anything. For a file with a `customers` and
an `orders` array of the same size:

```text
Error [shop.json]: 2 collections of shop.json are equally plausible. Nothing was analyzed.
Candidates:
  $.customers[] (2 elements)
  $.orders[] (2 elements)
Pass --collection, or run `tabalyst inspect shop.json` and set config.structure.dataset_path in the file it writes.
Choose the collection to analyze:
  tabalyst report shop.json --collection customers
  tabalyst report shop.json --collection orders
Or report every collection: tabalyst report shop.json --all-collections
```

`report` and `scan` print one ready-to-run command per collection, and so does
`tabalyst inspect shop.json`. A short form such as `--collection orders` stands
for `$.orders[]`, and the commands use it whenever the name is plain.
`--all-collections` reports each collection, as `shop.customers.html` and
`shop.orders.html` with their `.json` profiles.

To make the choice stick for `report` too, open `shop.json-inspect.json` and
set the collection in `config`:

```json
"config": {
  "structure": {"dataset_path": "$.orders[]"},
  "flatten": {"enabled": true, "separator": ".", "max_depth": null},
  "arrays": {"mode": "preserve"},
  "errors": {"policy": "strict"}
}
```

`tabalyst report shop.json` then analyzes `$.orders[]`. Tabalyst never picks a
collection by the name of its property, such as `results` or `data`, and never
picks one to let the work go on.

To analyze a collection once without editing a file, pass it on the command
line; `--collection` outranks the Inspect file:

```console
tabalyst scan shop.json --collection "$.customers[]"
```

A file with no usable collection, such as a single object, a number or an
array of plain values, is also unresolved: the Inspect file says so in its
`warnings`, and Tabalyst does not turn a lone object into a one-row dataset.

## Change how the file is read

Everything you may edit is in `config`. Omit a key to keep the default:

| Key | Default | Effect |
| --- | --- | --- |
| `structure.dataset_path` | the selection, or `null` | The collection analyzed, such as `$.customers[]`. For JSONL it is always `$[]`. |
| `flatten.enabled` | `true` | `false` keeps nested objects whole as complex values. |
| `flatten.separator` | `.` | One character joining nested keys in field names, such as `address.city`. |
| `flatten.max_depth` | `null` | Depth, in keys and `[]`, from which an object is kept whole. `null` means no limit. |
| `arrays.mode` | `preserve` | The only supported value: arrays never add records. |
| `errors.policy` | `strict` for JSON, `tolerant` for JSONL | What to do with a malformed record. |

For example, `"max_depth": 2` makes `address` and `address.city` fields and
keeps deeper objects whole, so `tabalyst scan orders.json` lists 13 fields
instead of 23. A value that is not supported is an error that names the key:

```text
Error [orders.json]: Invalid Inspect file orders.json-inspect.json: config.arrays.mode: Value error, Array mode 'explode' is not supported in this version; only 'preserve' is
```

Unknown keys and values of the wrong type are errors too, never ignored. An
Inspect file that cannot be read stops `scan` and `report` with exit code `2`;
Tabalyst never replaces your file with an automatic choice. The
[configuration reference](../reference/configuration.md#scan-settings)
describes each setting.

## Inspect a file again

Run `tabalyst inspect` again after the source changes. The detection and
warnings are rewritten; your `config` is kept:

```text
Inspect: shop.json-inspect.json
Selection: none (several collections are equally plausible)
Configured collection: $.orders[] (kept from the existing file)
```

- `--reset-config` replaces `config` with the detected one.
- `--force` replaces a file that cannot be kept, such as one written for
  another version of the format or with an invalid `config`.
- `--config FILE` seeds a new file from the `scan` section of a
  [configuration file](../reference/configuration.md).

If the source changes and the configured collection disappears, `scan` and
`report` stop with exit code `2`, before writing anything, and use no other
collection:

```text
Error [shop.json]: The collection $.orders[] set in the Inspect file shop.json-inspect.json is not an array of shop.json, so nothing was analyzed. Set config.structure.dataset_path in that file to a collection that exists; `tabalyst inspect shop.json` lists the candidates.
```

A source that changed while the collection still exists keeps its `config`;
`scan` and `report` mention that the file was written for another version of
the source, and scan again: a stored scan is reused only when the source
content, the effective settings and the version of Tabalyst are the same.

## Which setting wins

From lowest to highest priority:

1. Tabalyst defaults;
2. the collection Inspect detected, when the source has no Inspect file;
3. the `scan` section of each `--config` file;
4. the `config` of the Inspect file beside the source;
5. `--collection`, `--delimiter` and `--encoding`.

## JSONL and NDJSON files

A `.jsonl` or `.ndjson` file has one dataset, `$[]`: its records are the lines.
Inspect counts the lines instead of choosing a collection:

```console
tabalyst inspect web-events.jsonl --verbose
```

```text
Inspect: web-events.jsonl-inspect.json
Selection: $[] (the lines of the file)
Format: jsonl
Candidates: 1
  $[] (300 elements)
Warning [web-events.jsonl]: 2 lines are not valid JSON or are too long.
Warning [web-events.jsonl]: 1 line is valid JSON but not an object.
```

Inspect never fails on a bad line: it counts them in `detection.lines` and lists
the first ones, by physical line number, in `warnings`. A scan then follows the
error policy of `config`:

- `tolerant`, the default for JSONL, excludes the bad lines, counts them and
  finishes with status `partial`. The command succeeds with a warning:
  `partial scan, 3 records excluded (invalid_line: 2, not_object: 1).`
- `strict` stops at the first bad line, with exit code `4`:
  `Record 121 (line 121) of web-events.jsonl is not valid JSON (...)`.

Blank lines are ignored. `scan` and `report` do not inspect a JSONL file by
themselves, since there is nothing to choose; an Inspect file only sets the
other rules, such as the policy.

## Messages and exit codes

`--verbose` lists every candidate collection and the informative warnings;
`--quiet` keeps only warnings and errors; `--no-progress` turns off progress.
Messages use standard error.

| Code | Meaning |
| --- | --- |
| `0` | The inspection worked, including when it selected nothing. |
| `2` | Configuration problem: unsupported extension, invalid Inspect file, unresolved collection or missing configured collection (in `scan` and `report`). |
| `4` | The source cannot be read: invalid JSON, invalid UTF-8 or an empty source. No file is written. |
| `1` | Another failure, such as an output that cannot be written. |

A pattern skips files named `*-inspect.json`, and an Inspect file given as an
input is refused: give the source it describes. A source whose own name ends in
`-inspect.json` must be renamed first. Wildcards are resolved by Tabalyst,
including on Windows, so `tabalyst inspect *.json` skips the Inspect files too.

## Python API

```python
import tabalyst

result = tabalyst.inspect("orders.json")
print(result.path)
print(result.document.detection.selection.path)

batch = tabalyst.generate_inspections(["data/*.json", "logs/*.jsonl"])
```

`tabalyst.inspect()` inspects one source as the command does, writes the
Inspect file and returns an `InspectResult`, with the `source`, the `path` of
the file and the `document` as written. It raises an error derived from
`tabalyst.TabalystError` when the inspection fails. `tabalyst.generate_inspections()`
inspects several sources and returns the plan, the successes and the failures.
Both accept `config_path`, `reset_config` and `force`.
