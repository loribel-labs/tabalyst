# Datasets

The source files shared by the showcase demos, the cases and the documentation.
Every file is synthetic: people, addresses and amounts are fictional, and email
addresses use reserved `.example` domains. They hold no real data.

| File | Rows | Content | Used by |
| --- | --- | --- | --- |
| `basic.csv` | 5 | A five-row smoke example | `showcase/basic/` |
| `insurance-customers.csv` | 3,000 | Fictional customer and contract records across 34 columns | `showcase/insurance-customers/`, `showcase/insurance-customers-scan/`, `cases/sample-injected-errors/` |
| `orders.json` | 60 customers | A shop export with nested addresses, tags and orders | `showcase/orders/` |
| `web-events.jsonl` | 300 events | A web analytics log in JSON Lines, with three bad lines on purpose | `showcase/web-events/` |
| `sales.xlsx` | 120 orders | A workbook with the sheets `Orders`, `Regions` and `Notes` | `showcase/sales/` |

`sales.xlsx` is written by `examples/tools/make_sales_workbook.py`, with the same
bytes on every run. Do not replace `insurance-customers.csv` without a separate
decision to change the published demo: the website copies its report.

A dataset is public. Never add a real or confidential file here.
