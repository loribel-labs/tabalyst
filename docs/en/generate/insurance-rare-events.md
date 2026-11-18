---
title: Insurance rare events
description: How the rare_events profile of the insurance example injects a few exact, very rare cases (one reused key, five future birth dates, 500 foreign agencies), refuses a file that is too short, and tells how likely a sample is to miss each case.
---

The `rare_events` profile of the insurance example injects defects that are
rare on purpose: from one single case to 500, whatever the size of the file.
It exists to test whether a method, such as a sampling, a data quality
check or a detector, still finds the cases that make up 0.001 to 0.5 percent
of the rows. It is a [scenario profile](insurance-ground-truth.md): every
case belongs to a named scenario and the run writes its ground truth.

```console
tabalyst generate --example insurance --rows 100000 -d out/ --anomaly-profile rare_events
```

```text
Created: out/insurance-principal.csv
Created: out/insurance-ontario.csv
Created: out/insurance-quebec.csv
Created: out/insurance-combined.csv
Created: out/insurance-combined.rare_events.csv
Created: out/insurance-combined.rare_events.changes.csv
Created: out/insurance-combined.rare_events.summary.json
Created: out/insurance-combined.rare_events.truth.csv
Created: out/insurance-combined.rare_events.rules.json
Created: out/insurance-combined.rare_events.metrics.json
Created: out/insurance-combined.rare_events.manifest.json
Done in 35.0s, 1,251 cells changed
```

The profile keeps the 34 columns of the default file. It needs at least
**100,000 rows**: with fewer, the command stops before it writes anything,
because 500 cases in a short file are no longer rare.

```text
Error: Profile rare_events needs at least 100,000 rows on insurance-combined (below that its rare cases are not rare); 99,999 requested.
```

## The scenarios

The counts are absolute: they do not grow with the file. Each scenario has a
rarity level, which is the band its total falls in.

| Scenario | Cases | Level | The case |
| --- | ---: | --- | --- |
| `R01` | 1 (on 2 rows) | `single` | A contract identifier reused on a second contract |
| `R02` | 5 | `extremely_rare` | A birth date a century later, so in the future (for a reference date before 2040) |
| `R05` | 20 | `very_rare` | An annual premium multiplied by 100 |
| `R06` | 25 | `very_rare` | A start date written in the convention of another branch |
| `R07` | 50 | `very_rare` | A postal code of another province than the customer's |
| `R08` | 50 | `very_rare` | A contract that ends before it starts |
| `R10` | 100 | `rare` | An annual premium replaced by text (`N/A`, `inconnu`, `à venir`) |
| `R11` | 250 | `uncommon` | A contract status that is not one of the four statuses |
| `R12` | 500 | `uncommon` | An agency code that belongs to another branch |
| `B01` | 100 | `rare` | A contract that ends the day it starts (valid) |
| `B02` | 100 | `rare` | A record modified the day it was created (valid) |

| Level | Cases of a scenario |
| --- | --- |
| `single` | 1 |
| `extremely_rare` | 2 to 9 |
| `very_rare` | 10 to 74 |
| `rare` | 75 to 199 |
| `uncommon` | 200 to 999 |
| `frequent` | 1,000 or more |

The count is a promise: the profile applies exactly that many cases, or the
command fails and publishes nothing. If a scenario asks for more cases than
the file has rows that can take them, the message names the operation and the
rows available.

## One case on two rows

`R01` copies the contract identifier of one of the 1,000 rows before it, as a
double entry would. The case is one, on two rows, so the truth tells it with
two `relational` lines that share a `group_id`, `R01-<first row>`, one for
each row. Each row keeps its own identifier as `canonical_value`: the
identifier the second contract should have. `M21` also reports the two rows
as `rule_violation` lines.

```text
kind,scenario_id,rule_id,group_id,event_id,row_number,column,canonical_value
relational,R01,M21,R01-32669,,32669,id_contrat,CTR-1000032668
relational,R01,M21,R01-32669,370,33555,id_contrat,CTR-1000033554
```

## Valid cases that look like defects

`B01` and `B02` are not defects. They sit on the boundary that a rule allows,
so a check that flags them is wrong. Their truth lines have the kind
`valid_atypical`, the severity `info` and the expected detection `none`, and
the rules `M01` and `M02` do not report them. Use them to measure false
positives. The clean file holds no such case: they are written by the
profile, so they appear in `changes.csv` too.

## How likely is a sample to miss a case

`metrics.json` holds, for each scenario, the exact probability that a uniform
sample without replacement holds none of its cases, for samples of 500, 1,000,
5,000, 10,000 and 50,000 rows. It is computed for the rows of your file, not
copied from a table:

```json
"R02": {
  "cases": 5,
  "probability": {
    "500": 0.9752482630325081,
    "1000": 0.9509890892755107,
    "5000": 0.7737768648540725,
    "10000": 0.5904834388286798,
    "50000": 0.031246875015626563
  },
  "reason": null
}
```

Here a sample of 5,000 rows out of 100,000 misses all five future birth
dates 77 times in 100. A sample larger than the file has no probability
(`null`). `R01` has none either: its case spans two rows, so the single-row
formula does not apply, and the entry says `"reason": "multi_row_case"`.

For 275,000 rows and a sample of 5,000, a scenario of 500 cases is missed
0.01 percent of the time, one of 100 cases 16 percent, 50 cases 40 percent,
5 cases 91 percent and a single case 98 percent.

## Next steps

- [Insurance ground truth files](insurance-ground-truth.md) explains the
  truth, rules, metrics and manifest files and how to declare a scenario.
- [Generate insurance customers](insurance.md) describes the columns and the
  other profiles.
- The [CLI reference](../reference/cli/generate.md) lists every option.
