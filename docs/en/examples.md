---
title: Examples and demos
description: Synthetic example datasets and their generated reports, JSON profiles and column pages, to try Tabalyst before using your own data.
---

The Tabalyst repository includes small, synthetic datasets with their generated
outputs. None of them contains real personal data. Use them to see what
Tabalyst produces before running it on your own files.

## Live demo

- [Example report](https://tabalyst.com/examples/report.html): the interactive
  HTML report of the insurance customers dataset.
- [Example JSON profile](https://tabalyst.com/examples/report.json): the
  profile that the report is rendered from.

## Datasets

| Input | Content | What it shows |
| --- | --- | --- |
| `basic.csv` | Five rows | A smoke test of the whole workflow |
| `insurance-customers.csv` | 3,000 fictional customers and contracts, 34 columns | A realistic CSV report, with `--details` column pages |
| `orders.json` | 60 customers with nested addresses, tags and orders | A JSON report on the one collection `$.customers[]` that Inspect finds |
| `web-events.jsonl` | 300 events with nested `user` and `device` objects, plus three bad lines | A partial JSONL report: the bad lines are excluded and counted |

Email addresses use reserved `.example` domains, and all people and identifiers
are fictional.

## Regenerate the outputs

Clone the repository at
[github.com/loribel-labs/tabalyst](https://github.com/loribel-labs/tabalyst),
install Tabalyst and run, from the repository root:

```console
tabalyst report examples/input/basic.csv -o examples/output/basic/report.html --config examples/config.json --force
tabalyst report examples/input/insurance-customers.csv -o examples/output/insurance-customers/report.html --config examples/config.json --details --force
tabalyst report examples/input/orders.json -o examples/output/orders/report.html --config examples/config.json --force
tabalyst report examples/input/web-events.jsonl -o examples/output/web-events/report.html --config examples/config.json --force
```

Each output folder holds an HTML report, a JSON profile and a cumulative
`executions.json`. The insurance example also has one HTML page per column under
`report/`.

## Next steps

- [Create your first report](report/getting-started.md) with a file of your own.
- [Report JSON files](report/json.md) to understand the
  `orders.json` and `web-events.jsonl` examples.
