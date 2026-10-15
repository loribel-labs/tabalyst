# Datasets

The source files shared by the showcase demos, the cases and the documentation.
Every file is synthetic: people, addresses and amounts are fictional, and email
addresses use reserved `.example` domains. They hold no real data.

| File | Rows | Content |
| --- | --- | --- |
| `basic.csv` | 5 | A five-row smoke example |
| `insurance-customers.csv` | 3,000 | Fictional customer and contract records across 34 columns |
| `insurance-customers-100k.json` | 100,000 | The request that builds a larger insurance file, with 45 kinds of defect, 845 rows in all, outside the checkout (see below) |
| `orders.json` | 60 customers | A shop export with nested addresses, tags and orders |
| `web-events.jsonl` | 300 events | A web analytics log in JSON Lines, with three bad lines on purpose |
| `sales.xlsx` | 120 orders | A workbook with the sheets `Orders`, `Regions` and `Notes` |

Who uses each file (generated from the manifests by `tools/make_index.py`):

<!-- index:users:start -->
| File | Used by |
| --- | --- |
| `basic.csv` | `showcase/basic/` |
| `insurance-customers-100k.json` | `showcase/insurance-customers/`, `showcase/insurance-customers-scan/`, `cases/sample-real-errors/` |
| `insurance-customers.csv` | `cases/sample-injected-errors/` |
| `orders.json` | `showcase/orders/` |
| `sales.xlsx` | `showcase/sales/` |
| `web-events.jsonl` | `showcase/web-events/` |
<!-- index:users:end -->

`sales.xlsx` is written by `examples/tools/make_sales_workbook.py`, with the same
bytes on every run. Do not replace `insurance-customers.csv` without a separate
decision to change the published demo: the website copies its report.

`insurance-customers-100k.json` is a generation request, not data: the example `insurance`,
100,000 rows, a fixed seed and the anomaly profile `dirty_stress`, with the SHA-256 of the two
files it keeps (the altered CSV and its change log). The 27 MB CSV is never committed;
`python examples/tools/make_datasets.py` builds it outside the checkout, in
`D:/GIT.test/tabalyst/datasets/` (or `$TABALYST_DATASETS`), and reuses it while the SHA-256 matches.
`regenerate.py` calls the tool before the demos that read it, as `{datasets}/insurance-customers-100k.csv`.
The 3,000-row `insurance-customers.csv` stays for the cases and for anyone who wants a small file.

A dataset is public. Never add a real or confidential file here.
