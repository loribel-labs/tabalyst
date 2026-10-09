# The plan of a smart sample is a document of its own, built before the source is read again

Status: accepted on 2026-10-09 (maintainer, lot 10a of the Scan and JSON work; the
maintainer approved the plan and its defaults with "ok avec tout").

## Context

A smart sample aims to cover the diversity and the rare cases of a file (D15), not to
reproduce its proportions. The specification (SMART-01 to SMART-04, 15.2 to 15.6) asks
for targets built from the profile before the sample reads the source again, a weight
that is monotone, capped, configurable and versioned, a plan that exposes its sizes, its
reserve and its budgets, and readings of the source announced up front (E14). The
selection of the rows is another lot (10b), but it needs a stable description of what it
must cover.

The plan could have been a member of `AnalysisPlan`, as the stratification advice is, or a
document of its own. The targets stand on the Scan and, when it is current, on the
second-pass document: the planner reads the Scan only. A plan of analyses also keeps an
identity (`plan_id`) that the second-pass document stores.

## Decision

- The plan is `SamplingPlan` (`scanner/smart/`), built by `plan_sampling` from a Scan and an
  optional second-pass document. It has its own `plan_id`; `AnalysisPlan` and its identity
  are untouched. Like every plan it reads no source, writes nothing, and holds no date, no
  measured time and no value of the data.
- A target is described by a predicate: a kind and references into the Scan (an entry of the
  sample, a pattern, a bin), so that the plan can be kept and shown without exposing data,
  and exposure is respected (a masked or hidden column has no target).
- A column whose every value has a target is a complete catalog (`catalog_complete`), and
  only then are those targets mandatory. A column whose table of values overflowed still
  gets targets for the values the Scan saw, all optional, with the guarantee
  `known_values_only`. The plan names the guarantee; it never presents the catalog of
  targets as every phenomenon of the data (SMART-13).
- A weight is `min(cap, base * (1 + gain * rarity))`, with the rarity on a logarithmic scale
  of the share of rows the target covers (neutral when unknown). It is monotone in the share
  and in the base and has a ceiling, so that a very rare target does not drown the others.
  The settings are in the plan, and the formula has a version.
- The reserve of ordinary rows is a share of the size asked for and gives way to mandatory
  targets (SMART-10). The plan is a budget of candidate rows in source text, not a promise of
  process memory.
- The readings of the source are announced: the first pass if no Scan is stored, the second
  pass if it was asked for and its document is not current, and the selection. Smart never
  runs a second pass by itself (rule R1), and the second pass and the selection are never
  merged: a row rejected before a statistic was known cannot be selected afterwards.
- The settings are a top-level `smart` object of the configuration file, outside `scan` and
  `deep`: they change a plan, never a stored result.

## Consequences

- A user asking for the plan pays one planning pass over the Scan in memory (about 30 ms on a
  million rows by 34 columns) and nothing else.
- Predicates are versioned (`PREDICATE_VERSION`): lot 10b reads them, so changing what a kind
  means changes that number.
- Targets that only a second pass can bring (exact bin counts, validated patterns, relation
  exceptions) are listed once its document is current, and announced as awaiting before.
- The plan is not written on disk yet, so it has no JSON Schema: the report of lot 10b
  (SMART-12) will carry it, with the coverage obtained.
- The initial values of the weights are to be validated on the demos. The time estimate and a
  confirmation threshold for the selection need its executor and come with lot 10b.
