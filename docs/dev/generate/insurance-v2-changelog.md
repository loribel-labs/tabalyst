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
