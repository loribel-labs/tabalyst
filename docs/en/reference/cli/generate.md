---
title: "CLI: tabalyst generate"
description: The inputs, outputs and options of the tabalyst generate command.
---

`tabalyst generate` validates a YAML definition and writes synthetic CSV data.
It is available in Tabalyst 0.6.2 and later. See
[Tabalyst Generate](../../generate/index.md) for a walkthrough.

```text
tabalyst generate DEFINITION.yaml (-o FILE.csv | -d DIR) [options]
tabalyst generate --example crm (-o FILE.csv | -d DIR) [options]
```

Provide exactly one definition source: a YAML file or `--example crm` or
`--example insurance`. Exactly one destination is required.

| Option | Meaning |
| --- | --- |
| `--example NAME` | Use the packaged `crm` or `insurance` definition. |
| `-o`, `--output FILE` | Write one clean CSV. |
| `-d`, `--output-dir DIR` | Write all planned artifacts to a directory. |
| `--rows N` | Override the generated row count; for insurance, allocate the combined total across its branches. |
| `--seed INTEGER` | Override the root random seed. |
| `--as-of-date YYYY-MM-DD` | Override the reference date. |
| `--anomaly-profile NAME` | Produce the selected anomaly variant, cell change log and summary. Requires `-d`. |
| `-f`, `--force` | Replace existing generated artifacts. |

Explicit options override YAML defaults. Paths are checked before generation;
the definition and packaged resources cannot be overwritten. A selected
anomaly profile keeps the clean CSV alongside its altered variant.
