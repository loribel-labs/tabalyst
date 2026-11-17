# Insurance relations come from one population model with two outputs

Date: 2026-11-16. Status: accepted by the maintainer as a direction (plan Insurance V2, D2);
the model itself is designed and recorded at the gate before lot 8.

## Context

Today a row is a client with one contract, drawn independently by `InsuranceProvider.row()`
with no state between rows. The report asks for clients with several contracts, households,
brokers, agencies with a heavy load, renewals, several claims per contract and several payments
per claim (G01 to G10), for deduplication, sampling by group and leakage between partitions.
It proposes two outputs: a flattened CSV and four related files (`clients.csv`, `contrats.csv`,
`reclamations.csv`, `paiements.csv`).

## Decision

- One population model in memory (clients, households, brokers, agencies, contracts, renewals,
  claims, payments) feeds both outputs. There are never two generators.
- The flattened CSV is a projection of the model, one row per contract (a client with three
  contracts appears three times, with the same identity). The relational set is its other
  projection, with keys that the truth files reference.
- Phase 3 only, after the quality and truth work: the default file, the quality profiles and
  their digests do not depend on the model.
- The model must work in bounded memory for 500,000 rows with deterministic streams per
  canonical identifier (`seed`, kind, id), and never reread an output. The size of the state
  and what is kept per entity are decided at the gate before lot 8.
- Truth is written per table, with `relational` lines for the cases visible only across rows
  (shared address without duplicate, near-identical identities, reference to a missing contract).

## Consequences

- The Insurance provider stops being stateless for the profiles that ask for relations; the
  legacy path stays stateless and unchanged.
- Flattening can break a relation on purpose (random row sampling cuts a client from the
  other contracts of that client), which is what the sampling experiments need.
- The decision on memory limits, if it cannot be met, is reopened at that gate and recorded
  here before any code. Contract: `docs/dev/generate/insurance-v2.md` section 8.
