# Execution history

Every successful `tabalyst analyze` command updates `execution.json` in the HTML
report's output folder. The file provides a lightweight performance history for
comparing reports as Tabalyst and its configuration evolve.

Given this command:

```powershell
python -m tabalyst analyze data.csv -o reports\data\report1.html
```

Tabalyst writes `report1.html`, `report1.json`, and `execution.json` in
`reports\data`. A later `report2.html` run adds a second item to the existing
history. Only filenames are stored because all generated files share one folder.

## Format

```json
{
  "schema_version": "1.0",
  "executions": [
    {
      "timestamp": "2026-09-18T14:32:10Z",
      "tabalyst_version": "0.1.0a1",
      "source_file": "data.csv",
      "html_file": "report1.html",
      "json_file": "report1.json",
      "rows": 3000,
      "columns": 34,
      "analysis_seconds": 0.6527,
      "total_seconds": 0.9314,
      "git": {
        "available": true,
        "commit": "a1b2c3d4e5f6...",
        "dirty": true,
        "state": "a1b2c3d4+working"
      }
    }
  ]
}
```

`analysis_seconds` covers CSV ingestion and profiling. `total_seconds` also covers
JSON serialization and HTML rendering. The Tabalyst package version is always
recorded. Git metadata is included when the command runs inside a checkout; an
installed production run outside Git uses `available: false` and null values.

The complete history is rewritten through a temporary file and atomically replaced
after each successful analysis. Failed analyses do not add entries. The schema is
experimental and may change during alpha development.
