---
title: Inspect format changelog
description: Current format version and revisions of the JSON file written by tabalyst inspect.
---

An Inspect file written by `tabalyst inspect` identifies its experimental
contract with three fields:

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.2.0",
  "format_revision": 1
}
```

`format` identifies the document kind. `format_version` names the compatibility
family, and `format_revision` increases for meaningful structural or semantic
changes within it. [Scan](../scan/format-changelog.md) and the
[JSON profile](../report/profile-changelog.md) have their own versions and
changelogs. Beta revisions may be incompatible; automatic migration is not
provided. Tabalyst refuses a file of another version, and
`tabalyst inspect --force` writes a new one.

## Version 0.2.0, revision 1 — 2026-10-06

This is the starting point for the current [Inspect format](format.md). It
describes the `json` and `excel` kinds, their source identity, detection,
warnings and editable configuration.
