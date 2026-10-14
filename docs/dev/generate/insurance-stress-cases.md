# Insurance stress cases (lot G2a)

Maintenance document, never published. It prepares the `dirty_stress` profile of the
Insurance package (lot G2) and the showcase base of 100,000 rows (lot E2b). It answers
four questions: what the 3,000-row file holds (the specification), what the Generate
engine can express since lot G1, which new cases are worth adding, and how a new column
would be carried. No published file changes in this lot.

Decisions of 2026-10-14 that frame everything here: defects are **absolute numbers of
rows** (`count`, never `rate`), the 3,000-row file stays as the source of the
`sample-injected-errors` case, and the future compare tool needs the same truth: files
whose differences are known exactly.

## 1. What the 3,000-row file holds (specification for G2)

Measured on `examples/datasets/insurance-customers.csv` (3,000 rows: 2,185 principal, 568
quebec, 247 ontario). A row count is a number of rows with the defect in that column, found
by pattern against the clean grammar of the branch (identifier shapes, date format of the
branch, packaged reference tables for names, cities and streets). Counts are exact for
pattern classes and within a few rows for the typo families, whose "off the reference table"
test cannot name every mutation.

| Class | Column | Rows |
| --- | --- | ---: |
| identifier with a missing digit | `id_client` (principal 14, quebec 5, ontario 1) | 20 |
| identifier with a double hyphen | `id_client` (principal 12, quebec 5) | 17 |
| identifier with a missing digit | `id_contrat` | 22 |
| identifier with a double hyphen | `id_contrat` | 14 |
| empty | `id_contrat` | 9 |
| double hyphen | `agence_code` | 16 |
| empty | `prenom` 7, `nom` 4, `date_naissance` 6, `province_code` 3, `type_contrat` 2 | 22 |
| space inside the word | `prenom` 3, `nom` 5 | 8 |
| double space inside the word | `prenom` 6, `nom` 5 | 11 |
| leading apostrophe | `nom` | 1 |
| province code in lower case | `province_code` | 23 |
| province name in lower case, without accent or wrong case | `province_nom` (`quebec` 10, `Quebec` 10, `ontario` 1, `colombie-britannique` 1, `Nouvelle-Ecosse` 1) | 23 |
| country code in lower case | `pays_code` | 22 |
| doubled space in the postal code | `code_postal` | 54 |
| postal code with a character missing | `code_postal` | 21 |
| doubled space after `+1` | `telephone` | 42 |
| space inside the address | `courriel` | 12 |
| suffix `_X` | `type_contrat` 6, `statut_contrat` 5, `frequence_paiement` 3, `mode_paiement` 8 | 22 |
| accent removed | `mode_paiement` (`prelevement` 16, `cheque` 1) | 17 |
| date written with `/` | `date_naissance` 9, `date_debut` 8, `date_fin` 8, `date_creation` 9, `date_modification` 7 | 41 |
| date in the format of another branch | `date_naissance` 14, `date_debut` 14, `date_fin` 11, `date_creation` 14, `date_modification` 14 | 67 |
| start after end | `date_debut` / `date_fin` | 27 |
| modification before creation | `date_creation` / `date_modification` | 3 |
| negative annual premium | `prime_annuelle` | 25 |
| claim amount of `0.00` | `montant_reclamation` | 5 |
| negative claim amount | `montant_reclamation` | 1 |
| exact duplicate rows | all columns | 8 |
| typos (see below) | `prenom` about 54, `nom` about 81, `ville` about 69, `nom_voie` about 79 | about 280 |

Typos form one family across four text columns: all lower case, first two letters swapped
(`eLblanc`, `oMntréal`), a letter doubled (`Oliivier`, `RRoy`), a letter dropped
(`Sherbroke`), two letters transposed (`Evelny`, `Benajmin`), a space inserted
(`Charl es`), a letter replaced (`Peneolpe`), an accent lost (`Francois`). For G2 they are set by `count`
per column and per mutation, not by the total above.

The cohorts of the clean version already explain the rest: dates by branch (ISO for
principal, `DD-MM-YYYY` for ontario and quebec), identifier shapes by branch (`CLI-`, `ONT`,
`QC-`), language and units of address. They are properties of the population and follow the
size of the file. "Date in the format of another branch" is the injected exception to the
cohort.

Natural facts that are not defects: 71 claim dates without an amount, 2,280 empty
`orientation`, 1,928 empty `appartement`, 502 empty `date_fin`.

## 2. What the engine expresses since lot G1

| Class | Operation | Status |
| --- | --- | --- |
| empty, constant replacement, lower case | `set_missing`, `replace`, `format: lower` | available |
| `_X` suffix, accent removed, leading apostrophe | `format: suffix_x`, `strip_accents`, `leading_apostrophe` | available |
| space inside a word, double space, character dropped, double hyphen | `insert_space`, `double_space`, `drop_char`, `double_hyphen` | available |
| negative premium or claim | `negate` | available |
| date with `/` | `date_slash` | available |
| start after end | `swap` of `date_debut` and `date_fin` (stays inside the range of the column) | available |
| exact duplicate rows | `duplicate_row` | available |
| letter doubled, first two letters swapped, two letters transposed, letter replaced | none | **missing**: `double_char`, `swap_first_two`, `transpose`, `replace_char` (four small `format` values) |
| doubled space after `+1` in a phone number | `double_space` only doubles an existing space, the number has none | **missing**: a phone variant (`phone_double_space`) |
| date in the format of another branch | `date_slash` only changes `-` | **missing**: `date_dmy` and `date_iso` conversions |
| number with a currency suffix (`1234.18 $`) | none | **missing**: `currency_suffix` |
| `0.00` claim amount | `replace` with `"0.00"` | available (only on a claim row: use `when` on `reclamation_status` or a non-empty cell, see 4) |
| province in lower case, `Quebec` without accent | `lower` and `replace` | available |
| space inside the email, character missing in the postal code | `insert_space`, `drop_char` | available |

So G2 needs a short G1b: four typo values, one phone value, two date conversions and one currency suffix (eight `format` values). They are
text functions of the cell like the eight of G1, with the same tests. Without them, about 280
typo cells, 42 phone cells and 67 date cells of the 3,000-row file cannot be reproduced.

A limit of `count` that G2 must respect: a row drawn at random whose cell cannot take the
change (no hyphen, empty cell, `when` not met) is skipped, and the engine does not draw
another one. Choose target columns where every row is eligible, or plan the skipped rows.
Examples: `negate` on `montant_reclamation` hits an empty cell in 88 % of the rows, so a
`count: 1` there is skipped most of the time; use `when: {reclamation_status: fermé}` and
check the applied count in a test.

## 3. New cases worth adding

These are the cases the 3,000-row file never exercised. For each one a throwaway probe file
of 800 rows (outside the checkout) was written, scanned with `tabalyst scan --deep` and
sampled 8 times with `sample --smart` and `--sample-method random`, 100 rows each. The
table reports what Scan says about the defect and the share of the 8 draws that kept at
least one defective row.

| # | Case | Probe | Scan notices it | smart / random | Rows proposed | Carried by |
| --- | --- | --- | --- | --- | ---: | --- |
| N1 | column with a unit (`120 m²`) and its variants (`120m2`, `120 m`, `n/d`) | 800 rows, 13 variants | the `quantity` interpretation matches 791 of 800; the second pass reads the numbers (`measure_extraction`, `parsed 791`, `unparsed 9`, `homogeneous: false`); no observation names the variants | 100 % / 12 % to 50 % | 3 to 6 per variant | a new column (see 4); the Computer package already has 10 unit columns |
| N2 | wrong unit in a unit column (`m²` among `pi²`) | 5 rows | `minority_pattern` (5) | 100 % / 75 % | 3 | same as N1 |
| N3 | amounts with another convention (`$1,200`, `1,200.50` among `1 200,50 $`) | 13 rows | `minority_pattern` (9 of 13) | 100 % / 12 % to 88 % | 3 to 5 | a new column |
| N4 | text and sentinels in a number column (`N/A`, `-`, `1234$`) | 14 rows | `type_outliers` (14), `minority_pattern` (5) | 100 % / 12 % to 62 % | 3 | existing: `replace` on `prime_annuelle` and `montant_reclamation` |
| N5 | booleans in several forms (`Y`, `1`, `true`, `OUI`) | 5 rows | `variant_groups` (1), `minority_length` (4) | 100 % / 50 % | 3 | a new boolean column |
| N6 | datetime with and without offset | 16 rows | `minority_pattern` and `minority_length` (16) | 100 % / 75 % to 88 % | 3 | a new datetime column |
| N7 | identifier that lost its leading zeros | 8 rows | `minority_pattern` and `minority_length` (8) | 100 % / 75 % | 3 | a new code column; existing option: none |
| N8 | sentinel date `9999-12-31` | 4 rows | **not flagged** (no observation) | 100 % / 38 % (kept because the value is rare) | 2 | existing: `replace` on `date_fin` |
| N9 | very long cell, mojibake (`QuÃ©bec`) | 5 rows | **not flagged** | 100 % / 38 % to 50 % | 2 | existing: `replace` on `nom_voie` or `ville` |
| N10 | near-duplicate categories (upper case, trailing space, plural) | 9 rows | `variant_groups` (4), `trimmed_cells` (3) | 100 % / 0 % to 38 % | 2 to 4 | existing: `upper`, `suffix_x`, `strip` family on a category |
| N11 | province that does not match the city (valid value in the wrong place) | 2 rows | **not flagged** (cross-column) | 25 % / 12 % | 3 | existing: `replace` on `province_code` with `when: {ville: Montréal}` |
| N12 | end before start, with dates inside the range of the column | 10 rows | **not flagged** | see below | 10 | existing: `swap` |

The probe confirms three things. First, `smart` keeps at least one row of every class in all
8 draws, except N11 (25 %), where the injected value is common in its column and only the
combination is wrong. That is lot S3's territory (interactions between columns), and G2 must
record it as a known gap rather than hide it. Second, Scan does not describe N8, N9 and N11
in its observations, so a Report on `dirty_stress` will not name them: they are gaps of Scan
and of the observations, kept visible on purpose. Third, N12 was measured with a literal
early date, which is also the minimum of the column, so `smart` kept it for that reason, not
because it saw the inversion (this is the point already recorded in lot S3). The G2 profile
therefore uses `swap`, which keeps both dates inside the range.

## 4. How to carry a new column

N1, N2, N3, N5, N6 and N7 need a column that the Insurance package does not have (a surface or
sum insured with a unit, an amount with a currency, a boolean such as `paperless`, a
`datetime` such as `last_login`, a code with leading zeros). The two ways to carry them:

**A. Add columns to the package** (`schemas/customers.yaml`, `generate_insurance.FIELDS`).
Cost, measured by search:

- the six pinned digests in `tests/test_generate_insurance.py` and the 33-column contract
  (`FIELDS`, "33 named fields" in `docs/dev/generate/design.md`);
- "34 columns" cited in about thirty places: public pages (`reference/cli/report.md`,
  `get-started/simple-clear-smart.md`, `get-started/examples.md`, `scan/files.md`,
  `reference/configuration.md`), `examples/README.md`, `examples/datasets/README.md`, the
  release notes, and above all every benchmark of `docs/dev/scan/benchmarks.md`, which are
  measured on the generated 1,000,000-row, 34-column Insurance file. Adding columns
  invalidates those measurements;
- the showcase of E2b would no longer match the demonstrated 34 columns.

**B. A generic output profile for column packages.** `output_profiles` exists only for
Computer, as code (`generate_computer_output`), not as a manifest feature. Making it generic
means a manifest list of added columns, a planner and a writer (about one lot), and leaves
every published file, digest and number unchanged.

**C. Do not add columns to Insurance.** The Computer package already carries 10 unit columns
(with a localized variant and `unit_variants_extended`) and boolean columns (`touch`,
`ethernet_port`). N1, N2, N5 are exercised there. Only N3 (currency conventions), N6
(datetime with offset) and N7 (leading zeros) have no home.

Recommendation: **C now, B if N3, N6 or N7 are wanted**, never A. The showcase base and the
benchmarks keep their 34 columns; `dirty_stress` covers every class of the 3,000-row file plus
N4, N8, N9, N10, N11 and N12 on existing columns; Computer covers the units. This keeps G2
small (one profile, plus the G1b values) and keeps lot E2b free of a schema change.

## 5. Cases for G2 (proposal to confirm at gate G2a)

On top of the table of section 1 (each class at its measured absolute count), G2 would add,
all on existing columns:

| Case | Column | Operation | Rows |
| --- | --- | --- | ---: |
| text in a number column | `prime_annuelle` | `replace` `N/A`, `-` | 3, 2 |
| number with a currency suffix | `prime_annuelle` | `replace` is not enough (needs the value): `format: currency_suffix` (G1b) | 3 |
| sentinel date | `date_fin` | `replace` `9999-12-31` | 2 |
| mojibake | `ville` | `replace` `MontrÃ©al` with `when: {ville: Montréal}` | 2 |
| very long cell (300 characters) | `nom_voie` | `replace` | 2 |
| near-duplicate category | `type_contrat` | `upper`, `strip`, plural | 3, 2, 2 |
| province not matching the city | `province_code` | `replace` `ON` with `when: {ville: Montréal}` | 3 |
| end before start inside the range | `date_debut` / `date_fin` | `swap` | 27 (as in the file) |

`prime_annuelle` with a currency suffix (`1234.18 $`) can only be a defect among numbers;
it never makes the column a currency column. A genuine currency column belongs to B.

## 6. Decisions of gate G2a (2026-10-14)

1. **Insurance keeps its 34 columns** (option C, nothing added to the package, benchmarks and
   published numbers unchanged). Units are exercised by Computer.
2. **`prime_annuelle` carries monetary units in a minority of rows**, in several forms and
   with rows left without a unit (the plain number stays the majority, so the column is still
   read as a number with outliers; a genuine currency column would need option B). The forms
   G2 will set, each by its own absolute `count`, are a suffix (`1234.18 $`), a prefix
   (`$1234.18`), the French convention with a space as thousands separator and a decimal comma
   (`1 234,18 $`) and an ISO code (`1234.18 CAD`). This replaces the single `currency_suffix`
   of section 2.
3. **Lot G1b before G2**: eleven `format` values instead of eight: `double_char`,
   `swap_first_two`, `transpose`, `replace_char`, `phone_double_space`, `date_dmy`, `date_iso`,
   `currency_suffix`, `currency_prefix`, `currency_fr`, `currency_code`.
4. **Typos by `count`**, per column and per mutation.
5. **Known gaps recorded, no new detector now**: sentinel date, very long cell, mojibake,
   province not matching the city and the in-range end before start are listed as gaps of Scan
   and of `smart` in the `sample-real-errors` case (lot E2b) and in the observations notes.

Section 5 stands with these changes: the `prime_annuelle` row becomes four rows (one per
form, a few rows each, for example 4, 3, 3 and 2) in addition to the `N/A` and `-` rows.
