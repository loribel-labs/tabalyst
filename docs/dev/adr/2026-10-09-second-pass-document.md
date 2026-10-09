# The second pass is a separate document keyed by what each result depends on

Status: accepted on 2026-10-09 (maintainer, lot 7a of the Scan and JSON work).

## Context

The second pass adds analyses to a finished Scan (histograms, exact medians) by
reading the source again. The Scan must stay what it is: the file the first pass
wrote, valid as long as its source, configuration and engine are. A Report must
be able to carry what it shows. The settings of a histogram (the number of bins)
are a choice of the second pass, not a property of the data the Scan describes.
A result can be costly to compute and must not be recomputed for a change that
does not touch it.

## Decision

- The result is its own document, `tabalyst.scan.deep` (`<stem>.deep.json`,
  `deep.json` beside the shared `scan.json`), written atomically and never
  merged into the Scan. It carries the identity of the Scan it stands on, the
  plan that was run, the settings and one entry per analysis.
- Each entry has a key: the Scan, the analyzer and its version, the field, the
  method with its effective parameters and the domain of the values. Budgets and
  costs are not in it. A run keeps the complete entries that have the key it
  would give and computes only the others.
- A document of another Scan, engine, format or revision is ignored and
  rebuilt, never migrated.
- The `deep` settings (`bins`, `bin_strategy`) are a top-level object of the
  configuration files, outside `ScanConfig`: they are not in the configuration
  hash of the Scan, so changing them never makes it stale. They enter the key of
  the analyses that use them.
- The Python entries are `run_second_pass`, `prepare_deep`, `execute_deep` and
  `generate_deep`. `tabalyst.scan(..., deep=True)`, as the first drafts had it,
  is not kept: `scan` returns the `ScanResult` of the first pass and the second
  pass does not touch its signature or its speed. None of the entries prompts.
- The executor replays the first pass's reading of a cell with the same
  normalizer, classifier and number detector, and every result is checked against
  the counts of the Scan before it is kept.

## Consequences

- The Scan file is byte for byte what the first pass wrote (A12), and a second
  pass can be repeated, completed or thrown away without touching it.
- A change of the number of bins recomputes the histograms and nothing else; a
  change of budget recomputes nothing.
- Two files describe a source. A Report embeds the part it shows (lot 7c) and a
  reader that wants the whole joins them by the identity of the base.
- A new analyzer adds entries and a version; the format revision moves only when
  the shape of the document does.

Revisit if the Report chain of lot 7c needs the settings in the identity of the
Scan, or if a second-pass document should be kept in a store of its own.
