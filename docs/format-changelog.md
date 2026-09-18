# Profile format changelog

The generated `report.json` identifies its contract with two independent fields:

```json
{
  "format_version": "0.1.0a",
  "format_revision": 1
}
```

`format_version` names the experimental compatibility family. It remains
`0.1.0a` throughout the Tabalyst `0.1.0aX` application series.
`format_revision` is a monotonic integer incremented for meaningful structural or
semantic changes. It does not change for report styling, documentation, performance
improvements, or corrections that preserve the JSON contract.

Alpha revisions may be incompatible. No automatic migration is provided yet.

## Revision 1 - 2026-09-18

- Established the first explicitly tracked alpha profile contract.
- Includes dataset/source metadata, effective configuration, quality summary,
  issues, raw preview rows, and global column profiles.
- Column profiles include normalization, inferred and semantic types, errors,
  occurrences, bounded examples, numeric statistics, date analysis, and string
  length statistics.
- Added `format_version` and monotonic `format_revision` identifiers.
