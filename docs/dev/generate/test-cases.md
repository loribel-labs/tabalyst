# Generator of test cases (lot G3a)

Maintenance document, never published. It designs lot G3b: the case
`sample-injected-errors` stops injecting its errors by hand in `case.py` and takes them,
with its truth, from the Generate engine. No code changes in G3a.

Decisions of 2026-10-14 and 2026-10-15 that frame it: defects are **absolute numbers of
rows** (`count`, never `rate`); the truth of a case is **the rows of each named class**;
the future compare tool needs the same input (two files whose differences are known
exactly); the 3,000-row file stays the source of the case; no new command until the need
is established.

## 1. What exists

- `generate_anomalies.inject_anomalies(clean, altered, changes, dataset=, profile=, seed=,
  count=, delimiter=)` reads **any CSV** (`clean`), not only a file Generate just wrote. It
  needs a mapping with an `id` and a list of `operations`, the number of data rows and a
  seed, and writes the altered file and a change log. Nothing in it is specific to the
  insurance package: the only requirement is that the columns an operation names exist.
- An operation has `kind` (`set_missing`, `replace`, `duplicate`, `format`, `swap`,
  `duplicate_row`), `column`, `count` (or `rate`), `value`, `when` and `class`. With
  `count`, exactly that many rows are chosen among those the operation can change, and
  **no row is shared** between two `count` operations, so a row has one class.
- The change log has one line per changed cell, with the 1-based `row_number` of the file
  (the header is row 1) and the `class` of the operation. The case `sample-real-errors`
  already derives its truth from it (`truth_from_changes`: class to sorted 0-based data
  rows, `row_number - 2`).
- There is no command and no public function for this. `tabalyst generate` builds a clean
  file and injects into it in one run; `examples/tools/make_datasets.py` drives that.
  `inject_anomalies` is imported by the tests (`tests/test_generate_anomalies.py`).

## 2. The classes of the case and what Generate does with them

The case holds 21 classes, 167 rows of truth in all, built with a seed
(`build.seed` 123) by `case.py`.

| Class | Rows | Column | Generate | Verdict |
| --- | ---: | --- | --- | --- |
| `email_malformed` | 6 | `courriel` | `replace`, one value each | yes |
| `phone_malformed` | 6 | `telephone` | `replace`, one value each | yes |
| `postal_malformed` | 6 | `code_postal` | `replace`, one value each | yes |
| `birthdate_invalid` | 6 | `date_naissance` | `replace`, one value each | yes |
| `premium_outlier` | 6 | `prime_annuelle` | `replace`, one value each | yes |
| `id_trailing_space` | 6 | `id_client` | `format` `trailing_space` | yes |
| `name_long_weird` | 4 | `nom` | `replace` with the literal text (300 characters, a control character, markup, bidirectional marks) | yes |
| `end_before_start` | 8 | `date_debut`, `date_fin` | `swap` of the two columns | yes, see 3.2 |
| `novel_category_typo` | 4 | `type_contrat` | `replace`, one value each | yes |
| `missing_required` | 6 | `id_contrat` | `set_missing` | yes |
| `name_leading_space` | 6 | `prenom` | none (space or tab before the value) | needs two `format` values |
| `name_double_space` | 4 | `nom` | `format` `insert_double_space` | yes |
| `city_case_variant` | 6 | `ville` | `format` `upper` | yes |
| `agency_code_length` | 4 | `agence_code` | `replace`, one value each | yes |
| `name_zero_width` | 4 | `prenom` | none (U+200B inside the value) | needs a `format` value |
| `name_replacement_char` | 4 | `nom` | none (U+FFFD inside the value) | needs a `format` value |
| `rare_surname` | 6 | `nom` | `replace`, one value each | yes |
| `city_typo` | 6 | `ville` | `format` `double_char` | yes |
| `duplicate_rows` | 6 | the whole row | `duplicate_row` | yes, see 3.3 |
| `common_anomalies` | 60 | six columns | none (six different edits, 10 rows each) | stays in `case.py` |
| `worst_row` | 3 | six columns | impossible: Generate never puts two classes on a row | stays in `case.py` |

`worst_row` and `common_anomalies` stay in `case.py` because they exist to test the
interaction of anomalies (a row that has all six is not among the candidates of any of
them), which is the opposite of what the engine guarantees. `common_anomalies` shares its
six edits with `worst_row`, so both stay together.

New `format` values needed (four): `leading_space`, `leading_tab`, `insert_zero_width`
and `insert_replacement_char`. Each is a pure function of the value and the random stream
like the others of `TEXT_TRANSFORMS`, listed in `FORMAT_VALUES`, with a test and the line
of the format table in `design.md`. They are not specific to the case: a name with a
leading space or an invisible character is a defect a generated file should be able to
carry.

## 3. What changes, and must be accepted

### 3.1 One value per operation

`replace` has one `value`. A class with six different values (the six malformed emails)
becomes six operations of `count` 1 with the same `class`. The journal groups by class, so
the truth is the same. The expansion is made by `case.py` from a list of values in
`injections.json`; the engine does not change. A `values` list in the engine would be
shorter to write, and is left out until a second case needs it.

### 3.2 `end_before_start` through `swap`

The case writes two constants (`2030-01-01`, `2001-01-01`). A `swap` of `date_debut` and
`date_fin` turns an ordered pair into a broken one with real dates, which is closer to a
real defect and is what the `date_order` analysis of lot S3b counts. It applies only to
rows whose two dates differ and are not empty; the engine picks among those. If the file
already holds records whose end precedes the start, they are not in the truth, as for the
other classes the source holds by itself (see 3.5).

### 3.3 `duplicate_rows`

The case appends six copies at the end of the file (3,006 rows). `duplicate_row` overwrites
a row with a copy of an earlier output row, so the file keeps 3,000 rows and the duplicate
is the later of the two. The score already counts the distinct contents of the sample that
occur more than once in the source, so it does not depend on where the copy is. One
difference to keep in mind: the copied row can be one that already carries another class
(the engine copies output rows), so the duplicate then holds that defect without a journal
line of its own. The rows are claimed in profile order and the duplicates come last, as the
engine runs row operations after the others; G3b measures how often it happens and records
it.

### 3.4 Other rows, other measure

Generate chooses the rows with its own streams (`seed`, dataset, profile index), not with
`random.Random(123)` of `case.py`. The injected rows therefore change, and with them what a
sample at 150 rows and seed 1 keeps. G3b **re-measures** the case and records the
difference in `case.json` and in the README; it does not edit the expectations to match
and does not drop a class that is lost: a lost class is a gap with its reason, as in
`sample-real-errors`.

### 3.5 The source already holds some of the defects

The 3,000-row file is itself dirty (lot G2a measured its defects), so it holds malformed emails,
empty contract identifiers and so on. The truth by row cannot tell them from the injected
ones, which is why `score()` scores some classes by the property of the cell
(`BY_CONTENT`, `SINGLETONS`, empty identifiers). G3b keeps that function and its comments
unchanged; the truth of the other classes is exact by row. Making the source clean would
remove these exceptions and change the case (and the published demo that reads the file),
so it is not part of G3.

## 4. Design

**Request.** `examples/cases/sample-injected-errors/injections.json`: the profile `id`, a
list of operations in the form of the engine, where a `replace` may carry `values` (a list)
instead of `value`. `case.py` expands it (3.1), calls `inject_anomalies` on the source with
`count` equal to its number of rows, the `delimiter` of the file and `build.seed`, and
reads the change log.

**Entry point.** `case.py` imports `tabalyst.generate_anomalies.inject_anomalies`, as the
tests do. No new command, no new public API: a script of the repository using an internal
module of the same repository is the lightest thing that works. If the compare tool needs
the same entry, a small public function in `generate_service.py` is the next step, and then
the case moves to it.

**Truth.** `truth_from_changes` exists in `sample-real-errors/case.py`; G3b moves it to a
shared module of `examples/tools/` (`case_truth.py`) used by both cases. The classes that
stay in `case.py` (`common_anomalies`, `worst_row`) are added after the injection on rows
the log does not name, with the same six edits as today, and written to the same
`truth.json` (class to 0-based data rows, same format as now).

**Files.** `input/dirty.csv` and `input/truth.json` stay committed and rebuildable;
`input/changes.csv` (the change log, about 40 KB) is committed too, since it is the proof
that the truth comes from the generation. `case.py build` rebuilds the three and the
generic test of the cases (E1) compares them to the committed ones.

**Engine.** Four `format` values (section 2), with tests, in `generate_anomalies.py`,
`generate_definition.py` (the validator reads `FORMAT_VALUES`) and `docs/dev/generate/design.md`.
No change to the change log, the summary or the operation rules.

## 5. Plan of G3b

1. The four `format` values, with their tests (`tests/test_generate_anomalies.py`).
2. `injections.json`, the expansion and the injection in `case.py`; `common_anomalies` and
   `worst_row` as a post step; `case_truth.py` shared with `sample-real-errors`.
3. Rebuild `input/`, run `case.py measure`, compare with the current `kept` and `gaps` of
   `case.json`, and write both in the README. Measure first, then adjust nothing in `smart`.
4. Docs: `examples/cases/sample-injected-errors/README.md`, `examples/cases/README.md`,
   `examples/datasets/README.md` if the file list changes. Public documentation does not
   change (the new `format` values are not in `docs/en/`; to be confirmed when G3b reads the
   Generate pages).

Out of G3: a `values` list in the engine, a command or a public function, the compare tool,
a clean source for the case, any change to `smart`.

## 6. Risks

- The re-measure may lose or gain classes at 150 rows and seed 1. This is a result, not a
  failure: it is recorded as is.
- A swapped pair that looks fine in a column-by-column scan is the point of `end_before_start`;
  the `date_order` target of lot S3b should keep it. If it does not, that is a finding about
  `smart`, for a separate lot.
- The copy of a `duplicate_row` that carries another class (3.3).

## 7. Outcome of G3b (2026-10-15)

The four `format` values, `injections.json`, `examples/tools/case_truth.py` and the new
`case.py` are in. 19 classes come from the Generate run (167 rows of truth with the two
classes of `case.py`), the file keeps its 3,000 rows and `input/changes.csv` is the change
log (about 40 KB). No copied row shares its content with an altered row. The measure at 150
rows and seed 1 keeps the same classes as before (only `city_typo` stays a gap). Across
sizes, `city_case_variant` at 100 rows goes from 67% to 0% and `city_typo` from
33%/67%/100% to 0%/0%/33% (100/200/400 rows); the rest is equal or better. Recorded in the
README of the case as a finding about `smart`, not investigated in this lot.
