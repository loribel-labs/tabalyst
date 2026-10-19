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
| `insurance-customers-100k.json` | The request for 100,000 fictional customers and contracts, 34 columns, with 45 kinds of defect (845 rows in all) | A realistic single-file CSV report, built on a file generated outside the repository |
| `insurance-customers.csv` | 3,000 fictional customers and contracts, 34 columns | A small file for the walkthroughs and the sample commands |
| `orders.json` | 60 customers with nested addresses, tags and orders | A JSON report on the one collection `$.customers[]` that Inspect finds |
| `web-events.jsonl` | 300 events with nested `user` and `device` objects, plus three bad lines | A partial JSONL report: the bad lines are excluded and counted |
| `sales.xlsx` | A workbook of 120 fictional orders under two title lines, a five-row `Regions` sheet and a note | An Excel report on the sheet `$.Orders` that Inspect selects over `$.Regions` |

Email addresses use reserved `.example` domains, and all people and identifiers
are fictional.

## Regenerate the outputs

Clone the repository at
[github.com/loribel-labs/tabalyst](https://github.com/loribel-labs/tabalyst),
install Tabalyst and run, from the repository root:

```console
tabalyst report examples/datasets/basic.csv -o examples/showcase/basic/report.html --config examples/config.json --force
tabalyst report examples/datasets/orders.json -o examples/showcase/orders/report.html --config examples/config.json --force
tabalyst report examples/datasets/web-events.jsonl -o examples/showcase/web-events/report.html --config examples/config.json --force
tabalyst report examples/datasets/sales.xlsx -o examples/showcase/sales/report.html --config examples/config.json --force
```

The insurance report reads a 27 MB file that the repository does not store: it is
generated, with a fixed seed and a checked SHA-256, by
`python examples/tools/make_datasets.py`. From a clone,
`python examples/tools/regenerate.py` builds it when needed and runs the steps of
every demo, as listed in the `demo.json` of each folder under
`examples/showcase/`.

Each output folder holds an HTML report, a JSON profile and a cumulative
`executions.json`. The insurance example also has one HTML page per column under
`report/`.

## Next steps

- [Create your first report](first-report.md) with a file of your own.
- [Report JSON and JSONL files](../report/json.md) to understand the
  `orders.json` and `web-events.jsonl` examples, and
  [Report Excel workbooks](../report/excel.md) for `sales.xlsx`.
