# The second pass inside Report, and the validation of patterns

Date: 2026-10-09 (lot 7c of the Scan and JSON work)

## Context

`tabalyst report` is the command people run. Its decision P8 is to add the
second pass by itself when it has a benefit and a low cost, under deterministic
budgets, and to force it with `--deep`. The patterns of the Scan were inferred from
a sample of distinct values, and the dates of a column were only summarized by their
minimum, maximum and years. Two things had to be chosen: where the second pass lives in
the Report (and what the Report carries of it), and how patterns are validated on every
occurrence without a pathological cost.

## Decision

- The Report embeds the second-pass document whole under `analyses`, with how it was
  decided (`auto`, `forced`, `off`) and how it ended (`ran`, `reused`, `nothing_selected`,
  `disabled`, `unavailable`, `failed`). The renderer reads that member and nothing else.
- `tabalyst report --scan` reads no source (it already promises not to). What the Scan and
  the stored `<stem>.deep.json` answer is in the report; the rest is `skipped`, with a reason.
  `--deep` reads the source beside the document and fails, exit code 4, when it is not there.
- `deep.mode` (`auto`, `off`, `force`) is for scripts; it lives in `DeepSection`, outside the
  settings the second-pass document records, so changing it never makes a result stale.
  `tabalyst scan --deep` is explicit and ignores it.
- An automatic second pass that fails (the source changed) does not fail the report; a forced
  one does.
- A forced batch asks once, after the sources are scanned and before any is read again; the
  Scans stay in memory until the answer (the precedent of `prepare_deep`). An automatic report
  is finished source by source and never asks.
- Patterns are validated with the matcher of the inference. An ASCII value is read by a
  compiled regular expression whose every repeat is possessive, which is the semantics of
  the greedy matcher of the grammar and cannot backtrack; any other value goes through the
  token matcher. A test compares them on random signatures and values.
- A field whose inference read every distinct value needs no reading: the same classification
  runs over the exact counts the Scan lists.
- Dates are placed by the date as written, without converting the offset, so a change of
  daylight saving time moves nothing and a date stays on the day its text says.
- A period counter remembers up to 16,384 raw strings of its column, charged to the plan, so
  the date detector reads each distinct date once for the whole file.

## Consequences

- A Report of 1 million rows by 34 columns takes more time by default: the automatic selection
  is allowed up to 100 million cells of the moderate CPU class (decision O36), and the
  measured overhead is in `docs/dev/scan/benchmarks.md`. The budgets are the lever if it is
  too much; they are deterministic and recorded in the plan.
- The Report JSON grows by the embedded second-pass document (about 0.4 MB for the combined
  file; the plan lists every candidate).
- A Report of a scan document has fewer analyses than the report of its source, by design.
- `deep.json` is written by `report` too, so a second report, or one that changes only the
  presentation, reads nothing.
