"""Import observations from an authorised CSV export without overwriting history.

Example:
    python scripts/import_snapshots.py --file data/snapshot_import_template.csv \
      --source-type manual_authorized --authorization-reference "MMT-PERM-2026-001"
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tracker.repository import (  # noqa: E402
    connect,
    finish_run,
    ingest_observation,
    initialize_database,
    record_error,
    start_run,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import approved hotel or villa observations into SQLite.")
    parser.add_argument("--file", type=Path, required=True, help="CSV file using the documented import columns.")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "tracker.db", help="SQLite database path.")
    parser.add_argument("--source-type", choices=["authorized_feed", "partner_export", "manual_authorized", "internal"], required=True)
    parser.add_argument("--authorization-reference", required=True, help="Written permission, partner contract, or governed export reference.")
    parser.add_argument("--note", default="", help="Optional collection-run note.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first invalid row (default logs invalid rows and continues).")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"Input file not found: {args.file}")
    initialize_database(args.db)
    connection = connect(args.db)
    try:
      with args.file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit("The file has no header row.")
        required = {"property_id", "check_in", "check_out", "guests", "rooms", "observed_at", "availability_status", "source_reference"}
        missing = sorted(required - set(reader.fieldnames))
        if missing:
            raise SystemExit("Missing required CSV columns: " + ", ".join(missing))
        run_id = start_run(connection, args.source_type, args.authorization_reference, args.note)
        attempted = succeeded = failed = duplicates = 0
        for row_number, row in enumerate(reader, start=2):
            if not any(str(value).strip() for value in row.values()):
                continue
            attempted += 1
            row["source_type"] = args.source_type
            row["is_demo"] = False
            try:
                inserted = ingest_observation(connection, row, collection_run_id=run_id)
                if inserted:
                    succeeded += 1
                else:
                    duplicates += 1
            except (KeyError, ValueError) as exc:
                failed += 1
                record_error(connection, run_id, row_number, row.get("property_id"), str(exc), row)
                if args.fail_fast:
                    finish_run(connection, run_id, attempted, succeeded, failed)
                    raise SystemExit(f"Stopped at row {row_number}: {exc}")
        finish_run(connection, run_id, attempted, succeeded, failed)
        connection.commit()
    finally:
        connection.close()
    print(f"Run {run_id}: {succeeded} inserted, {duplicates} duplicates skipped, {failed} invalid rows logged.")


if __name__ == "__main__":
    main()
