# Case: defects kept by a sample of a large file

Question: when a 100,000-row file holds defects of 45 kinds, a few rows each, how many
kinds does a sample of 3,000 or 300 rows keep? `tabalyst sample --smart` is compared with
`--sample-method random`. This is the case that checks the promise of Sample on a file
where a random draw misses most of the rare defects: a single wrong province, a single
identifier with a missing digit.

## Input

The source is `examples/datasets/insurance-customers-100k.json`, a request that builds
100,000 rows of the Insurance example with the anomaly profile `dirty_stress`: 45 classes of
defect, 845 rows in all, each class with the same number of rows whatever the file size, each
row in one class. The 27 MB file is built outside the checkout and never committed:

```console
python examples/tools/make_datasets.py
```

`input/truth.json` lists the 0-based data rows of every class. It is derived from the change
log of the generation (`insurance-customers-100k.changes.csv`), so there is no injector; the
case test checks that the committed file is that derivation. The classes, their columns and
their sizes are those of `docs/dev/generate/insurance-stress-cases.md`.

Rebuild the truth with:

```console
python examples/cases/sample-real-errors/case.py build
```

## Run

The case scans the source once with the second pass (`--deep`), as the showcase does, then
samples it. `smart` runs 3 seeds and `random` 3 seeds, at 3,000 and at 300 rows:

```console
python examples/cases/sample-real-errors/case.py measure OUTPUT_DIR
```

A row is matched by its whole content. A copied row cannot be told from its original, so for
`duplicate_rows` the count is the number of distinct contents in the sample that occur more
than once in the source.

## Result

Measured on 2026-10-14 (lot E2b), sensitive values shown (the default). Share of the 3 runs of
each method that keep at least one row of the class:

| Class | Rows | smart 3000 | random 3000 | smart 300 | random 300 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `code_postal_double_space` | 54 | 100% | 100% | 100% | 0% |
| `courriel_space_inside` | 12 | 67% | 33% | 0% | 0% |
| `id_contrat_empty` | 9 | 100% | 33% | 100% | 0% |
| `date_slash` | 41 | 67% | 67% | 0% | 0% |
| `province_code_lower` | 23 | 100% | 67% | 100% | 0% |
| `date_other_branch_format` | 67 | 100% | 67% | 0% | 0% |
| `agence_code_double_hyphen` | 16 | 100% | 0% | 100% | 0% |
| `ville_typo` | 62 | 100% | 67% | 100% | 67% |
| `nom_voie_typo` | 79 | 100% | 100% | 100% | 33% |
| `id_client_double_hyphen` | 17 | 100% | 0% | 100% | 33% |
| `claim_amount_negative` | 1 | 100% | 0% | 100% | 0% |
| `prenom_typo` | 47 | 100% | 100% | 100% | 33% |
| `duplicate_rows` | 8 | 100% | 0% | 100% | 0% |
| `nom_typo` | 79 | 100% | 100% | 100% | 33% |
| `prime_annuelle_currency_code` | 2 | 0% | 0% | 0% | 0% |
| `type_contrat_variant` | 7 | 100% | 67% | 100% | 0% |
| `province_nom_lower` | 12 | 100% | 33% | 100% | 0% |
| `name_space_inside` | 8 | 0% | 0% | 0% | 0% |
| `province_code_empty` | 3 | 100% | 0% | 100% | 0% |
| `name_double_space` | 11 | 100% | 33% | 100% | 0% |
| `prime_annuelle_negative` | 25 | 100% | 67% | 100% | 33% |
| `telephone_double_space` | 42 | 100% | 67% | 100% | 0% |
| `category_suffix_x` | 22 | 100% | 67% | 100% | 33% |
| `id_contrat_missing_digit` | 22 | 100% | 67% | 100% | 33% |
| `id_client_missing_digit` | 20 | 100% | 33% | 100% | 0% |
| `id_contrat_double_hyphen` | 14 | 100% | 67% | 100% | 0% |
| `prime_annuelle_currency_suffix` | 4 | 0% | 33% | 0% | 0% |
| `prime_annuelle_currency_prefix` | 3 | 33% | 33% | 33% | 0% |
| `pays_code_lower` | 22 | 100% | 100% | 100% | 0% |
| `date_start_after_end` | 27 | 100% | 67% | 100% | 0% |
| `ville_space_inside` | 6 | 0% | 67% | 0% | 0% |
| `date_fin_sentinel` | 2 | 100% | 0% | 100% | 0% |
| `date_naissance_empty` | 6 | 100% | 0% | 100% | 0% |
| `mode_paiement_accent_removed` | 17 | 100% | 67% | 100% | 0% |
| `claim_amount_zero` | 5 | 100% | 0% | 100% | 0% |
| `prime_annuelle_text` | 5 | 100% | 33% | 100% | 0% |
| `prenom_empty` | 7 | 100% | 0% | 100% | 0% |
| `code_postal_char_missing` | 21 | 100% | 67% | 100% | 0% |
| `nom_empty` | 4 | 100% | 0% | 100% | 0% |
| `type_contrat_empty` | 2 | 100% | 0% | 100% | 0% |
| `prime_annuelle_currency_fr` | 3 | 67% | 0% | 67% | 0% |
| `province_code_city_mismatch` | 3 | 0% | 0% | 0% | 0% |
| `city_mojibake` | 2 | 0% | 0% | 0% | 0% |
| `nom_leading_apostrophe` | 1 | 0% | 0% | 0% | 0% |
| `nom_voie_very_long` | 2 | 100% | 0% | 100% | 0% |

Over the 3 seeds, the number of classes of 45 that no run kept at all: `smart` 7 at 3,000 rows and
10 at 300, `random` 18 at 3,000 and 37 at 300. With seed 1, the run the test checks, `smart` keeps 35
classes at 3,000 rows against 17 for `random`; at 300 rows `smart` keeps 34 and `random` 3. These are the
numbers to compare when a change to Sample is made.

## Known gaps

The 10 classes that `smart` does not keep at 3,000 rows with seed 1 are listed in `case.json`
(`expectations.gaps`) and run as strict `xfail`: the test fails the day one of them is kept, so
the list is updated on purpose. Two kinds of gap appear. Classes of a handful of rows hidden in
a value that Scan sees as ordinary (a space inserted inside a name or a city, a currency sign or
code in a column of numbers, a mis-decoded city, an apostrophe before a surname) are not
targets of `smart` yet. `province_code_city_mismatch` is a combination of two columns, which is
the subject of lot S3. The rest is for a lot S4 that looks at why the other classes are lost,
without adding rows to the base to hide them.

## Files

| File | Role |
| --- | --- |
| `case.json` | The manifest: runs, sizes, expectations and gaps |
| `case.py` | Builds the truth, runs `tabalyst sample`, scores the sample, prints the tables |
| `input/truth.json` | The rows of each class |
