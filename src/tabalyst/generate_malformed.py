# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Isolated malformed and syntax-corrupted CSV files generator (SRS §14, D13).

These artifacts test parser and profiling engine resilience against low-level structural corruption:
truncated lines, unclosed double quotes, inconsistent delimiter counts, and illegal UTF-8 byte encodings.
Per decision D13, these malformed test files are strictly isolated from reference benchmark datasets
to ensure exploration, sampling, and ML workflows are never accidentally corrupted.
"""

from __future__ import annotations

from pathlib import Path


def generate_malformed_csvs(
    source_csv: Path,
    output_dir: Path,
    *,
    max_source_rows: int = 100,
) -> dict[str, Path]:
    """Generate isolated syntactically malformed CSV files for parser stress benchmarks.

    Reads clean records from ``source_csv`` and writes four distinct corrupted files into
    ``output_dir``:
    - ``malformed_corrupted_separators.csv``: Lines with erratic delimiter counts.
    - ``malformed_truncated_lines.csv``: Truncated records without end-of-line delimiters.
    - ``malformed_unclosed_quotes.csv``: Unclosed quote absorbing subsequent lines.
    - ``malformed_invalid_encoding.csv``: Non-decodable invalid UTF-8 byte sequences.

    Returns a mapping from corruption scenario name to the generated file path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_text = source_csv.read_text(encoding="utf-8")
    lines = raw_text.splitlines()[:max_source_rows]
    if len(lines) < 2:
        raise ValueError(f"source_csv {source_csv} requires at least a header and one row")

    header = lines[0]
    data_rows = lines[1:]
    results: dict[str, Path] = {}

    # 1. Corrupted separators: inject extra delimiters on some rows and remove them on others
    sep_path = output_dir / "malformed_corrupted_separators.csv"
    corrupted_sep_lines = [header]
    for idx, row in enumerate(data_rows):
        if idx % 5 == 1:
            # Extra commas injected at end of row
            corrupted_sep_lines.append(f"{row},,,,,")
        elif idx % 5 == 3:
            # Truncated column fields (drop half of commas)
            parts = row.split(",")
            corrupted_sep_lines.append(",".join(parts[: max(1, len(parts) // 2)]))
        else:
            corrupted_sep_lines.append(row)
    sep_path.write_text("\n".join(corrupted_sep_lines) + "\n", encoding="utf-8", newline="\n")
    results["corrupted_separators"] = sep_path

    # 2. Truncated lines: abruptly cut a line in the middle of a token without a newline terminator
    trunc_path = output_dir / "malformed_truncated_lines.csv"
    trunc_lines = [header]
    for idx, row in enumerate(data_rows):
        if idx == len(data_rows) - 1:
            # Abrupt cutoff at the 15th character of the last row
            trunc_lines.append(row[: min(15, len(row))])
        else:
            trunc_lines.append(row)
    # No trailing newline on the truncated file
    trunc_path.write_text("\n".join(trunc_lines), encoding="utf-8", newline="")
    results["truncated_lines"] = trunc_path

    # 3. Unclosed quotes: insert an opening double-quote that is never closed
    unclosed_path = output_dir / "malformed_unclosed_quotes.csv"
    unclosed_lines = [header]
    for idx, row in enumerate(data_rows):
        if idx == 2:
            # Inject opening quote on the second column
            parts = row.split(",", 2)
            if len(parts) >= 2:
                unclosed_lines.append(f'{parts[0]},"UNCLOSED_QUOTE_START_{parts[1]},{parts[2] if len(parts) > 2 else ""}')
            else:
                unclosed_lines.append(f'"{row}')
        else:
            unclosed_lines.append(row)
    unclosed_path.write_text("\n".join(unclosed_lines) + "\n", encoding="utf-8", newline="\n")
    results["unclosed_quotes"] = unclosed_path

    # 4. Invalid UTF-8 encoding: raw binary bytes with illegal sequence
    enc_path = output_dir / "malformed_invalid_encoding.csv"
    clean_bytes = ("\n".join([header, *data_rows]) + "\n").encode("utf-8")
    # Insert invalid continuation byte 0xFF and 0xFE in the middle of the binary stream
    split_pos = len(header.encode("utf-8")) + 10
    corrupted_bytes = clean_bytes[:split_pos] + b"\xff\xfe\x80\xc0" + clean_bytes[split_pos:]
    enc_path.write_bytes(corrupted_bytes)
    results["invalid_encoding"] = enc_path

    return results


def is_malformed_test_file(path: Path) -> bool:
    """Return whether ``path`` identifies an isolated syntax-corrupted test artifact."""
    return path.name.startswith("malformed_")
