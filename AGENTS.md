# Tabalyst project instructions

## Project scope

Tabalyst is a beta toolkit for understanding unfamiliar structured data. Its
current Report workflow is:

```text
CSV/JSON -> Scan -> global JSON profile -> interactive HTML report
```

Tabalyst is presented as beta until its first stable 1.0 release. The JSON
format remains experimental during beta. Its historical `0.1.0a` format
identifier is retained; breaking changes are allowed and migration support is
not yet required. Record format changes in the relevant changelogs.

## Source of truth

- This repository is the public source of truth for Tabalyst code and public documentation.
- Keep private strategy, personal notes, confidential data and unpublished research in `tabalyst-gb`, not here.
- The sibling `../tabalyst-gb` is the private starting point for the maintainer's
  AI requests. For work originating there, read `../tabalyst-gb/AGENTS.md` and
  its relevant `DOCS/` pages for intent and decisions. Verify product behavior
  against this public repository before changing code or public documentation.
- Do not commit secrets, credentials or real sensitive datasets.
- The sibling repository `tabalyst-studio` holds the documentation site
  (`docs.tabalyst.com`), public website (`tabalyst.com`), brand guidelines and
  DNS references. It consumes this repository: the documentation site imports
  `docs/en/` and `docs/fr/`, and the website copies
  `examples/output/insurance-customers/`. The website
  only advertises features documented in this `README.md`. When a change affects
  the CLI, the public API, the report or the demos, mention the follow-up needed
  in `tabalyst-studio` (see its `AGENTS.md`), but do not edit it unless asked.

## Language

- Use English for source code, public documentation, report labels and user-facing project content.
- Conversation language may follow the user's preference.
- Keep technical names and JSON field names stable once documented.

## Architecture

- `src/tabalyst/report_profile.py`: report profile built from a Scan result,
  without file or presentation concerns.
- `src/tabalyst/models.py`: Pydantic models serialized to the experimental JSON profile.
- `src/tabalyst/scan_reuse.py`: scan documents reused by the report, with the
  staleness rule.
- `src/tabalyst/config.py`: validated configuration and defaults.
- `src/tabalyst/service.py`: reusable analysis boundary for the CLI and future API adapters.
- `src/tabalyst/batch.py`: glob resolution, output planning, collision
  protection and atomic writes shared by the commands.
- `src/tabalyst/report_service.py`, `sampling_service.py`, `scan_service.py`:
  batch planning and execution of each command.
- `src/tabalyst/progress.py`: presentation-neutral engine progress events.
- `src/tabalyst/reporting.py`: JSON-to-HTML rendering without CSV access.
- `src/tabalyst/cli/`: thin command adapters, error presentation and terminal
  output management.
- `src/tabalyst/templates/` and `src/tabalyst/static/`: report presentation.

Read `README.md`, `docs/dev/architecture.md` and the relevant configuration or
format changelog (`docs/en/reference/`) before changing shared behavior.

Tabalyst Scan, the future core analysis engine (`src/tabalyst/scanner/`), is
built in lots. Before working on it, read `docs/dev/scan/plan.md` (lots,
status, models, sessions) and `docs/dev/scan/design.md` (the contract). Its
contract tests in `tests/scan/` are enabled lot by lot.

## Development workflow

Use the existing patterns and keep changes focused. Preserve user changes already
present in the working tree. Use `apply_patch` for manual edits and avoid unrelated
refactors.

After Python changes:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

After report JavaScript or CSS changes, regenerate a report and run the browser
regression check described in `docs/dev/architecture.md` at desktop and mobile sizes.
After every project modification, regenerate the public demos using the commands
in `examples/README.md`. Use the `insurance-customers` output for browser checks.

Update `docs/dev/progress.md` for meaningful work. Update
`docs/en/reference/profile-format-changelog.md` only when the JSON structure or
semantics change. Update release notes in `docs/dev/releases/` for release
milestones.

For release preparation, also update the private release status and feature
summaries in `../tabalyst-gb/DOCS/` and note the work in its progress log.
Check the documentation and website changes in `../tabalyst-studio` against
the public README and released tag. Keep prepared, committed, tagged and
published states distinct in all three repositories.

## Documentation

`docs/` holds the sources of the public documentation site (docs.tabalyst.com,
built by `tabalyst-studio` from the latest release tag) and the maintainer
documentation. See `docs/README.md`.

- `docs/en/`: user documentation, published, organized as `tutorials/`,
  `how-to/`, `reference/` and `explanation/`.
- `docs/fr/`: French translation of `docs/en/`, published under `/fr/`.
- `docs/dev/`: maintainer documentation, never published.

Writing and translation rules for `docs/en/` and `docs/fr/`:

1. English is the source of truth. French is always derived from English, never
   the reverse.
2. Never translate commands, CLI options, JSON keys, module names, file paths or
   product names.
3. "Tabalyst" is always one word with a capital T only. "Tabalyst" is the
   toolkit; "Tabalyst Report" is a tool included in it; users always install
   Tabalyst, never "Tabalyst Report".
4. Every page is self-contained: an AI may retrieve a single page or section.
5. Put the essentials first on each page (what it does, command, result), then
   details.
6. No essential content in images or JavaScript-only components. Prefer plain
   `.md` over `.mdx`.
7. Only document what is available in the latest release published on PyPI.
   Document a feature in the same change that implements it, so the docs ship
   with the release.
8. Slugs are in English in both languages, with the same file names and folders.
9. Use the terms of `docs/en/reference/glossary.md` in every translation.
10. Pages start with a `title` and `description` frontmatter and have no `# H1`.

When a user-facing behavior changes, update the matching page in `docs/en/`.
The contents of `docs/en/` and `docs/fr/` are licensed under CC BY 4.0
(`docs/LICENSE`); the code stays MIT.

## Versioning

- Application versions use PEP 440, for example `0.1.0a1`.
- Git release tags use the matching `v` prefix, for example `v0.1.0a1`.
- The existing JSON format family uses `format_version: "0.1.0a"` and a monotonic
  `format_revision`.
- `executions.json` has its own `schema_version`.

Never create a commit, tag, push or release unless the user explicitly requests it.
