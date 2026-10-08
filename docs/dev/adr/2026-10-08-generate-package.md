# Generate uses one versioned package format

Status: accepted on 2026-10-08 for implementation after the Computer lot 0.
The current released interface remains YAML `definition_version: 1` until the
new format and both migrated examples are ready.

## Context

The current Generate definition describes CRM and Insurance datasets, columns,
entities, cohorts, anomaly passes, and packaged providers. Computer additionally
needs catalogs, typed CSV schemas, relations, conditional weights, constraints,
two localized projections, and output profiles. Maintaining two definition
readers would create divergent rules for planning, validation, and publishing.

## Decision

Computer, CRM, and Insurance use the versioned package described in
[`../generate/computer.md`](../generate/computer.md): `dataset.yaml`,
`catalog.yaml`, schemas, and optional CSV resources. One loader and execution
boundary validate and plan all three. Registered internal providers may
implement domain behavior, with declared schemas and resources; packages
cannot load arbitrary code. After migrating CRM and Insurance, remove the
published YAML v1 reader before the new format is released. There is no
automatic conversion or compatibility fallback for user definitions.

## Consequences

- Package paths and resources require containment, bounded loading, and
  location-rich errors before any generation.
- The Computer demo initially runs from a local package path; adding
  `--example computer` is a separate distribution decision.
- CRM and Insurance must pass documented output and scenario parity gates
  before the v1 reader is removed. Cross-version byte identity is not required.
- CLI, API, user documentation, examples, and the documentation website need a
  coordinated release update. This ADR does not publish the new behavior.

Revisit the decision if a required behavior cannot be represented by the
common package plus a registered provider; record the mismatch before adding
a second final format.
