# Case: errors kept by a sample

Question: when a file holds a few wrong rows, how often does a sample keep at
least one of them? `tabalyst sample --smart` is compared with
`--sample-method random`.

## Input

`input/dirty.csv` is `examples/input/insurance-customers.csv` (3,000 rows) with
62 rows changed on purpose and 6 rows copied, in 11 classes. `input/truth.json`
lists the 0-based data rows of every class.

| Class | Rows | What was injected |
| --- | --- | --- |
| `email_malformed` | 6 | no `@`, two `@`, empty part, a space |
| `phone_malformed` | 6 | too short, wrong prefix, letters, other layout |
| `postal_malformed` | 6 | missing space, digits only, lower case |
| `birthdate_invalid` | 6 | month 13, `N/A`, other separators, year 2099 |
| `premium_outlier` | 6 | negative, text, 99999999, `1e9`, two commas |
| `id_trailing_space` | 6 | a space after the client identifier |
| `name_long_weird` | 4 | 300 characters, control and bidirectional characters |
| `end_before_start` | 8 | contract ends in 2001 and starts in 2030 |
| `novel_category_typo` | 4 | `autoo`, `VIE`, `santé `, `hab` in the contract type |
| `missing_required` | 6 | empty contract identifier |
| `duplicate_rows` | 6 | rows copied at the end of the file |

Rebuild it with:

```console
python examples/cases/sample-injected-errors/case.py build
```

## Run

```console
tabalyst sample examples/cases/sample-injected-errors/input/dirty.csv --smart --rows 100 --seed 1 -d OUTPUT_DIR
```

The measure runs 3 seeds of `smart` and 8 of `random` at 100, 200 and 400 rows
and prints, per class, the share of runs that keep at least one injected row:

```console
python examples/cases/sample-injected-errors/case.py measure OUTPUT_DIR
```

## Result

Measured on 2026-10-14, sensitive values shown (the default since the sensitive
columns are off for now).

| Error class           | Rows | smart 100 | random 100 | smart 200 | random 200 | smart 400 | random 400 |
| --------------------- | ---- | --------- | ---------- | --------- | ---------- | --------- | ---------- |
| `email_malformed`     | 6    | 100%      | 25%        | 100%      | 25%        | 100%      | 100%       |
| `phone_malformed`     | 6    | 100%      | 12%        | 100%      | 62%        | 100%      | 25%        |
| `postal_malformed`    | 6    | 100%      | 25%        | 100%      | 38%        | 100%      | 75%        |
| `birthdate_invalid`   | 6    | 100%      | 25%        | 100%      | 12%        | 100%      | 50%        |
| `premium_outlier`     | 6    | 100%      | 12%        | 100%      | 25%        | 100%      | 50%        |
| `id_trailing_space`   | 6    | 100%      | 25%        | 100%      | 38%        | 100%      | 75%        |
| `name_long_weird`     | 4    | 100%      | 0%         | 100%      | 25%        | 100%      | 50%        |
| `end_before_start`    | 8    | 100%      | 12%        | 100%      | 0%         | 100%      | 75%        |
| `novel_category_typo` | 4    | 100%      | 12%        | 100%      | 25%        | 100%      | 50%        |
| `missing_required`    | 6    | 0%        | 12%        | 33%       | 38%        | 33%       | 75%        |
| `duplicate_rows`      | 6    | 0%        | 62%        | 33%       | 75%        | 100%      | 88%        |

Reading:

- A smart sample keeps a row of nine classes out of eleven from 100 rows, where
  a random sample of the same size keeps one in a quarter of the runs or less.
- Two gaps remain: `missing_required` (an empty cell in a column with many
  values has no target) and `duplicate_rows` (the target exists but cannot be
  evaluated yet). Random does better there only because it needs no target.
- `end_before_start` is kept because the injected dates are also the earliest
  and the latest of their columns; the sample does not yet look for a start
  after its end.
- With the sensitive columns masked, `email_malformed` and `phone_malformed`
  were never kept at 100 rows (0%): a masked column has no pattern and no
  target.

The expectations are in `tests/cases/test_sample_injected_errors.py`: the nine
kept classes must stay kept, and the two gaps are `xfail(strict=True)`.
