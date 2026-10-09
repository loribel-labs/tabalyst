# The second pass has two memory levels and keeps time out of the plan

Status: accepted on 2026-10-08 (maintainer, lot 6b of the Scan and JSON work).

## Context

Rule R1 of the design (smart by default, explicit when costly) needs an
automatic choice that is cheap and a forced one that may cost more but never
without warning. The plan must stay the same for the same Scan on any machine,
so it cannot hold a measured time. The memory of a forced analysis cannot be
lifted at will: an exact distinct count that does not fit is a failure of the
machine, not a choice.

## Decision

- Two memory levels in the budgets of the planner: 128 MiB for what it picks by
  itself, 512 MiB as a hard budget for requests and forced plans, which no
  request lifts. The same applies to cells and CPU class, which only limit the
  automatic choice.
- A selection beyond an automatic limit requires a confirmation. The plan lists
  the limits it exceeds in `summary.beyond_automatic`, deterministic like the
  rest of it.
- The estimated time (a range from the first pass of the Scan) is computed
  outside the plan by `estimate_time` and adds one reason, `time_over_threshold`,
  at 120 seconds on its upper bound. It never enters `plan_id`.
- The cost constants live in one module, `scanner/planner/costmodel.py`, and are
  versioned by `cost_model_version`.

## Consequences

- An automatic plan never asks; asking is a property of requests, forcing and
  long runs.
- A change of a constant changes the plan; the version tells it.
- The CPU classes stand on proxy measures until the executor (lot 7a) measures
  its own; the memory model of the exact set is replaced at lot 7b.

Revisit if the automatic level proves too low for the Report at lot 7c, or if a
machine-independent measure of time becomes available.
