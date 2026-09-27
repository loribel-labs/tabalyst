---
title: Scan format changelog
description: How a scan document written by tabalyst scan identifies its format, and the changes of each format revision.
---

A scan document written by `tabalyst scan` identifies its contract with three
fields:

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 1
}
```

`format` names the kind of document; the JSON profile of `tabalyst report` has
its own [changelog](profile-format-changelog.md). `format_version` names the
experimental compatibility family, `0.1.0a` throughout the alpha.
`format_revision` is a monotonic integer incremented for each meaningful
structural or semantic change. It does not change for performance improvements,
documentation or corrections that keep the contract.

Alpha revisions may be incompatible. No automatic migration is provided.

## Revision 1

- First published scan format, written by `tabalyst scan`.
- Top level: engine and detector versions, scan status, source identity with
  size, modification time and SHA-256, effective configuration and its
  SHA-256, scope and diagnostics.
- CSV and JSON datasets, with fields identified by paths, exact presence,
  native types, string categories and a configurable missing count.
- Value measures: cardinality, frequencies, samples, first and last values,
  string characteristics and lengths, exact numeric statistics, booleans and
  dates, wrapped in measure envelopes when they can be limited.
- Normalization version 1 with change counters, distinct values per stage and
  variant groups.
- Technical type, thirteen built-in detectors, declarative patterns,
  interpretations and the masking of sensitive values.
