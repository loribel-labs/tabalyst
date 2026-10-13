# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Collect Computer catalog CSVs into a reviewable Markdown snapshot."""

from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_FILE = "csv_files.md"
RECURSIVE = False          # True = inclure les sous-dossiers
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252")
PAUSE_ON_EXIT = True       # Garder la console ouverte après exécution

# ============================================================
# SCRIPT
# ============================================================

def read_csv(path: Path) -> str:
    """Read a catalog CSV using the supported source encodings."""
    for encoding in ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Impossible de lire : {path.name}")


def main() -> None:
    """Write a Markdown snapshot beside the Computer CSV files."""
    # Dossier contenant le script Python
    folder = Path(__file__).resolve().parent
    output = folder / OUTPUT_FILE

    pattern = "**/*.csv" if RECURSIVE else "*.csv"
    csv_files = sorted(folder.glob(pattern))

    if not csv_files:
        print("Aucun fichier CSV trouvé.")
        return

    sections = []

    for csv_file in csv_files:
        relative_path = csv_file.relative_to(folder)

        try:
            content = read_csv(csv_file).strip()

            sections.append(
                f"### {relative_path.as_posix()}\n\n"
                f"```csv\n{content}\n```\n\n"
                f"---"
            )

            print(f"OK : {relative_path}")

        except (OSError, UnicodeError, ValueError) as exc:
            print(f"ERREUR : {relative_path} - {exc}")

    output.write_text(
        "\n\n".join(sections) + "\n",
        encoding="utf-8"
    )

    print(f"\nFichier généré : {output.name}")
    print(f"CSV traités : {len(sections)}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"\nERREUR : {exc}")
    finally:
        if PAUSE_ON_EXIT:
            input("\nAppuyez sur Entrée pour fermer...")
