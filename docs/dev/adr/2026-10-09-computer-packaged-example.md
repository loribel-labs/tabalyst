# Keep one source for bundled Generate examples

Status: accepted on 2026-10-09 for the development checkout. This does not publish a release.

## Context

CRM and Insurance were copied between `examples/generate/` and the installed
package. Computer was copied the same way when `--example computer` was added.
The copies were identical but every catalog or schema edit required two file
changes and a parity check. During stabilization, the maintainer chose one
source for each distributed example.

## Decision

CRM, Insurance, and Computer live only under
`src/tabalyst/generate_examples/`. The wheel and sdist include those packages,
and CLI/API callers select them with `--example`. The small
`common-references` and `cohorts-anomalies` fixtures remain under
`examples/generate/` for local teaching and tests. The example generation
script reads the two local fixtures and the two bundled column packages.
Computer remains a separate three-artifact run.

## Consequences

There is no file parity process or duplicated Computer catalog. To edit a
shipped domain example, edit its package under `src/` and test `--example` from
an installed wheel. Custom packages can still be loaded by path. Computer
still writes paired localized CSVs plus metadata and requires `-d`; its lack
of anomaly profiles does not change. Public user documentation and the site
should be updated when this development format is released.
