"""Read-only readiness checks for the assignment demonstration."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tracker.repository import connect, list_conditions  # noqa: E402


def scalar(connection: sqlite3.Connection, statement: str) -> int:
    return int(connection.execute(statement).fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Check minimum data coverage and integrity.")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "tracker.db")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit("Database not found. Run `python app.py --seed-demo` or import approved observations first.")
    connection = connect(args.db)
    try:
        primary = scalar(connection, "SELECT COUNT(*) FROM properties WHERE role = 'primary' AND is_active = 1")
        competitors = scalar(connection, "SELECT COUNT(*) FROM properties WHERE role = 'competitor' AND is_active = 1")
        observations = scalar(connection, "SELECT COUNT(*) FROM observations")
        changes = scalar(connection, "SELECT COUNT(*) FROM change_events")
        errors = scalar(connection, "SELECT COUNT(*) FROM ingestion_errors")
        duplicate_keys = scalar(connection, """SELECT COUNT(*) FROM (
            SELECT property_id, condition_id, observed_at, room_type, source_reference, COUNT(*) c
            FROM observations GROUP BY property_id, condition_id, observed_at, room_type, source_reference HAVING c > 1
        )""")
        conditions = list_conditions(connection)
    finally:
        connection.close()
    checks = [
        ("One active primary property", primary == 1, str(primary)),
        ("At least 30 active competitors", competitors >= 30, str(competitors)),
        ("At least two booking conditions", len(conditions) >= 2, str(len(conditions))),
        ("Historical observations preserved", observations > 0, str(observations)),
        ("Change detection produced events", changes > 0, str(changes)),
        ("No duplicate observation keys", duplicate_keys == 0, str(duplicate_keys)),
    ]
    print("\nREADINESS CHECK")
    print("-" * 62)
    for label, passed, value in checks:
        print(f"{'PASS' if passed else 'CHECK':<7} {label:<42} {value:>8}")
    print(f"Logged ingestion errors: {errors}")
    failed = [label for label, passed, _ in checks if not passed]
    if failed:
        raise SystemExit("\nResolve before submission: " + "; ".join(failed))
    print("\nReady for the functional demonstration. Verify listing identities and data-source authorisation before a live demonstration.")


if __name__ == "__main__":
    main()
