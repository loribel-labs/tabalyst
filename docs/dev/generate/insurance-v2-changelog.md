# Insurance V2 changelog

Maintenance document, never published. The contract is [`insurance-v2.md`](insurance-v2.md).

Two numbers are tracked here (contract 5.5 and 5.7):

- `generation_version` of `manifest.json`: an integer raised whenever the bytes of a V2 output
  change for the same inputs (seed, profile, rows, as-of date, package);
- `format_revision` of `rules.json`, `metrics.json` and `manifest.json` (`format_version`
  `0.2.0`): raised by a change of structure or meaning of one of the files.

The format is experimental during the beta: no migration is provided. Until the first release
that ships it (0.7.8, gate P2), the branch may still add members within revision 1; each one is
listed here.

## generation_version 1, format revision 1 (lot 2, 2026-11-16)

First appearance of the four files of a scenario profile:

- `truth.csv`: the 14 columns of contract 5.2; kinds `injected`, `net_difference` and
  `rule_violation` (the other three kinds arrive with lots 3 and 9);
- `rules.json` (`tabalyst.generate.rules`): `dataset`, `profile`, `as_of_date`, `conventions`
  (`branch_column`, `date_format`, `decimal`) and the rules the profile names, each with
  `detection`;
- `metrics.json` (`tabalyst.generate.metrics`): `rows`, `counts`, `scenarios`, `rules`,
  `categories`, `kinds`; `absence_probability` arrives with lot 3, still in revision 1;
- `manifest.json` (`tabalyst.generate.manifest`): the members of contract 5.5 plus `dataset`.

## generation_version 2, format revision 1 (lot 3, 2026-11-17)

`metrics.json` and `truth.csv` change for the same inputs, hence the new generation version; no
structure of `rules.json` or `manifest.json` changes, and the first release that ships the
format is still to come, so the revision stays 1:

- `metrics.json` gains `absence_probability`: per scenario, `cases`, `probability` (a sample
  size, 500, 1000, 5000, 10000 and 50000, to the exact probability for the rows of the file,
  `null` above the number of rows) and `reason`; a scenario whose case spans several rows has
  `probability` `null` and `reason` `multi_row_case`;
- `ScenarioMetrics.applied_cases` counts cases (distinct `relational` groups when a scenario has
  some) and `rows_touched` the rows they involve: they differ for a case on several rows;
- `truth.csv` uses the kinds `relational` (two lines per `reuse_value` case, `group_id`
  `<scenario>-<first row>`) and `valid_atypical` (one line per cell a `valid_atypical` scenario
  changed, severity `info`, detection `none`);
- the manifest holds `generation_version` 2.

Package side: the profile `rare_events` (34 columns, floor of 100,000 rows) and the profile key
`min_rows`; operation kinds `reuse_value` and `copy_column`; `format` values `times_100`,
`date_plus_century` and `postal_other_province`. The three legacy profiles do not move.

## Extended output profile (lot 4, 2026-11-17)

Option `--output-profile extended` on the Insurance package:

- Appends 10 priority columns after `filiale` on `insurance-combined.csv` (44 columns in total,
  the 34 of default plus 10) and on branch files (43 columns, the 33 base columns plus 10):
  `date_sinistre`, `montant_couverture`, `franchise`, `montant_indemnise`, `date_resiliation`,
  `statut_paiement`, `canal_acquisition`, `courtier_id`, `produit_code`, `nombre_reclamations`;
- Independent random streams per column `_stream(seed, dataset, column, "extended")`: base row
  draws and bytes remain strictly identical to default for the same seed;
- New rules added to the package catalogue: M07 (cancellation date), M08 (claim event date),
  M09 (claim declaration date), M10 (non-negative indemnity), M11 (indemnity cap), M12 (structural
  absence), M13 (claim counts), M24 (broker channel), M25 (product code);
- `RuleEvaluator.check` skips any rule referencing columns not present in the evaluated row;
- `manifest.json` carries `output_profile: "extended"` when selected;
- `generation_version` stays 2 (default runs keep identical bytes).

## Format catalogue F01 to F22 (lot 5, 2026-11-17)

Catalogue of format defect and variant operations completed in `generate_anomalies.py`:

- 18 new format operation values added to `FORMAT_VALUES` and `TEXT_TRANSFORMS` (bringing total format values to 52):
  - F01: `surrounding_space` (random leading/trailing spaces)
  - F03: `insert_non_breaking_space` (NBSP `\u00A0` replacing or added to spaces)
  - F04: `unicode_nfd` / `unicode_nfc` (Unicode normalization)
  - F05: `title_case` (first letter of each word capitalized)
  - F08: `phone_drop_digit` (drop random digit from phone number)
  - F09: `email_invalid` (syntax error, e.g. missing `@` or domain)
  - F10: `email_forbidden_domain` (forbidden test domain such as `example.com`, `test.invalid`)
  - F11: `postal_no_space` (Canadian postal code without space, `A1A1A1`)
  - F12: `postal_invalid_syntax` (corrupted postal code syntax)
  - F13: `decimal_comma` / `decimal_dot` (decimal comma vs dot)
  - F14: `thousands_space` / `thousands_comma` (thousands separators)
  - F18: `date_impossible` (calendar-impossible date e.g. day 00 or 32, month 00 or 13)
  - F20: `date_swap_month_day` (swapped day/month for ambiguous date, keeping canonical clean ISO date)
  - F21: `drop_leading_zeros` (drop leading zeros from identifier)
  - F22: `similar_char` (visually confusable homoglyphs: `O` <-> `0`, `l` <-> `1`)
- Canonical normalization in `generate_canonical.py`:
  - `canonical_decimal` strips thousands separators and normalizes decimal commas to plain decimal `.`.
  - F20 retains the original clean ISO date in `truth.csv`.
- Kleene 3-valued logic in `generate_rules.py`: format defects on date/decimal columns result in unknown (`None`) evaluations, ensuring that format defects never cause spurious business rule violations.
- Non-regression: 29 legacy format operations and existing profiles unchanged.
- `generation_version` stays 2.

