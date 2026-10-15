# Case: errors kept by a sample

Question: when a file holds a few wrong rows, how often does a sample keep at
least one of them? `tabalyst sample --smart` is compared with
`--sample-method random`.

## Input

`input/dirty.csv` is `examples/datasets/insurance-customers.csv` (3,000 rows) with
167 rows changed on purpose, in 21 classes, and the file keeps its 3,000 rows.
`input/truth.json` lists the 0-based data rows of every class.

The errors are injected by the Generate engine from `injections.json` (one
operation per class, `count` rows each, no row in two classes), and
`input/changes.csv` is its change log, the proof that the truth comes from the
generation. Two classes stay in `case.py` because Generate never puts two
classes on a row: `common_anomalies` and `worst_row`, applied afterwards on rows
the log does not name. The design is `docs/dev/generate/test-cases.md`.

| Class | Rows | What was injected |
| --- | --- | --- |
| `email_malformed` | 6 | no `@`, two `@`, empty part, a space |
| `phone_malformed` | 6 | too short, wrong prefix, letters, other layout |
| `postal_malformed` | 6 | missing space, digits only, lower case |
| `birthdate_invalid` | 6 | month 13, `N/A`, other separators, year 2099 |
| `premium_outlier` | 6 | negative, text, 99999999, `1e9`, two commas |
| `id_trailing_space` | 6 | a space after the client identifier |
| `name_long_weird` | 4 | 300 characters, control and bidirectional characters |
| `end_before_start` | 8 | the start and end dates of a contract swapped |
| `novel_category_typo` | 4 | `autoo`, `VIE`, `santé `, `hab` in the contract type |
| `missing_required` | 6 | empty contract identifier |
| `name_leading_space` | 6 | a space or a tab before the first name |
| `name_double_space` | 4 | two spaces inside the last name |
| `city_case_variant` | 6 | the city in capitals (`MONTRÉAL`) |
| `agency_code_length` | 4 | an agency code of 7, 8 or 11 characters |
| `name_zero_width` | 4 | a zero-width space inside the first name |
| `name_replacement_char` | 4 | the replacement character inside the surname |
| `rare_surname` | 6 | surnames that occur nowhere else |
| `city_typo` | 6 | a letter doubled in a city |
| `duplicate_rows` | 6 | rows replaced by a copy of an earlier row |
| `common_anomalies` | 60 | one of six anomalies, each in its own column and 10 times |
| `worst_row` | 3 | all six anomalies of `common_anomalies` in the same row |

Rebuild it with:

```console
python examples/cases/sample-injected-errors/case.py build
```

## Run

```console
tabalyst sample examples/cases/sample-injected-errors/input/dirty.csv --smart --rows 150 --seed 1 -d OUTPUT_DIR
```

The measure runs 3 seeds of `smart` and 8 of `random` at 100, 200 and 400 rows
and prints two tables: per class, the share of runs that keep at least one
injected row, then the mean number of rows of the class a run keeps. The first
table hides a class of several different errors, the second shows it:

```console
python examples/cases/sample-injected-errors/case.py measure OUTPUT_DIR
```

## Result

Measured on 2026-10-15 (lot G3b), sensitive values shown (the default since the
sensitive columns are off for now). Since this lot the injected rows are chosen
by Generate and not by `case.py`: they are other rows of the file, so a class
can move without any change in `smart` (the figures of 2026-10-14 are in the
history of this file).

Share of runs that keep at least one row of the class:

| Error class | Rows | smart 100 | random 100 | smart 200 | random 200 | smart 400 | random 400 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `email_malformed` | 6 | 100% | 62% | 100% | 75% | 100% | 100% |
| `phone_malformed` | 6 | 100% | 12% | 100% | 50% | 100% | 62% |
| `postal_malformed` | 6 | 100% | 12% | 100% | 25% | 100% | 50% |
| `birthdate_invalid` | 6 | 100% | 38% | 100% | 38% | 100% | 75% |
| `premium_outlier` | 6 | 100% | 12% | 100% | 38% | 100% | 50% |
| `id_trailing_space` | 6 | 100% | 12% | 100% | 12% | 100% | 25% |
| `name_long_weird` | 4 | 100% | 0% | 100% | 25% | 100% | 50% |
| `end_before_start` | 8 | 100% | 0% | 100% | 50% | 100% | 50% |
| `novel_category_typo` | 4 | 100% | 38% | 100% | 12% | 100% | 25% |
| `missing_required` | 6 | 100% | 25% | 100% | 100% | 100% | 62% |
| `name_leading_space` | 6 | 100% | 25% | 100% | 38% | 100% | 50% |
| `name_double_space` | 4 | 100% | 38% | 100% | 62% | 100% | 62% |
| `city_case_variant` | 6 | 0% | 25% | 100% | 50% | 100% | 50% |
| `agency_code_length` | 4 | 100% | 100% | 100% | 62% | 100% | 100% |
| `name_zero_width` | 4 | 67% | 0% | 100% | 25% | 100% | 62% |
| `name_replacement_char` | 4 | 67% | 12% | 100% | 25% | 100% | 50% |
| `rare_surname` | 6 | 100% | 100% | 100% | 100% | 100% | 100% |
| `city_typo` | 6 | 0% | 12% | 0% | 62% | 33% | 38% |
| `duplicate_rows` | 6 | 100% | 62% | 100% | 62% | 100% | 100% |
| `common_anomalies` | 60 | 100% | 75% | 100% | 88% | 100% | 100% |
| `worst_row` | 3 | 100% | 25% | 100% | 12% | 100% | 0% |

Mean number of rows of the class a run keeps:

| Error class | Rows | smart 100 | random 100 | smart 200 | random 200 | smart 400 | random 400 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `email_malformed` | 6 | 1.3 | 0.9 | 4.0 | 1.1 | 4.3 | 2.8 |
| `phone_malformed` | 6 | 1.0 | 0.1 | 6.0 | 0.5 | 6.0 | 1.0 |
| `postal_malformed` | 6 | 3.0 | 0.1 | 5.0 | 0.2 | 5.0 | 0.6 |
| `birthdate_invalid` | 6 | 1.7 | 0.6 | 2.0 | 0.5 | 2.3 | 1.1 |
| `premium_outlier` | 6 | 2.7 | 0.1 | 4.0 | 0.5 | 4.7 | 0.9 |
| `id_trailing_space` | 6 | 1.3 | 0.4 | 2.0 | 0.1 | 2.0 | 0.4 |
| `name_long_weird` | 4 | 1.0 | 0.0 | 2.0 | 0.2 | 2.0 | 0.5 |
| `end_before_start` | 8 | 1.0 | 0.0 | 1.0 | 0.8 | 1.7 | 1.4 |
| `novel_category_typo` | 4 | 4.0 | 0.4 | 4.0 | 0.1 | 4.0 | 0.4 |
| `missing_required` | 6 | 1.3 | 0.2 | 1.7 | 1.9 | 2.7 | 1.6 |
| `name_leading_space` | 6 | 1.3 | 0.2 | 4.3 | 0.6 | 4.7 | 0.6 |
| `name_double_space` | 4 | 1.0 | 0.5 | 1.0 | 0.6 | 1.0 | 0.9 |
| `city_case_variant` | 6 | 0.0 | 0.2 | 4.0 | 0.5 | 4.0 | 0.5 |
| `agency_code_length` | 4 | 11.0 | 1.2 | 11.0 | 0.8 | 11.3 | 3.0 |
| `name_zero_width` | 4 | 0.7 | 0.0 | 1.0 | 0.2 | 1.0 | 0.8 |
| `name_replacement_char` | 4 | 0.7 | 0.1 | 1.0 | 0.4 | 1.0 | 0.8 |
| `rare_surname` | 6 | 15.7 | 2.9 | 21.0 | 7.0 | 24.3 | 12.1 |
| `city_typo` | 6 | 0.0 | 0.1 | 0.0 | 0.6 | 0.3 | 0.6 |
| `duplicate_rows` | 6 | 1.0 | 0.9 | 1.3 | 1.0 | 2.3 | 3.9 |
| `common_anomalies` | 60 | 5.3 | 1.0 | 13.3 | 3.6 | 15.7 | 8.1 |
| `worst_row` | 3 | 3.0 | 0.2 | 3.0 | 0.1 | 3.0 | 0.0 |

Reading:

- At 150 rows, the size of the expectations, a smart sample keeps a row of 20
  classes out of 21 on the first seed, as before. A random sample of the same
  size keeps one in a quarter of the runs or less for most of them.
- Compared with the figures of 2026-10-14 (same classes, other injected rows),
  `city_case_variant` at 100 rows goes from 67% to 0% and `city_typo` from
  33%, 67% and 100% (100, 200 and 400 rows) to 0%, 0% and 33%; the other
  classes keep the same shares or gain. Both classes concern the `ville`
  column; why they moved is not investigated here. It is a finding about `smart`
  for a later lot, not a reason to change the case.
- Several classes are scored by the property of the row, not by the injected
  rows, because the source already holds some (empty contract identifiers,
  copied rows, malformed emails, whitespace, capitals, other agency lengths,
  singleton surnames): the sample is right to keep any of them.
- `end_before_start` is now a swap of the real dates of the row, and the sample
  keeps it from 100 rows on the three seeds because the second pass counts the
  records whose start is after their end (`date_order`).
- `worst_row` shows the worst rows: each of its six anomalies has many other
  candidate rows, and a cover counts a target once.
- `city_typo` is the one known gap at 150 rows.

The expectations are in `case.json` and run by `tests/cases/test_cases.py`: every
class but `city_typo` must stay kept, and `city_typo` is `xfail(strict=True)`.
