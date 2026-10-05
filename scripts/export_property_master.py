"""Export the configured candidate property master to CSV for review and sign-off."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tracker.repository import connect, list_properties  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "tracker.db")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "property_master_lonavala_karjat.csv")
    args = parser.parse_args()
    connection = connect(args.db)
    try:
        rows = list_properties(connection)
    finally:
        connection.close()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    columns = ["property_id", "name", "role", "market", "property_type", "segment", "total_units", "inventory_basis", "listing_url", "listing_status", "source_note", "is_active"]
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows([{column: row.get(column) for column in columns} for row in rows])
    print(f"Exported {len(rows)} properties to {args.out}")


if __name__ == "__main__":
    main()
