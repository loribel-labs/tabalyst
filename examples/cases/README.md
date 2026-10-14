# Cases

A case is a small, reproducible scenario that tests a Tabalyst command (or a
group of them) and that documentation can quote. A case is more than a unit
test: it has an input, a stated expectation and a written result.

```text
examples/cases/<case-name>/
|-- README.md      what it checks, how to run it, the result (documentation source)
|-- case.py        builds the input, runs the commands, scores the output
`-- input/         the input files and, when injected, the truth about them
tests/cases/test_<case_name>.py   the expectations, run by pytest
```

Rules:

- The build is deterministic (fixed seeds), so `input/` can be rebuilt and
  compared. A test checks that the committed input is the build.
- Outputs go outside the checkout (`D:\GIT.test\tabalyst\artifacts`), never in the
  case folder.
- A gap that is known and accepted is an `xfail(strict=True)` test: the day it is
  fixed the test fails and the expectation moves to the passing group.
- The `README.md` of a case holds the commands and the measured result, written
  so that a documentation page can quote it.

Cases:

| Case | Checks |
| --- | --- |
| [`sample-injected-errors`](sample-injected-errors/README.md) | Which injected errors a `tabalyst sample --smart` keeps, against a random sample |
