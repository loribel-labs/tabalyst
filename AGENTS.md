# Tabalyst project instructions

## Project scope

Tabalyst is an alpha CSV profiling project. Its main workflow is:

```text
CSV -> global JSON profile -> interactive HTML report
```

The JSON format is intentionally experimental during the `0.1.0aX` series.
Breaking changes are allowed and migration support is not required yet.

## Source of truth

- This repository is the public source of truth for Tabalyst code and public documentation.
- Keep private strategy, personal notes, confidential data and unpublished research in `tabalyst-gb`, not here.
- Do not commit secrets, credentials or real sensitive datasets.

## Language

- Use English for source code, public documentation, report labels and user-facing project content.
- Conversation language may follow the user's preference.
- Keep technical names and JSON field names stable once documented.

## Architecture

- `src/tabalyst/analysis.py`: analysis logic without file or presentation concerns.
- `src/tabalyst/models.py`: Pydantic models serialized to the experimental JSON profile.
- `src/tabalyst/config.py`: validated configuration and defaults.
- `src/tabalyst/service.py`: reusable analysis boundary for the CLI and future API adapters.
- `src/tabalyst/reporting.py`: JSON-to-HTML rendering without CSV access.
- `src/tabalyst/cli.py`: command-line workflow and output management.
- `src/tabalyst/templates/` and `src/tabalyst/static/`: report presentation.

Read `README.md`, `docs/architecture.md` and the relevant configuration or format
changelog before changing shared behavior.

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
regression check described in `docs/architecture.md` at desktop and mobile sizes.
After every project modification, regenerate the reference report at
`reports/data/report.html` from `reports/data/report.json`.

Update `docs/progress.md` for meaningful work. Update the format changelog only
when the JSON structure or semantics change. Update release notes for release
milestones.

## Versioning

- Application versions use PEP 440, for example `0.1.0a1`.
- Git release tags use the matching `v` prefix, for example `v0.1.0a1`.
- During the alpha family, JSON uses `format_version: "0.1.0a"` and a monotonic
  `format_revision`.
- `execution.json` has its own `schema_version`.

Never create a commit, tag, push or release unless the user explicitly requests it.
