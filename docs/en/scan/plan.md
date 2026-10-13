---
title: Plan the analyses a scan could add
description: What tabalyst scan --plan shows, how the planner chooses analyses under memory, cell and CPU limits, when a run would ask for a confirmation, the decisions and reasons in a plan, the advice on stratified sampling and the plan of a smart sample, and the Python functions that return it.
---

`tabalyst scan --plan` shows which further analyses would be useful and possible
for a file, what each would cost, and which ones the scan already answers. It
runs none of them and writes nothing beside the source. The plan is experimental
in the beta. Every analysis it proposes can be run with [`tabalyst scan
--deep`](deep.md), and `tabalyst report` runs by itself the ones that are useful and
cheap.

```console
tabalyst scan customers.csv --plan
```

If the scan of the file stored by Tabalyst is current (same content, settings
and version), only the planning runs. Otherwise the first pass runs and is
stored, as `tabalyst scan` does. The plan goes to standard output; messages go to
standard error.

```text
Plan for basic.csv (plan 84f918d7e204, planner 1).
22 candidates: 5 selected, 16 already answered by the scan, 1 left out.

Selected:
  1. temporal_distribution [period_counts]: rows / joined (up to 1.7 KiB, CPU moderate, automatic)
  2. pattern_validation [compiled_matcher]: rows / id (up to 6.0 KiB, CPU moderate, automatic)
  3. pattern_validation [compiled_matcher]: rows / name (up to 6.0 KiB, CPU moderate, automatic)
  4. pattern_validation [compiled_matcher]: rows / amount (up to 6.0 KiB, CPU moderate, automatic)
  5. pattern_validation [compiled_matcher]: rows / notes (up to 6.0 KiB, CPU moderate, automatic)

Not applicable:
  1 x the field mixes types, so a typed analysis would be unreliable

A second reading of the source is needed (30 cells, CPU very_low). Memory: 24.0 MiB to 24.0 MiB, about 24.0 MiB.
Estimated time: under a second (a guide from the first pass, not a promise).
Running it would not ask for a confirmation.
```

## What the plan contains

The planner looks at the scan, never at the source. For each field it considers
the analyses that concern it:

| Analysis | What it adds |
| --- | --- |
| `exact_frequencies` | The exact count of every distinct value of a field of at most 1,000 values (runs with `--deep`) |
| `numeric_histogram` | The spread of the numbers, with exact median and quantiles when the integers have a small range (runs with `--deep`) |
| `length_distribution` | The lengths of the text (runs with `--deep`) |
| `exact_distinct` | The exact number of distinct values of an identifier-like field (runs with `--deep`) |
| `pattern_validation` | The structural patterns counted on every occurrence, not only on a sample of the distinct values (runs with `--deep`). Needs no reading when the scan holds every distinct value with its exact count |
| `temporal_distribution` | The dates counted by day, month or year, as written (runs with `--deep`). Also for a column of datetimes |
| `datetime_parts` | The dates by year-month, day of the week and hour, with the ambiguous dates read under each order, the invalid ones by reason and the dates after a bound you give. Asked for, or run with `--deep`, never by itself |
| `numeric_shape` | The asymmetry, kurtosis, outliers of Tukey and decimals of a numeric field, with a logarithmic and an equal-count histogram. Asked for, or run with `--deep`, never by itself |
| `position_drift` | The records, values and missing values of each tenth of the file for a field, and its values by tenth when it has few different ones. Asked for, or run with `--deep`, never by itself |
| `missing_matrix` | For a column that lacks a value, the records where it lacks one together with each other column. One candidate per column, one counting for the dataset. Asked for, or run with `--deep`, never by itself |
| `array_profile` | The number of arrays of every length for a JSON field that holds arrays. Asked for, or run with `--deep`, never by itself |
| `structure_variants` | The sets of keys the objects of a JSON field have, and the records themselves under the field `$`. Asked for, or run with `--deep`, never by itself |
| `text_profile` | The words, lines and digits of the texts of a field whose values reach 80 characters. Asked for, or run with `--deep`, never by itself |
| `fingerprint_distinct` | The distinct values of a field whose values are too long for the exact set, told apart by a 128-bit fingerprint, and the texts found more than once. Asked for, or run with `--deep`, never by itself |
| `sensitive_forms` | The masks of the values of a masked field and their classes, without a value or a count below a floor. Asked for, or run with `--deep`, never by itself. `exact_distinct` also applies to a masked or hidden field, as two numbers. Both are off until `deep.sensitive.enabled` is set |
| `residual_values` | The values that patterns and detectors leave out, with their exact counts, and each pattern's example and distinct values (runs with `--deep`). Needs no reading when the scan holds every distinct value with its exact count, and then gives no record |
| `duplicates_report` | The values found more than once in a column of almost all different values, with their counts (runs with `--deep`). Also the repeated combinations of two columns, when you ask for them |

Each candidate gets one decision:

- **selected**: asked for, or useful and cheap enough to be chosen
  automatically. Selected analyses share one reading of the source.
- **already_satisfied**: the scan already holds the answer, for example an
  enumeration of 17 values whose counts are all listed. It is never run again,
  and the plan says where the answer is.
- **rejected**: not applicable to the field (no values, a mixed type, a sensitive
  field whose values are withheld, except for the counts that carry no value,
  `exact_distinct` and `sensitive_forms`, when `deep.sensitive.enabled` is set), of too little benefit, or beyond the memory
  budget. A rejection never says the analysis is impossible.

A plan contains no value from your data, and no date: the same scan gives the
same plan on any machine, whatever the number of workers.

## Pairs of columns

Most analyses concern one column. `pearson_correlation` concerns a pair of numeric
columns of the same dataset, and a file of 100 numeric columns has 4,950 pairs, so
the planner does not list them all. It scores every pair of the eligible columns
on the rows the scan sampled, which reads no source, and lists the best.

A pair is a candidate like another, with `partner` (the second field) and
`exploration`, what the sample says of it:

```json
{"id": "pearson_correlation:rows:column_2+column_3",
 "display": "price and cost", "partner": "column_3",
 "exploration": {"scope": "interior_rows", "pairs": 900,
                 "coefficient": 0.987977, "lower": 0.986307,
                 "upper": 0.989444, "score": 0.986307}}
```

`scope` says which rows were used: `interior_rows` (the sampled rows of the interior
of the file, not uniform over it) or `all_rows` (a complete sample, the whole file).
`lower` and `upper` bound the coefficient at 95%, and `score` is the lower bound of
its absolute value, which ranks the pairs and gives the benefit (100 times the score,
45 at least for an automatic choice). With the rank correlation on
(`deep.pearson.rank_bins`), the exploration also has `rank_coefficient`, `rank_lower`,
`rank_upper` and `rank_score` for the Spearman coefficient of the sample, and the
benefit is that of the larger of the two scores. The figures are rounded to six decimals. A pair
without a score, because too few rows have both numbers or a column does not vary,
carries a `reason` instead of a coefficient, and is not listed unless you asked for it.

The plan also has a `relations` member that says what the exploration did, for each
dataset with two numeric columns: the rows it used, the numeric columns, the
columns kept, the columns it left out by reason (`constant`, `identifier_like`,
`sensitive_exposure`, `repeated_path`, `not_in_sample`, `too_few_values`,
`column_budget`), the pairs that were possible, scored and left undefined (by
reason), the pairs listed, and the `work` spent, the pairs times the rows compared.
A dataset that could not be explored has `unavailable`: `no_sample`,
`sample_reduced` or `too_few_rows`.

The work of the exploration is bounded like the rest: `deep.pearson.max_columns`
(50) and `deep.pearson.max_work` (1,000,000 pairs times rows). Beyond them the
least present columns are left out and counted as `column_budget`. The planner lists
20 pairs at most (`max_candidates`) and picks 8 at most by itself
(`automatic_pairs`); a pair it did not pick says `pairs_budget`.

## Tables of a category against a feature

`category_crosstab` concerns a column of a few values, the category, and another
column, whose pattern, length, prefix or value (its **feature**) it counts for each
category. Like a pair, a table is a candidate with a `partner` (the column of the
feature), here with the feature in its parameters, and its exploration says what the
row sample shows. The order matters: `column_1>column_2` is the category `column_1`
against the column `column_2`.

```json
{"id": "category_crosstab:rows:column_1>column_2:pattern",
 "display": "region and client_id (pattern)", "partner": "column_2",
 "parameters": {"feature": "pattern", "max_categories": 30, "examples": 3,
                "rule_purity": 90, "rule_support": 30},
 "exploration": {"scope": "interior_rows", "rows": 900, "categories": 12,
                 "classes": 5, "purity": 0.964853, "cramers_v": 0.944099,
                 "score": 0.938529, "stable": true}}
```

`score` is the corrected Cramér's V of the table on the sample, which ranks the
tables and gives the benefit (100 times the score, 45 at least for an automatic
choice); `stable` says whether the sample has the counts to trust it, and a table
that does not is still listed, since the whole file may have them. `rows` are the sample rows that have a category and a value to classify.
A table without a score, because only one category or one class has rows or there
are too few of them, carries a `reason` and is not listed unless you asked for it.
The plan holds the number of classes and never their labels: no value of your data.

The plan's `relations.tables` member says what the exploration did for each dataset
with a column that can be a category: the rows it used, how many categories and
columns it kept, those it left out by reason (`sensitive_exposure`, `repeated_path`,
`identifier_like`, `near_unique`, `single_value`, `too_many_categories`,
`no_frequencies`, `not_in_sample`, and for the features `not_text`, `no_pattern`,
`few_lengths`, `few_prefixes`, `column_budget`), the tables that were possible, scored
and left undefined (by reason), the tables listed, the `work` spent (tables times rows
coded) and `cells`, the largest table in rows times classes.

The work is bounded like the rest: `deep.crosstab.max_columns` (50) and
`deep.crosstab.max_work` (1,000,000 tables times rows). The planner lists 20 tables
at most (`max_candidates`) and picks 8 at most by itself (`automatic_tables`; the
others say `tables_budget`). Of the features of the same two columns, it picks by itself
only the best: the others say `redundant_feature`, and a request or `--deep` takes them all.
The feature `value` sets a category against another category; of two columns that could both
be the category, only the one with fewer distinct values (the first of the file on a tie) is
the row axis in the exploration, and a request can ask for the other.

## Numbers by category

`category_stats` concerns a category and a numeric column, whose numbers it describes for each
category. It is a candidate with a `partner` (the numeric column) and no feature, and the order
matters: `column_1>column_2` is the category `column_1` and the number `column_2`.

```json
{"id": "category_stats:rows:column_1>column_2",
 "display": "type_contrat and prime_annuelle", "partner": "column_2",
 "method": "group_moments",
 "parameters": {"max_categories": 30, "bins": 50, "strategy": "linear"},
 "exploration": {"scope": "interior_rows", "rows": 900, "groups": 6,
                 "eta_squared": 0.35, "epsilon_squared": 0.34, "score": 0.58}}
```

`score` is the square root of the corrected correlation ratio of the pair on the sample (the share of
the variance of the number that the categories explain, corrected for their number), which ranks the
pairs and gives the benefit (100 times the score, 45 at least for an automatic choice). `rows` are the
sample rows that have a category and a number, and `groups` the categories among them (`other` takes
no part). A pair without a score, because only one category has rows, there are too few of them or the
number does not vary, carries a `reason` instead and is not listed unless you asked for it.

The plan's `relations.stats` member says what the exploration did for each dataset with a category
and a number: the rows it used, the categories and numeric columns it kept, those it left out by
reason (as for the tables and the pairs), the pairs that were possible, scored and left undefined (by
reason), the pairs listed and the `work` spent (pairs times rows). It is bounded by
`deep.stats.max_columns` (50) and `deep.stats.max_work` (1,000,000). The planner lists 20 pairs at most
and picks 2 at most by itself (`automatic_stats`; the others say `stats_budget`). Of two columns that
could both be the category, only the one with fewer distinct values is the category in the exploration.

## Stratification advice

```console
tabalyst scan customers.csv --plan --stratify-by province,language --sample-size 1000
```

`--stratify` adds advice for [stratified sampling](../sample/index.md) to the plan,
and `--stratify-by` also assesses the strata of several columns together (a
comma-separated list, repeated for other combinations). It reads the scan only:
the source is not read again, and the advice is a recommendation, not a fact of the
data. The advice is not part of the choice of analyses and is not written in the
second-pass document.

For each column, it says whether it can be a key by itself and why not when it
cannot: an identifier, nearly unique values, a single value, more than 50 distinct
values, a count the scan stopped tracking, or values that exposure withholds. For a
column that can, it gives:

- `strata`, the distinct values plus one stratum for the missing values (a missing
  value is a stratum of its own, as `tabalyst sample` makes it), with its `strata_basis`:
  `exact`, `estimate` (the scan only estimated the count) or `bound`;
- `smallest_share` and `largest_share`, from the exact frequencies, and
  `size_for_every_stratum`, the sample size from which the rarest stratum cannot
  get zero rows;
- with `--sample-size`, `uncovered_at_size`: the strata the proportional allocation
  would leave without a row. `rare_strata` warns that some can be absent from a small
  sample. `stratified` keeps its classic meaning and promises no minimum of one row.

For a combination of columns, it gives `strata_bound`, the largest number of
combinations the columns allow: the product of their numbers of strata, computed
with saturating arithmetic (it never overflows; `saturated` says that the product
passed 2^63 - 1) and capped by the number of records. When a count is only an
estimate the product is labelled `estimated_strata`, and the bound uses the certain
maximum of each column instead. The row sample gives `observed`, the combinations
it holds: at least that many exist, or exactly that many when the sample holds every
row (`observed_exact`). `risk` is `low`, `moderate` (above 1,000 strata), `high`
(above 10,000) or `excessive` (above 100,000, the states a sample may hold, or
saturated). A high bound proves a risk, not an explosion: the combinations that exist
can be far fewer. For a `high` or `excessive` risk the advice suggests
`reduce_fields`, `set_explicit_limit` (`--max-strata`) and `use_smart`.

## Smart sample plan

```console
tabalyst scan customers.csv --plan --smart --sample-size 1000
```

`--smart` adds the plan of a smart sample to the plan. A smart sample aims to
cover the diversity and the rare cases of a file, not to look like it: its
proportions do not estimate the population. The plan says what the sample would
aim for and what it would cost; it reads the scan and the second-pass document if
it is current, never the source, and writes nothing. [`tabalyst sample
--sample-method smart`](../sample/index.md#cover-rare-cases-with-a-smart-sample)
chooses the rows from this plan.

The plan lists **targets**, each a thing worth having in the sample, with a
`weight` and an `obligation`:

| Family | Targets |
| --- | --- |
| `low_cardinality` | each distinct value of a column of at most 100 values, and its missing cells |
| `structured_string` | each inferred pattern and the values no pattern takes, the shortest and the longest length |
| `numeric` | the minimum, the maximum, zero, each sign when both occur, ten bins of equal width |
| `date` | the earliest and the latest date, each format when several occur, each year |
| `quality` | each candidate anomaly or confirmed issue of the scan that a row can show |
| `relations` | the exceptions to a [table of a category against a feature](#tables-of-a-category-against-a-feature), when the second pass has computed it |

A target names what it stands for by reference into the scan and never holds a
value of your data. A rare target weighs more than a frequent one, up to a
ceiling; a target whose frequency is unknown gets a neutral weight, and its
`frequency` says `unknown`. A target is `mandatory` when the plan can promise
it: the values of a column whose table of values is complete, and the confirmed
issues. The others are `optional`. A target the sample cannot recognize yet, such
as a duplicate row, says `not_evaluable` and why.

Each column has a catalog that says what the targets promise. `catalog_complete`:
every value the column can take has a target. `known_values_only`: only the values
the scan saw have one, and no value outside them is promised (the scan stopped
tracking the distinct values of that column). A column with too many values, a
single value, or values that exposure withholds gets no target, and its reason.
The plan covers its targets, not every phenomenon of the data.

The plan also gives:

- `size`: the rows asked for, the number of mandatory targets (one row each is
  enough, and rows that cover several targets need fewer) and the size beyond which
  only the reserve grows;
- `reserve`: the share of the rows (20% by default) kept for ordinary rows. It
  gives way to the mandatory targets;
- `candidates`: the rows the selection would hold in memory, a few per target, and
  whether they stay within the budget;
- `passes`: the readings of the source from now to the sample, each with its
  reason. A smart sample reads the source once more to choose its rows. A second
  pass asked for before it, with `--deep`, is a reading of its own, announced with
  what it would add: the sample does not run it by itself. A stored second-pass
  document that is current is used and adds no reading.

The weights and the limits are the [`smart` settings](../reference/configuration.md#smart-settings).

## Memory and cost

Each analysis lists the memory it needs in three cases: at least what the scan
already proves, the likely size, and a firm maximum taken from the counts of
the scan. The budget is charged with the maximum, so a selection never exceeds
it. Memory that several analyses share is counted once, and the reading of the
source is counted once whatever the number of analyses. These figures size the
data structures of the analyses, not the whole process. They come from
measures of the structures Tabalyst uses, so a set of one million 12-character
identifiers is charged about 133 MB, which is why an automatic plan leaves
such exact counts out.

Each analysis and the reading also get a CPU class, `very_low`, `low`,
`moderate` or `high`, from the work they add to each cell. The classes are
measured on the second pass, with the reading of each cell included. A counter
of integers or a bin costs about 1 microsecond a cell, as much as the first pass
spends on a cell, which is why both are `moderate`; so are a pattern validation
(about 0.9 microsecond, and a little more for each candidate pattern) and a count
of dates by period (about 1.6 microseconds). A pair of numeric columns costs
about 1.5 microseconds for each cell of its two columns, also `moderate`; a column
that several pairs share is read once. A table costs from 0.3 to 0.6 microsecond for each cell of its
two columns, according to its feature, which is `low`, and a column is converted once for all the
tables that use it.

## Automatic, requested and forced

What the planner chooses by itself stays within limits that keep it cheap:

| Limit | Automatic choice | Requested or forced |
| --- | --- | --- |
| Memory (firm maximum) | 128 MiB | 512 MiB, never exceeded |
| Cells of the reading | 100 million | no limit |
| CPU class | `moderate` at most | no limit |
| Expected benefit | 45 out of 100 at least | only orders the analyses |

The limits count memory in bytes and work in cells, never measured time, so the
same scan gives the same plan on any machine.

`--deep` plans the second pass as if it were forced: every analysis that
applies and fits the 512 MiB budget, whatever the automatic limits.

```console
tabalyst scan customers.csv --plan --deep
```

The selected analyses then say `forced` instead of `automatic`. `tabalyst scan
--deep` without `--plan` [runs the second pass](deep.md) with them.

## Estimated time and confirmation

When a second reading is needed, the plan text ends with an estimated time, as
a range, from how long the first pass took to read the file:

```text
Estimated time: 4 s to 9 s (a guide from the first pass, not a promise).
Running it would ask for a confirmation first: its memory is above what an automatic choice may take.
```

The estimate is a guide: compression, disk cache and the width of the records
change it. It is not part of the plan, which stays the same from one machine to
another. A run would ask for a confirmation before starting when the selection
goes beyond an automatic limit, because it was requested or forced, or when the
upper end of the estimate reaches two minutes. What the planner chooses by
itself never asks. With several files, the text ends with one line for all of
them: the times add up and the memory is the largest.

## Options

`--plan` accepts the options that choose how the file is read (`-c`,
`--delimiter`, `--encoding`, `--collection`, `--workers`, `-q`, `--no-progress`).
It refuses `-o`, `-d`, `--force` and `--counters`, which write.
`--deep` shows the forced plan with `--plan`, and runs the second pass without it.

## Python API

```python
import tabalyst

plan = tabalyst.plan_document("customers.scan.json")
for candidate in plan.candidates:
    print(candidate.id, candidate.selection.state)

scan = tabalyst.scan("customers.csv")
plan = tabalyst.plan_analyses(
    scan,
    requests=[tabalyst.AnalysisRequest("numeric_histogram", field="age")],
)
print(plan.summary.second_pass_required)
```

`tabalyst.plan_analyses(scan)` plans from a scan result in memory.
`tabalyst.plan_document(path)` plans from a scan document; a Report is refused,
because it keeps fewer sample values than its scan. `requests` name analyses to
choose first, and `automatic=False` selects nothing else. A request for a pair names
both columns, `tabalyst.AnalysisRequest("pearson_correlation", field="price",
partner="cost")`, and works for a pair the sample did not show; with `field` alone
it asks for the listed pairs that use the column. A request for the repeated values of a combination names both columns,
`tabalyst.AnalysisRequest("duplicates_report", field="client", partner="year")`;
it is never proposed by itself. A request for a table names the
category, the column and the feature,
`tabalyst.AnalysisRequest("category_crosstab", field="region", partner="client_id",
feature="pattern")`; without `feature` it asks for all the features. It can carry
`rules=[("east", "basic")]`, rules to check against the table (a category label and the label
of the class its rows should take), which then needs the three names. A request for an
unknown analysis, dataset or field raises `tabalyst.ConfigurationError`.
`stratify=tabalyst.Stratify(combinations=[("province", "language")],
sample_size=1000)` adds the [stratification advice](#stratification-advice) as
`plan.stratification`; without it the plan has no such member.
`tabalyst.plan_sampling(scan, size=1000)` returns the [smart sample plan](#smart-sample-plan)
of a scan result; `deep=` gives the second-pass result it may use, and `dataset=` names the
dataset of a scan that has several. `tabalyst.generate_plans(inputs, smart=tabalyst.Smart(size=1000))`
gives it as `sampling` in each success.
`tabalyst.generate_plans(inputs)` plans several sources, as the command does;
`forced=True` plans a forced second pass, and the result says whether running
the plans together would require a confirmation (`requires_confirmation`).
`plan.model_dump(mode="json")` gives the plan as JSON.

`tabalyst.plan_second_pass(scan)` returns the plan with its estimated time and
whether running it requires a confirmation. It never asks anything and runs
nothing:

```python
second = tabalyst.plan_second_pass(scan, forced=True)
print(second.estimate)
print(second.requires_confirmation, second.confirmation.reasons)
```

The reasons are `memory_over_automatic`, `cells_over_automatic`,
`cpu_over_automatic` and `time_over_threshold`. The number of bins of a
histogram comes from the `deep` settings of a [configuration
file](../reference/configuration.md#deep-settings); `plan_second_pass(scan,
deep=tabalyst.DeepSettings(bins=50))` takes them explicitly. Running a plan is
described in [the second pass](deep.md#python-api).
