"""Standard-library regression tests for persistence and business logic."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from tracker.repository import (  # noqa: E402
    DashboardRepository,
    add_property,
    database_session,
    ingest_observation,
    initialize_database,
    seed_demo_database,
)


class TrackerCoreTests(unittest.TestCase):
    def test_observations_are_idempotent_and_change_detection_is_auditable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            initialize_database(db_path)
            with database_session(db_path) as connection:
                add_property(connection, {"property_id": "P001", "name": "Primary", "role": "primary", "market": "Lonavala", "property_type": "Resort"})
                add_property(connection, {"property_id": "C001", "name": "Comparable", "role": "competitor", "market": "Karjat", "property_type": "Resort"})
                base = {
                    "property_id": "P001", "check_in": "2026-11-10", "check_out": "2026-11-12", "guests": 2, "rooms": 1,
                    "room_type": "Lead room", "availability_status": "available", "available_units": 8,
                    "selling_rate": 10000, "public_rate": 11200, "discount_amount": 1200, "currency": "INR",
                    "source_type": "internal", "source_reference": "RUN-A", "observed_at": "2026-10-01T09:00:00+05:30",
                }
                self.assertTrue(ingest_observation(connection, base))
                self.assertFalse(ingest_observation(connection, base), "The same source observation must be skipped.")
                later = {**base, "available_units": 5, "selling_rate": 10800, "source_reference": "RUN-B", "observed_at": "2026-10-02T09:00:00+05:30"}
                self.assertTrue(ingest_observation(connection, later))
                event_types = {row[0] for row in connection.execute("SELECT event_type FROM change_events")}
                self.assertIn("availability_decreased", event_types)
                self.assertIn("price_increased", event_types)
                event = connection.execute("SELECT estimated_units_sold, estimated_revenue FROM change_events WHERE event_type = 'availability_decreased'").fetchone()
                self.assertEqual(event[0], 3)
                self.assertEqual(event[1], 32400)

    def test_seed_covers_assignment_minimums_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "seed.db"
            seed_demo_database(db_path)
            with database_session(db_path) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM properties WHERE role = 'primary'").fetchone()[0], 1)
                self.assertGreaterEqual(connection.execute("SELECT COUNT(*) FROM properties WHERE role = 'competitor'").fetchone()[0], 30)
                self.assertGreaterEqual(connection.execute("SELECT COUNT(*) FROM booking_conditions").fetchone()[0], 7)
                self.assertGreater(connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0], 0)
                dashboard = DashboardRepository(connection).build()
                self.assertEqual(dashboard["metrics"]["competitors_covered"], 30)
                self.assertEqual(len(dashboard["competitors"]), 30)
                self.assertTrue(dashboard["metrics"]["is_demo_dataset"])


if __name__ == "__main__":
    unittest.main()
