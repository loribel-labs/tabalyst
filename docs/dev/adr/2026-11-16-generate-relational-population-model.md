# Insurance relations come from one population model with two outputs

Date: 2026-11-16 (accepted as direction), ratified: 2026-11-17 at gate P2 before lot 8.
Status: accepted by the maintainer.

## Context

Today a row is a client with one contract, drawn independently by `InsuranceProvider.row()`
with no state between rows. The report asks for clients with several contracts, households,
brokers, agencies with a heavy load, renewals, several claims per contract and several payments
per claim (G01 to G10), for deduplication, sampling by group and leakage between partitions.
It proposes two outputs: a flattened CSV and four related files (`clients.csv`, `contrats.csv`,
`reclamations.csv`, `paiements.csv`).

## Decision

- One population model in memory (`PopulationModel` in `src/tabalyst/generate_population.py`,
  managing `Household`, `Customer`, `Broker`, `Contract`, `Claim`, `Payment`) feeds both outputs.
  There are never two generators.
- The flattened CSV is a projection of the model, one row per contract (a client with three
  contracts appears three times, with the same identity). The relational set is its other
  projection, with keys that the truth files reference.
- Phase 3 only, after the quality and truth work: the default file, the quality profiles and
  their digests do not depend on the model (legacy stateless `InsuranceProvider.row()` stays
  strictly intact and byte-identical).
- Memory bound: for 500,000 contracts (~360,000 clients, ~300,000 households, ~75,000 claims,
  ~110,000 payments), memory is strictly bounded under 150 MB through lightweight `__slots__`
  classes, string interning for repetitive categorical values, and on-demand projection.
- Determinism: independent random streams keyed by `seed`, entity kind and entity sequence id.
- Truth is written per table, with `relational` lines for the cases visible only across rows
  (shared address without duplicate, near-identical identities, reference to a missing contract).

## Consequences

- The Insurance provider stops being stateless for the profiles that ask for relations; the
  legacy path stays stateless and unchanged.
- Flattening can break a relation on purpose (random row sampling cuts a client from the
  other contracts of that client), which is what the sampling experiments need.
- Memory consumption for 500,000 rows is validated through automated tests (`tracemalloc`).
- Contract: `docs/dev/generate/insurance-v2.md` section 8.
