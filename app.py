"""Local web application for the Hotel & Vacation Rental Competitor Intelligence Tracker.

Run from this folder:
    python app.py --seed-demo

The application deliberately has no scraper.  It accepts records from an approved data
feed, an authorised export, or a manual authorised-review process, then preserves every
snapshot and calculates changes locally.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tracker.repository import (
    DashboardRepository,
    initialize_database,
    list_conditions,
    list_properties,
    list_recent_changes,
    list_collection_runs,
    list_observations,
    seed_demo_database,
)


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_DB = ROOT / "data" / "tracker.db"


class TrackerHandler(BaseHTTPRequestHandler):
    """Small dependency-free HTTP layer for the local dashboard and JSON API."""

    db_path: Path = DEFAULT_DB

    server_version = "CompetitorTracker/1.0"

    def log_message(self, fmt: str, *args: object) -> None:  # keep the console readable
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} — {fmt % args}")

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Resource not found"})
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path in {"/", "/index.html"}:
                self._file(STATIC / "index.html", "text/html; charset=utf-8")
                return
            if parsed.path == "/assets/dashboard.js":
                self._file(STATIC / "dashboard.js", "application/javascript; charset=utf-8")
                return
            if parsed.path == "/assets/styles.css":
                self._file(STATIC / "styles.css", "text/css; charset=utf-8")
                return
            if parsed.path.startswith("/docs/"):
                requested = (ROOT / parsed.path.lstrip("/")).resolve()
                docs_root = (ROOT / "docs").resolve()
                if docs_root in requested.parents and requested.suffix.lower() == ".md":
                    self._file(requested, "text/markdown; charset=utf-8")
                    return

            connection = self._connection()
            try:
                if parsed.path == "/api/health":
                    self._json(HTTPStatus.OK, {"status": "ok", "database": str(self.db_path.name), "at": datetime.now(timezone.utc).isoformat()})
                    return
                if parsed.path == "/api/conditions":
                    self._json(HTTPStatus.OK, {"conditions": list_conditions(connection)})
                    return
                if parsed.path == "/api/properties":
                    self._json(HTTPStatus.OK, {"properties": list_properties(connection)})
                    return
                if parsed.path == "/api/changes":
                    condition_id = query.get("condition_id", [None])[0]
                    self._json(HTTPStatus.OK, {"changes": list_recent_changes(connection, condition_id=condition_id, limit=40)})
                    return
                if parsed.path == "/api/dashboard":
                    condition_id = query.get("condition_id", [None])[0]
                    self._json(HTTPStatus.OK, DashboardRepository(connection).build(condition_id=condition_id))
                    return
                if parsed.path == "/api/runs":
                    self._json(HTTPStatus.OK, {"runs": list_collection_runs(connection, limit=30)})
                    return
                if parsed.path == "/api/observations":
                    condition_id = query.get("condition_id", [None])[0]
                    property_id = query.get("property_id", [None])[0]
                    limit = int(query.get("limit", ["250"])[0])
                    self._json(HTTPStatus.OK, {"observations": list_observations(
                        connection, condition_id=condition_id, property_id=property_id, limit=limit
                    )})
                    return
                if parsed.path == "/api/export/observations.csv":
                    condition_id = query.get("condition_id", [None])[0]
                    rows = list_observations(connection, condition_id=condition_id, limit=1000)
                    import csv
                    import io
                    output = io.StringIO()
                    fields = list(rows[0].keys()) if rows else [
                        "observation_id", "property_id", "property_name", "condition_id",
                        "check_in", "check_out", "guests", "rooms", "observed_at",
                        "room_type", "availability_status", "available_units",
                        "public_rate", "selling_rate", "taxes_fees", "discount_amount",
                        "currency", "meal_plan", "cancellation_terms", "rating",
                        "review_count", "source_type", "source_reference", "is_demo"
                    ]
                    writer = csv.DictWriter(output, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                    body = output.getvalue().encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="competitor_observations.csv"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            finally:
                connection.close()

            self._json(HTTPStatus.NOT_FOUND, {"error": "Unknown route"})
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # application errors should not expose a traceback in the browser
            print(f"Application error: {exc!r}")
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The local tracker could not complete this request."})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local competitor intelligence dashboard.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path (default: data/tracker.db)")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8765")), help="TCP port (default: 8765)")
    parser.add_argument("--seed-demo", action="store_true", help="Create/reset the clearly labelled synthetic demonstration dataset.")
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.seed_demo:
        seed_demo_database(args.db)
        print("Created fresh demo database. All pricing and availability values are synthetic.")
    elif not args.db.exists():
        # Cloud-friendly first boot: create a working demonstration database when
        # no persistent database has been mounted yet. Existing databases are never
        # overwritten on restart.
        seed_demo_database(args.db)
        print("Created initial demo database. All pricing and availability values are synthetic.")
    else:
        initialize_database(args.db)

    TrackerHandler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), TrackerHandler)
    print(f"\nCompetitor Intelligence Tracker is ready at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop the local server.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
