# Conformance of the Report overview to its specification

Status of the thirty acceptance criteria (CA-01 to CA-30) and of the decisions D-01 to
D-17 of the specification "Tabalyst Report: summary table of the columns and semantic
inference" (private repository `tabalyst-gb`, `KANBAN/04-SRS/2026-10-16-report-overview/`),
after lot R11. Maintainer documentation, never published. The contract is
`summary-table.md`.

All the criteria are tested in `tests/scan/test_contract_summary.py`; the browser
regression is `tests/browser/report.cjs` (four sizes, both themes, keyboard, touch).

## Acceptance criteria

| Id | Criterion | Test | Status | Note |
| --- | --- | --- | --- | --- |
| CA-01 | The table has the eight columns in the order of D-01 | `test_CA01_the_table_has_the_eight_columns_in_order` | Met |  |
| CA-02 | A family filter does not select a homonymous type of another family | `test_CA02_a_family_filter_does_not_select_a_homonymous_type` | Met |  |
| CA-03 | Two columns with the same name keep their own results and links | `test_CA03_two_columns_with_the_same_name_keep_their_own_identity` | Met |  |
| CA-04 | A complete, exact, unique identifier is a Unique ID | `test_CA04_a_complete_exact_unique_identifier_is_unique_id` | Met |  |
| CA-05 | A missing value, a repetition or a limited cardinality keeps an ID | `test_CA05_a_missing_or_repeated_value_keeps_the_field_an_id`, `test_CA05_a_limited_cardinality_keeps_the_field_an_id` | Met |  |
| CA-06 | Values equal after trim are not unique | `test_CA06_values_equal_after_trim_are_not_unique` | Met |  |
| CA-07 | A distinct first column of dates or amounts is not an identifier | `test_CA07_a_distinct_first_column_of_dates_or_amounts_is_not_an_identifier` | Met |  |
| CA-08 | The median length, not the maximum, gives the Text type | `test_CA08_the_median_length_gives_the_text_type_not_the_maximum` | Met |  |
| CA-09 | Text types change at the configured bounds | `test_CA09_text_types_change_at_the_configured_bounds` | Met with a reserve | The default bounds are 5, 20, 50 and 255 characters (setting `scan.classification.*_max_length`), not the 10, 50, 255 and 1,000 of the first specification: see D-07. |
| CA-10 | A column of long emails stays Email | `test_CA10_long_emails_stay_email_and_do_not_become_text` | Met |  |
| CA-11 | An impossible calendar date is an Error, an ambiguous one an Issue | `test_CA11_an_impossible_calendar_date_is_an_error_and_an_ambiguous_one_is_not`, `test_CA11_an_ambiguous_date_is_an_issue` | Met |  |
| CA-12 | A column named email that holds free text gets no email Errors | `test_CA12_an_email_name_over_free_text_is_not_established` | Met |  |
| CA-13 | A value a non-mandatory detector does not recognize is not an Error | `test_CA13_a_value_a_detector_does_not_recognize_is_not_an_error` | Met |  |
| CA-14 | Three categories and twenty occurrences are distinct figures | `test_CA14_three_categories_and_twenty_occurrences_are_distinct_figures` | Met |  |
| CA-15 | Repetitions beyond the first are not duplicated occurrences | `test_CA15_repetitions_beyond_the_first_are_not_duplicated_occurrences` | Met |  |
| CA-16 | A mostly empty column reports Missing without an Error | `test_CA16_a_mostly_empty_column_reports_missing_without_error` | Met |  |
| CA-17 | A partial detector is not 'none detected' | `test_CA17_a_partial_detector_is_not_none_detected` | Met |  |
| CA-18 | Null, disabled and failed stay distinguishable | `test_CA18_null_disabled_and_failed_stay_distinguishable` | Met |  |
| CA-19 | Masked and hidden values leave no raw example | `test_CA19_masked_and_hidden_values_leave_no_raw_example` | Met with a reserve | Tested under `mask` and `hide`. The project default is `show` (sensitive values are not hidden for now); the projection of a column keeps no raw value for those modes (R11b, 20.5). |
| CA-20 | The classification renders without the source | `test_CA20_the_classification_renders_without_the_source` | Met |  |
| CA-21 | JSON occurrences are not reported as rows | `test_CA21_json_occurrences_are_not_reported_as_rows` | Met |  |
| CA-22 | Naming conventions give equivalent tokens | `test_CA22_naming_conventions_give_equivalent_tokens` | Met |  |
| CA-23 | Adverse names get no generic hint | `test_CA23_adverse_names_get_no_generic_hint` | Met |  |
| CA-24 | Secondary traits do not add displayed types | `test_CA24_secondary_properties_do_not_add_displayed_types` | Met |  |
| CA-25 | An overview over several patterns names no subsidiary | `test_CA25_an_overview_over_several_patterns_names_no_subsidiary` | Met |  |
| CA-26 | Equal counts without proven overlap are not merged | `test_CA26_equal_counts_without_proven_overlap_are_not_merged` | Met |  |
| CA-27 | Previews are reachable without hover or colour | `test_CA27_previews_are_reachable_without_hover_or_color` | Met |  |
| CA-28 | A report without --details links to no missing page | `test_CA28_a_report_without_details_links_to_no_missing_page` | Met with a reserve | Links to the column pages exist only with `--details`. |
| CA-29 | A recommended finding is never reported | `test_CA29_a_recommended_finding_is_never_reported` | Met with a reserve | The thirteen `recommended` entries of the catalogue produce no finding and no tile. |
| CA-30 | A failed check is never counted as invalid | `test_CA30_a_failed_check_is_never_counted_as_invalid` | Met |  |

## Decisions

| Id | Decision | Where it is met | Status | Note |
| --- | --- | --- | --- | --- |
| D-01 | Eight columns in the target order | CA-01, `report_table.py`, `report.cjs` | Met | Column, Type family, Type, Overview, Missing, Errors, Issues and Details |
| D-02 | Family and type in two filterable, sortable columns | CA-02, `report.cjs` | Met | Filters and sorts work on codes |
| D-03 | Textual Overview | CA-25, `report_overview.py` | Met | One sentence per profile, written from stored facts |
| D-04 | Errors and Issues as short labels with quantities, preview wished | CA-14, CA-27, `report_preview.py` | Met | Two labels, then "+N more"; the preview gives population, share, accuracy, limits and examples |
| D-05 | Details includes examples | `report_details.py`, CA-19 | Met | Representative values and measures, through the exposure |
| D-06 | Five Text types | CA-08, CA-09 | Met | Very short, Short, Medium, Long, Very long |
| D-07 | Text classified by the median; bounds 10 / 50 / 255 / 1,000, configurable | CA-08, CA-09 | Amended | Decision 12 of the plan: the bounds are 5 / 20 / 50 / 255, one setting `scan.classification.*_max_length` shared with the String analysis |
| D-08 | The JSON may change | `docs/en/report/profile-changelog.md` | Met | Report revision 4, unpublished; the changes are in its changelog entry |
| D-09 | Scope: table, classification, first rules, JSON | contract sections 1 to 20 | Met | The scope grew with the overview cards (Column quality, Signals, Column types) and the column page |
| D-10 | Catalogue with status and priority per entry | `scanner/classify/catalog.py`, CA-29 | Met | Python catalogue (ADR 2026-10-16); `active` entries are produced, `recommended` ones are not |
| D-11 | Inference shared with the engine; Scan first, then `scan --deep`; results in the JSON | `scanner/classify/`, `report_classification.py` | Met | The Scan carries the classification, the Report refines it with the second pass |
| D-12 | One family and one type; traits and candidates as metadata; fallback when evidence is thin | CA-24 | Met | |
| D-13 | An Error needs deterministic invalidity with established semantics, or a violated constraint | CA-11, CA-12, CA-13 | Met | No constraint format yet (O-15): only deterministic Errors exist |
| D-14 | The name alone never concludes an Error | CA-12 | Met | |
| D-15 | Unique ID needs a credible role, no missing value and exact analytical uniqueness | CA-04 to CA-07 | Met | |
| D-16 | Scan2 is the existing `scan --deep` | `deep_service.py` | Met | No change |
| D-17 | An autonomous, complete, evolving Markdown document | `summary-table.md`, this page | Met | |

## Open points of the specification

| Id | Point | State |
| --- | --- | --- |
| O-05 | Score and confidence levels | Decided: evidence is kept, no classification percentage is shown |
| O-06 | Rarity rule for categories, patterns, formats | Not active: the entries stay `recommended` |
| O-11 | Technical type in Details | Decided: kept in the JSON and in the Column types card |
| O-12 | Vocabulary of the evaluation states | Decided: ADR 2026-10-16 (assessment state vocabulary) |
| O-13 | Number of labels, order, "+N more", number of examples | Decided: two labels then "+N more", two examples (R9b) |
| O-15 | Configuration of mandatory constraints | Open, outside this work (lot L2) |
| O-16 | Version and keys of the JSON | Decided: `format_version` 0.2.0, Report revision 4 |
| O-17 | Format of the catalogue | Decided: central Python catalogue (ADR 2026-10-16) |
| O-20 | Colours of Issues and new families | Decided: Error red, Issue orange, Info blue; contrasts and keyboard checked by `report.cjs` |
| O-21 | Performance budget | Measured in lot R11 (see `docs/dev/releases/0.7.0.md`); no threshold proposed |
| Others | O-01 to O-04, O-07 to O-10, O-14, O-18, O-19, O-22 | Not re-examined in R11; to confirm with the maintainer |
