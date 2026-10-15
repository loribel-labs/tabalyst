# Cases

A case is a small, reproducible scenario that tests a Tabalyst command (or a
group of them) and that documentation can quote. A case is more than a unit
test: it has an input, a stated expectation and a written result.

```text
examples/cases/<case-name>/
|-- README.md      what it checks, how to run it, the result (documentation source)
|-- case.json      the manifest: what the case runs, measures and expects
|-- case.py        builds the input, runs the commands, scores the output
`-- input/         the input files and, when injected, the truth about them
tests/cases/test_cases.py   one generic test, run by pytest on every case.json
```

A new case needs no new test file: `test_cases.py` reads each `case.json`.

## The manifest `case.json`

| Key | Holds |
| --- | --- |
| `id`, `title`, `tool`, `question` | the folder name, a short title, the command checked, the question asked |
| `inputs` | `source`, `dirty` and `truth`, and when the case is generated `injections` (the Generate request) and `changes` (its change log), paths relative to the case folder |
| `build` | the `script` (`case.py`) and the `seed` of the deterministic build |
| `runs` | per method, the command-line `args` and the `seeds` to measure |
| `measure` | the `sizes` measured and the `unit` of the table |
| `expectations` | the `run`, `rows` and `seed` that are tested, the classes `kept`, and the known `gaps` (each with a `class` and a `reason`, tested as strict `xfail`) |
| `publish` | `site` (true when tabalyst.com copies the case) and `docs`, the pages that quote it |
| `captures` | optional, reserved for automatic screenshots of the HTML pages |

`case.py` must provide `build_matches_input()`, `run(method, rows, seed, output)`
and `score(output)`; the generic test calls them.

Rules:

- The build is deterministic (fixed seeds), so `input/` can be rebuilt and
  compared. A test checks that the committed input is the build.
- Outputs go outside the checkout (`D:\GIT.test\tabalyst\artifacts`), never in the
  case folder.
- A gap that is known and accepted is listed in `expectations.gaps` and runs as an
  `xfail(strict=True)` test: the day it is fixed the test fails and the class moves
  to `kept`.
- The `README.md` of a case holds the commands and the measured result, written
  so that a documentation page can quote it.

Cases:

| Case | Checks |
| --- | --- |
| [`sample-injected-errors`](sample-injected-errors/README.md) | Which injected errors a `tabalyst sample --smart` keeps, against a random sample |
