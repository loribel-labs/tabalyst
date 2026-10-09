# Insurance Generate reference provenance

The seven CSV tables in this folder are synthetic project data created on
2026-09-16 for the Insurance prototype. They were copied from
`tabalyst-generate/domains/insurance/resources/` and keep their original rows
and weights. They do not come from an insurer or an actuarial study. Premium
ranges and claim probabilities are illustrative, not pricing guidance.

| Table | Purpose |
| --- | --- |
| `contract_types.csv` | Products, illustrative premium ranges and claim parameters. |
| `branch_contract_weights.csv` | Product weights for the three branches. |
| `contract_statuses.csv` | Status weights and end-date policies. |
| `payment_frequencies.csv` | Payment frequency weights. |
| `payment_methods.csv` | Payment method weights. |
| `claim_statuses.csv` | Claim status weights and amount policies. |
| `agencies.csv` | Fictional agency codes linked to cities in the common references. |

The source manifest is
`tabalyst-generate/domains/insurance/resources/SOURCES.md`. Generate validates
table headers, weights, product coverage and agency geography when the
Insurance example runs. The common person, address and contact tables are
documented in the parent `SOURCES.md`.
