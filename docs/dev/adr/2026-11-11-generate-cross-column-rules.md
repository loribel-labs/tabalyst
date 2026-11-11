# Generate rules between columns and the rule_breaks profiles

Date: 2026-11-11. Status: accepted by the maintainer, who uses the generated
files to test analyses across columns.

## Context

The three Generate examples drew most columns independently: a CRM deal lost
with a 95% probability, an activity before the contact existed, a travel
contract active for nine years, a monthly payment by cheque. Such files cannot
test an analysis across columns: the clean file already holds exceptions
nobody logged, and no profile holds exceptions that were.

## Decision

- **The clean file holds no exception to its rules.** Every rule between
  columns is strict in the clean data; noise comes only from anomaly profiles,
  where it is logged.
- **Declarative options in the column model** (`generate_definition.py`,
  `generate_values.py`), usable by any package and validated once:
  `decimal` gains `distribution: lognormal` (`median`, `sigma`), `by_month`,
  `by_value` and `round_to`; `choice`, `integer`, `decimal`, `date` and
  `datetime` gain `by_case`; dates gain `after`, `growth` and `weekdays`;
  `boolean` gains `true_share`; a column gains `missing_by`. A `by_case` entry
  is validated as a column of its own, so the rules of a kind exist once.
- **Each option leaves the other draws alone**: one random number per value
  whatever it does, and a stream of its own for `round_to`, so a declaration
  that does not use an option keeps its bytes.
- **Insurance and Computer keep their Python providers.** Their rules are
  written there (`generate_insurance.py`, `generate_computer.py`), not moved to
  the column model; the truncated log-normal is shared in `generate_draws.py`.
- **A `rule_breaks` profile in each example** breaks the rules on purpose with
  the existing operations (`replace`, `set_missing`, `format`, `swap`, a one
  column `when`) and a `class` per rule, so the change log is the ground truth
  of an analysis. It uses rates, not counts, so it works at any size; Insurance
  replaces dates in the ISO branch only, and Computer uses `compact` columns
  only, so a broken rule never comes with a format defect or a missing column.

## Consequences

- The clean files of the three examples change for a given seed, and the
  pinned digests of `tests/test_generate_anomalies_regression.py`,
  `test_generate_crm_package.py` and `test_generate_insurance.py` are
  recomputed. `dirty_realistic` of Insurance now skips the emails already
  missing in the clean file.
- Scan and Report still do not evaluate these rules (design, Lot 5): the files
  illustrate them, the Report does not claim to detect them.
- A numeric correlation that needs a new column (CRM promises 26) and an
  emptied Computer `color` (part of the SKU) were left out.
- Contracts: `docs/dev/generate/design.md` and `docs/dev/generate/computer.md`;
  public pages `docs/en/generate/crm.md`, `insurance.md`, `computer.md`.
