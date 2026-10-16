# The classification catalogue is a typed Python module

Date: 2026-10-16 (lot R0 of the Report overview work)

## Context

The classification needs families, types, name rules and finding codes, each
with a status and prerequisites. The brainstorm sketched YAML. Tabalyst's user
configuration is strict JSON, and a catalogue is not a user format (RT-08,
O-17).

## Decision

- The catalogue is `scanner/classify/catalog.py`: frozen, typed dataclasses and
  tuples, validated by tests and by `mypy`.
- It lists only the active entries of the L0 foundation, plus the finding codes
  with a `status` of `active` or `recommended`. A `recommended` entry never
  produces anything in a real report.
- The name rules form a versioned registry (`NAME_RULES_VERSION`) in
  `scanner/classify/names.py`.
- No YAML or JSON catalogue, no user-facing rule format. A rule needs an
  algorithm and a threshold before it is active.

## Consequences

- A rule change is a code change with a test and a version bump; the version
  reaches `rule_version` and the engine warning.
- Rules cannot be extended by users in L0. Declared constraints (backlog L2)
  need their own configuration design.
- The catalogue is independent of the HTML templates; the words are in
  `report_labels.py`.
