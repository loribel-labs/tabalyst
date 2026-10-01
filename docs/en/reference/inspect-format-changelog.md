---
title: Inspect format changelog
description: How an Inspect file written by tabalyst inspect identifies its format, and the changes of each format revision.
---

An Inspect file written by `tabalyst inspect` identifies its contract with
three fields:

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1
}
```

`format` names the kind of document; the [scan format](scan-format-changelog.md)
and the [JSON profile](profile-format-changelog.md) have their own changelogs.
`format_version` names the experimental compatibility family, `0.1.0a` retained
during beta. `format_revision` is a monotonic integer incremented for each
meaningful structural or semantic change. It does not change for documentation
or for corrections that keep the contract.

Beta revisions may be incompatible. No automatic migration is provided: Tabalyst
refuses a file of another version, and `tabalyst inspect --force` writes a new
one. See the [Inspect format](inspect-format.md) for the current structure.

## Revision 1

- First Inspect format, kind `json`, for `.json`, `.jsonl` and `.ndjson` sources.
- Sections `inspect`, `source`, `detection`, `warnings` and `config`; the part
  you edit is `config`, with `structure.dataset_path`, `flatten` (`enabled`,
  `separator`, `max_depth`), `arrays.mode` and `errors.policy`.
- `detection` records the whole-source candidates and the bounded observation of
  their first records, with its scope, the selection and its basis. There is no
  confidence score.
- `warnings` codes: `ambiguous_collections`, `no_collection`,
  `candidates_truncated`, `candidate_not_eligible`,
  `candidate_not_eligible_truncated`, `invalid_lines`, `non_object_lines`,
  `configured_path_not_found` and `source_name_mismatch`.
