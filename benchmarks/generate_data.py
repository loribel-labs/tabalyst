"""Generate deterministic synthetic datasets for Tabalyst benchmarks.

All people, contacts and identifiers are fictional. Values deliberately mix
clean and imperfect representations so benchmarks exercise type inference,
normalization and future detectors, not only raw reading speed.

    python benchmarks/generate_data.py --rows 100000 -o benchmarks/data/synthetic-100k.csv
    python benchmarks/generate_data.py --rows 100000 -o benchmarks/data/synthetic-100k.json
"""

import argparse
import csv
import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

FIRST_NAMES = [
    "Alice", "Amélie", "Benoît", "Camille", "Chloé", "David", "Élodie", "Emma",
    "Félix", "Gabriel", "Hélène", "Hugo", "Inès", "Jacob", "Jade", "Karim",
    "Laura", "Léa", "Liam", "Louis", "Maya", "Mia", "Noah", "Olivia", "Omar",
    "Paul", "Raphaël", "Rose", "Samuel", "Sofia", "Thomas", "Zoé",
]
LAST_NAMES = [
    "Tremblay", "Gagnon", "Roy", "Côté", "Bouchard", "Gauthier", "Morin",
    "Lavoie", "Fortin", "Gagné", "Ouellet", "Pelletier", "Bélanger", "Lévesque",
    "Bergeron", "Leblanc", "Paquette", "Girard", "Simard", "Boucher", "Smith",
    "Brown", "Wilson", "Martin", "Nguyen", "Singh", "Chen", "Garcia",
]
CITIES = [
    "Montréal", "Québec", "Laval", "Gatineau", "Longueuil", "Sherbrooke",
    "Saguenay", "Lévis", "Trois-Rivières", "Toronto", "Ottawa", "Vancouver",
    "Calgary", "Edmonton", "Winnipeg", "Halifax", "Moncton", "Regina",
]
# Several representations of the same province are intentional.
PROVINCES = [
    "Québec", "Québec", "Québec", "QUÉBEC", "Quebec", " Québec ", "Ontario",
    "Ontario", "British Columbia", "Alberta", "Manitoba", "Saskatchewan",
    "Nova Scotia", "New Brunswick", "Newfoundland and Labrador",
    "Prince Edward Island",
]
STATUSES = ["active", "active", "active", "pending", "suspended", "closed", "trial"]
BOOLEANS = ["true", "false", "true", "false", "yes", "no"]
AREA_CODES = ["514", "438", "450", "418", "613", "416", "604", "403"]
POSTAL_LETTERS = "ABCEGHJKLMNPRSTVXY"
WORDS = [
    "data", "customer", "contract", "renewal", "claim", "premium", "coverage",
    "policy", "payment", "address", "change", "request", "pending", "review",
    "approved", "urgent", "follow", "call", "email", "note", "agent", "branch",
    "update", "missing", "document", "signature", "quote", "vehicle", "home",
]

FIELDS = [
    "id", "customer_uuid", "first_name", "last_name", "email", "phone",
    "postal_code", "city", "province", "birth_date", "signup_date", "amount",
    "amount_fr", "quantity", "score", "active", "status", "comment", "code", "ip",
]


def _phone(rng: random.Random) -> str:
    area = rng.choice(AREA_CODES)
    middle = rng.randint(200, 999)
    last = rng.randint(0, 9999)
    return rng.choice(
        [
            f"({area}) {middle}-{last:04d}",
            f"{area}-{middle}-{last:04d}",
            f"+1 {area} {middle} {last:04d}",
            f"{area}{middle}{last:04d}",
        ]
    )


def _postal_code(rng: random.Random) -> str:
    letters = [rng.choice(POSTAL_LETTERS) for _ in range(3)]
    digits = [str(rng.randint(0, 9)) for _ in range(3)]
    first = f"{letters[0]}{digits[0]}{letters[1]}"
    second = f"{digits[1]}{letters[2]}{digits[2]}"
    separator = rng.choice([" ", " ", " ", ""])
    return f"{first}{separator}{second}"


def _record(rng: random.Random, index: int) -> dict[str, object]:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    email = f"{first}.{last}{index}@example.com".lower().replace(" ", "")
    if rng.random() < 0.005:
        email = email.replace("@", ".")
    birth = date(1940, 1, 1) + timedelta(days=rng.randrange(365 * 65))
    signup = date(2015, 1, 1) + timedelta(days=rng.randrange(365 * 11))
    amount = round(rng.uniform(0, 5000), 2)
    comment = (
        ""
        if rng.random() < 0.2
        else " ".join(rng.choices(WORDS, k=rng.randint(1, 30)))
    )
    return {
        "id": index,
        "customer_uuid": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        "first_name": first,
        "last_name": last,
        "email": email,
        "phone": "" if rng.random() < 0.05 else _phone(rng),
        "postal_code": _postal_code(rng),
        "city": rng.choice(CITIES),
        "province": rng.choice(PROVINCES),
        "birth_date": birth.isoformat(),
        "signup_date": f"{signup.day:02d}/{signup.month:02d}/{signup.year}",
        "amount": amount,
        "amount_fr": f"{amount:.2f}".replace(".", ","),
        "quantity": rng.randint(0, 100),
        "score": None if rng.random() < 0.05 else round(rng.gauss(50, 15), 3),
        "active": rng.choice(BOOLEANS),
        "status": rng.choice(STATUSES),
        "comment": comment,
        "code": (
            str(rng.randint(1000, 99999))
            if rng.random() < 0.97
            else f"A{rng.randint(100, 999)}"
        ),
        "ip": ".".join(str(rng.randint(0, 255)) for _ in range(4)),
    }


def _csv_value(field: str, value: object) -> str:
    if value is None:
        return "N/A"
    if field == "amount":
        return f"{value:.2f}"
    return str(value)


def write_csv(path: Path, rows: int, seed: int) -> None:
    rng = random.Random(seed)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(FIELDS)
        for index in range(1, rows + 1):
            record = _record(rng, index)
            writer.writerow(_csv_value(field, record[field]) for field in FIELDS)


def write_json(path: Path, rows: int, seed: int) -> None:
    """Write one root array with nested orders, nulls and a late optional field."""
    rng = random.Random(seed)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("[\n")
        for index in range(1, rows + 1):
            record = _record(rng, index)
            record["active"] = record["active"] in {"true", "yes"}
            record["address"] = (
                None
                if rng.random() < 0.05
                else {
                    "city": record.pop("city"),
                    "province": record.pop("province"),
                    "postal_code": record.pop("postal_code"),
                }
            )
            record["orders"] = [
                {
                    "sku": f"SKU-{rng.randint(1, 500):04d}",
                    "amount": round(rng.uniform(1, 800), 2),
                    "quantity": rng.randint(1, 5),
                }
                for _ in range(rng.randint(0, 3))
            ]
            if index > rows * 0.9:
                record["loyalty_tier"] = rng.choice(["silver", "gold", "platinum"])
            separator = ",\n" if index < rows else "\n"
            stream.write(json.dumps(record, ensure_ascii=False) + separator)
        stream.write("]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path; the .csv or .json suffix selects the format.",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    suffix = args.output.suffix.lower()
    if suffix == ".csv":
        write_csv(args.output, args.rows, args.seed)
    elif suffix == ".json":
        write_json(args.output, args.rows, args.seed)
    else:
        parser.error("output must end in .csv or .json")


if __name__ == "__main__":
    main()
