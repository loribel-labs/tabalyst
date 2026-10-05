"""Write ``input/sales.xlsx``, the synthetic Excel example of Tabalyst.

Only needed to regenerate the input: ``pip install xlsxwriter``, then run
``python examples/make_sales_workbook.py`` from the repository root. The output is
the same on every run (fixed seed and creation date). All people, addresses and
amounts are fictional; email addresses use the reserved ``.example`` domain.
"""

import random
from datetime import date, datetime
from pathlib import Path

import xlsxwriter

OUTPUT = Path(__file__).parent / "input" / "sales.xlsx"
REGIONS = [
    ("North", "Lille", 4),
    ("West", "Nantes", 7),
    ("South", "Marseille", 9),
    ("East", "Strasbourg", 5),
    ("Center", "Lyon", 6),
]
CHANNELS = ["web", "store", "phone"]
FIRST = ["Ana", "Bruno", "Chloe", "David", "Emma", "Farid", "Gaelle", "Hugo"]
LAST = ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Simon", "Michel"]


def main() -> None:
    rng = random.Random(42)
    book = xlsxwriter.Workbook(str(OUTPUT))
    book.set_properties({"created": datetime(2026, 10, 1, 9, 0, 0)})  # noqa: DTZ001
    day = book.add_format({"num_format": "yyyy-mm-dd"})
    money = book.add_format({"num_format": "0.00"})

    orders = book.add_worksheet("Orders")
    orders.write(0, 0, "Synthetic sales export")
    orders.write(1, 0, "Fictional data for the Tabalyst examples")
    header = ["order_id", "order_date", "customer", "email", "region", "channel"]
    header += ["quantity", "unit_price", "paid"]
    for column, name in enumerate(header):
        orders.write(3, column, name)
    for index in range(1, 121):
        row = 3 + index
        first, last = rng.choice(FIRST), rng.choice(LAST)
        orders.write_string(row, 0, f"SO-{index:04d}")
        ordered = date.fromordinal(date(2026, 1, 1).toordinal() + index * 2 % 150)
        orders.write_datetime(row, 1, ordered, day)
        orders.write_string(row, 2, f"{first} {last}")
        orders.write_string(row, 3, f"{first}.{last}{index}@shop.example".lower())
        orders.write_string(row, 4, rng.choice(REGIONS)[0])
        orders.write_string(row, 5, rng.choice(CHANNELS))
        orders.write_number(row, 6, rng.randint(1, 12))
        orders.write_number(row, 7, round(rng.uniform(4, 180), 2), money)
        if index % 9:
            orders.write_boolean(row, 8, rng.random() > 0.2)

    regions = book.add_worksheet("Regions")
    for column, name in enumerate(["region", "hub", "stores"]):
        regions.write(0, column, name)
    for row, values in enumerate(REGIONS, start=1):
        for column, value in enumerate(values):
            regions.write(row, column, value)

    notes = book.add_worksheet("Notes")
    notes.write(0, 0, "Orders holds the sales; Regions is a small lookup table.")
    book.close()


if __name__ == "__main__":
    main()
