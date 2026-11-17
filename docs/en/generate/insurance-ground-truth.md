---
title: Insurance ground truth files
description: What the truth.csv, rules.json, metrics.json and manifest.json files of an insurance scenario profile hold, and how to declare the scenarios and rules that produce them.
---

A **scenario profile** of the insurance example injects defects that each
belong to a named test case, a scenario, and writes the **ground truth** of
the run beside the altered CSV: what was injected, which cells really differ
from the clean file, which rows break a rule, with the exact counts and the
fingerprint of every file. An evaluation of a detection, cleaning or sampling
method reads these files instead of guessing what the generator did.

```console
tabalyst generate my-insurance/ --rows 3000 -d out/ --anomaly-profile v2_demo
```

```text
Created: out/insurance-principal.csv
Created: out/insurance-ontario.csv
Created: out/insurance-quebec.csv
Created: out/insurance-combined.csv
Created: out/insurance-combined.v2_demo.csv
Created: out/insurance-combined.v2_demo.changes.csv
Created: out/insurance-combined.v2_demo.summary.json
Created: out/insurance-combined.v2_demo.truth.csv
Created: out/insurance-combined.v2_demo.rules.json
Created: out/insurance-combined.v2_demo.metrics.json
Created: out/insurance-combined.v2_demo.manifest.json
Done in 1.0s, 51 cells changed
```

| File | What it holds |
| --- | --- |
| `<dataset>.<profile>.truth.csv` | One line per cell or row and per kind of fact |
| `<dataset>.<profile>.rules.json` | The rules the profile tests, with the conventions to read the cells |
| `<dataset>.<profile>.metrics.json` | Exact counts per scenario, rule, category and kind |
| `<dataset>.<profile>.manifest.json` | Seed, date, versions, scenarios and the SHA-256 of every other file |

The `dirty_realistic`, `dirty_stress` and `rule_breaks` profiles are not
scenario profiles: they write the same files as before and no truth file.
The JSON formats are experimental during the beta (`format_version` `0.2.0`,
`format_revision` 1): their structure can still change.

## Declare a scenario profile

A profile is a scenario profile when its operations declare `scenario_id`.
Every operation then declares `scenario_id`, `category` and `severity`, uses
`count` (an exact number of rows, never `rate`) and targets the combined
dataset `insurance-combined`, whose `filiale` column tells how to read each
date. Copy the insurance example package (the `generate_examples/insurance`
directory of the installed `tabalyst` package) and add a profile to its
`dataset.yaml`:

```yaml
anomaly_profiles:
  v2_demo:
    targets: [insurance-combined]
    operations:
    - kind: swap
      column: date_debut
      value: date_fin
      count: 20
      scenario_id: R08
      rule_id: M01
      category: business_rule_violation
      severity: major
      rarity_level: very_rare
      expected_detection: cross_column
      description: Contract ending before it starts
    - kind: replace
      column: statut_contrat
      value: inconnu
      count: 6
      scenario_id: R11
      rule_id: M23
      category: semantic_invalid
      severity: major
      expected_detection: domain
    - kind: format
      column: date_debut
      value: date_mdy_iso
      count: 5
      when: {filiale: quebec}
      scenario_id: F19
      category: contextual_invalid
      severity: major
      expected_detection: contextual
```

| Key | Meaning |
| --- | --- |
| `scenario_id` | The test case, such as `R08`: capitals, digits and `_`, 16 characters at most |
| `category` | `format_variant`, `format_invalid`, `semantic_invalid`, `business_rule_violation`, `contextual_invalid` or `valid_atypical` |
| `severity` | `info`, `minor`, `major` or `critical` |
| `rule_id` | The rule of `rules.yaml` the case breaks or tests (optional) |
| `rarity_level` | `single` (1 case), `extremely_rare` (2 to 9), `very_rare` (10 to 74), `rare` (75 to 199), `uncommon` (200 to 999) or `frequent` (1,000 or more); the total of the scenario must fall in the band (optional) |
| `expected_detection` | The kinds of check that should react, joined by `\|`: `syntactic`, `domain`, `cross_column`, `uniqueness`, `contextual`, `statistical`, or `none` (optional) |
| `root_cause_id` | Groups the effects of one incident, such as `ontario_import` (optional) |
| `description` | One line of free text, copied to the manifest (optional) |
| `can_overlap`, `conflicts_with`, `requires` | Whether the scenario may share rows with others, the scenarios it never shares a row with, and the columns it needs (optional) |

The operations of one scenario declare the same category, severity, rule,
level, cause, detection and description. A wrong value stops the command
with the profile and the operation index, before anything is generated.
A `valid_atypical` scenario must have the severity `info` and the detection
`none`: it describes a value that is not a defect.

A profile may also declare `min_rows`, the fewest rows it accepts (at least
its largest count); the command stops below it. The kinds `reuse_value`
(repeat the value of one of the 1,000 rows before) and `copy_column` (write
the value of another cell of the row, in `value`) and the `format` values
`times_100`, `date_plus_century` and `postal_other_province` serve the
[rare events profile](insurance-rare-events.md); they work in scenario
profiles only.

## The truth file

`truth.csv` is UTF-8 with a header and a comma, sorted by row, column and
kind. A cell can have several lines, one per kind:

```text
truth_id,kind,scenario_id,rule_id,category,severity,rarity_level,root_cause_id,group_id,event_id,row_number,column,canonical_value,expected_detection
1,rule_violation,R08,M01,business_rule_violation,major,very_rare,,,1,9,,,cross_column
2,injected,R08,M01,business_rule_violation,major,very_rare,,,1,9,date_debut,2017-11-09,cross_column
3,net_difference,R08,M01,business_rule_violation,major,very_rare,,,1,9,date_debut,2017-11-09,cross_column
4,injected,R08,M01,business_rule_violation,major,very_rare,,,1,9,date_fin,2027-01-03,cross_column
5,net_difference,R08,M01,business_rule_violation,major,very_rare,,,1,9,date_fin,2027-01-03,cross_column
6,rule_violation,R11,M23,semantic_invalid,major,extremely_rare,,,2,27,,,domain
```

| `kind` | The line says |
| --- | --- |
| `injected` | An operation changed this cell: one line per line of `changes.csv`, with the same `event_id` |
| `net_difference` | The final cell differs from the clean cell. A cell that a later change restored has events but no such line |
| `rule_violation` | The final row breaks a rule of `rules.json`; `column` is empty because the line is about the row |
| `relational` | A case that shows only by comparing rows, such as a key reused on two rows: one line per row, sharing a `group_id` such as `R01-12` |
| `valid_atypical` | The cell is valid but a naive detector would flag it: a case of a `valid_atypical` scenario, with severity `info` and detection `none` |

`row_number` counts the header as line 1, like `changes.csv`. The
`canonical_value` is what the clean cell means, written one way: a date in
ISO 8601 (the Quebec cell `05-10-2026` is `2026-10-05`), an amount as a plain
decimal, a text trimmed in NFC. So a date rewritten in another branch's
convention keeps its intended day in the truth. A `rule_violation` line takes
its category and severity from the rule, and its scenario from the last
change of the row that touched a column of the rule. Repeated keys share a
`group_id` that names the rule and the first row, such as `M21-12`.

## Rules

The rules are data, not code. The insurance package declares them in
`rules.yaml`, and `rules.json` copies the ones the profile names with
`rule_id`. Before the files are published, the generator checks that the
clean file satisfies every rule of the profile; a clean row that breaks one
stops the command and nothing is written.

| Rule | What must hold |
| --- | --- |
| `M01` | `date_fin` on or after `date_debut`, when there is an end |
| `M02` | `date_modification` on or after `date_creation` |
| `M03` | `date_naissance` before `date_debut` |
| `M04` | `date_naissance` from 1900-01-01 to the reference date |
| `M14` | `prime_annuelle` above zero |
| `M21` | `id_contrat` unique |
| `M23` | `type_contrat` and `statut_contrat` among the known values |

A rule has its `columns`, an optional `when` (where it applies), an `assert`
(what must hold), `exceptions` (cases allowed anyway) and, for people, its
`valid_boundaries`. The operators are `eq`, `gt`, `gte`, `lt`, `lte`,
`between`, `in`, `not_in`, `regex`, `not_empty`, `empty`, `unique`,
`implies`, `and`, `or` and `not`. An operand is a column name, a constant
`{value: "0"}` or the reference date `{param: as_of_date}`, read as a `date`,
a `decimal` or a `text`. A cell date is read with the format of its branch
(`conventions.date_format` of `rules.json`).

A test of a value is unknown when the cell is empty or does not read as its
type, and an unknown test is not a violation. In the run above, the five
Quebec start dates rewritten as ISO (`F19`) cannot be read as Quebec dates,
so they are format defects and do not count as end-before-start
violations: `M01` has 20 violations, those of `R08`. An empty or malformed
value is the subject of a presence or format rule.

## Metrics and manifest

`metrics.json` recounts everything from the files written: the rows per
branch, the events, changed cells, distinct changed cells and net
differences, and for each scenario the cases requested and applied, the rows
touched and the eligible population (the rows each operation could change in
the clean file). It also gives the violations per rule, the cases per
category, the truth lines per kind and, for each scenario, the probability
that a sample misses all its cases (see
[Insurance rare events](insurance-rare-events.md)):

```json
{
  "rules": {"M01": 20, "M23": 6},
  "counts": {"events": 31, "changed_cells": 51,
             "distinct_changed_cells": 51,
             "net_differences": 51}
}
```

`manifest.json` holds what fixes every byte of the run: `seed`,
`as_of_date`, `rows`, `profile`, `output_profile`, the versions of
Tabalyst, of the package and of the generation logic (`generation_version`),
the scenarios with their description, operations and expected cases, the
columns of `truth.csv`, and the name, size and SHA-256 of every other file of
the run. The same package, options and version give the same bytes.

The JSON Schemas of the three JSON files are in the `schemas/` directory of
the installed `tabalyst` package (`tabalyst.generate.rules.schema.json`,
`tabalyst.generate.metrics.schema.json`,
`tabalyst.generate.manifest.schema.json`).

## Next steps

- [Insurance rare events](insurance-rare-events.md) describes the first
  packaged scenario profile, `rare_events`.
- [Generate insurance customers](insurance.md) describes the columns, the
  branches and the other profiles.
- [Tabalyst Generate](index.md) explains packages and anomaly operations.
- The [CLI reference](../reference/cli/generate.md) lists every option.
