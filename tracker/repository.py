"""Persistence, ingestion, change detection, seeded demo data, and dashboard queries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .schema import SCHEMA


DEMO_START = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)
DEMO_OBSERVED_AT = (
    "2026-10-02T09:00:00+00:00",
    "2026-10-03T09:00:00+00:00",
    "2026-10-04T09:00:00+00:00",
)
MMT_LONAVALA_MARKET_URL = "https://www.makemytrip.com/hotels/lonavala-hotels.html"
MMT_KARJAT_MARKET_URL = "https://www.makemytrip.com/hotels/p-resorts-in-karjat.html"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_number(text: str, low: int, high: int) -> int:
    """Deterministic helper for synthetic fixtures; never used in live ingestion."""
    digest = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)
    return low + digest % (high - low + 1)


def as_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def connect(db_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_session(db_path: Path | str):
    """Commit or roll back, then close the SQLite file deterministically (important on Windows)."""
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with database_session(path) as connection:
        connection.executescript(SCHEMA)


def create_condition(
    connection: sqlite3.Connection,
    *,
    check_in: str,
    check_out: str,
    guests: int,
    rooms: int,
    meal_preference: str = "Any",
    cancellation_preference: str = "Any",
) -> str:
    try:
        in_date = datetime.fromisoformat(check_in).date()
        out_date = datetime.fromisoformat(check_out).date()
    except ValueError as exc:
        raise ValueError("check_in and check_out must use YYYY-MM-DD.") from exc
    if out_date <= in_date:
        raise ValueError("check_out must be after check_in.")
    if guests < 1 or rooms < 1:
        raise ValueError("guests and rooms must both be at least 1.")

    condition_key = "|".join((check_in, check_out, str(guests), str(rooms), meal_preference, cancellation_preference))
    condition_id = "COND-" + hashlib.sha256(condition_key.encode("utf-8")).hexdigest()[:12].upper()
    connection.execute(
        """
        INSERT OR IGNORE INTO booking_conditions
            (condition_id, check_in, check_out, guests, rooms, meal_preference, cancellation_preference, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (condition_id, check_in, check_out, guests, rooms, meal_preference, cancellation_preference, now_iso()),
    )
    return condition_id


def add_property(connection: sqlite3.Connection, record: dict[str, Any]) -> None:
    if record.get("role") not in {"primary", "competitor"}:
        raise ValueError("Property role must be primary or competitor.")
    connection.execute(
        """
        INSERT OR IGNORE INTO properties
        (property_id, name, role, market, property_type, segment, total_units, inventory_basis,
         listing_url, listing_status, source_note, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["property_id"], record["name"], record["role"], record["market"],
            record.get("property_type", "Resort"), record.get("segment"), record.get("total_units"),
            record.get("inventory_basis", "not_recorded"), record.get("listing_url"),
            record.get("listing_status", "candidate_verification"), record.get("source_note"),
            int(record.get("is_active", True)), now_iso(),
        ),
    )


def start_run(connection: sqlite3.Connection, source_type: str, authorization_reference: str | None = None, notes: str | None = None) -> str:
    run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
    connection.execute(
        """INSERT INTO collection_runs
           (run_id, source_type, started_at, status, authorization_reference, notes)
           VALUES (?, ?, ?, 'running', ?, ?)""",
        (run_id, source_type, now_iso(), authorization_reference, notes),
    )
    return run_id


def finish_run(connection: sqlite3.Connection, run_id: str, attempted: int, succeeded: int, failed: int) -> None:
    status = "completed" if failed == 0 else "completed_with_errors"
    connection.execute(
        """UPDATE collection_runs
           SET completed_at = ?, status = ?, attempted_count = ?, succeeded_count = ?, failed_count = ?
           WHERE run_id = ?""",
        (now_iso(), status, attempted, succeeded, failed, run_id),
    )


def record_error(connection: sqlite3.Connection, run_id: str | None, row_number: int | None, property_id: str | None, error: str, raw_row: dict[str, Any] | None, retryable: bool = False) -> None:
    connection.execute(
        """INSERT INTO ingestion_errors
        (error_id, run_id, source_row, property_id, error_message, raw_row, retryable, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ERR-" + uuid.uuid4().hex[:12].upper(), run_id, row_number, property_id, error,
         json.dumps(raw_row, ensure_ascii=False) if raw_row else None, int(retryable), now_iso()),
    )


def _coerce_float(value: Any, field: str, *, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{field} is required.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if number < 0:
        raise ValueError(f"{field} cannot be negative.")
    return number


def _coerce_int(value: Any, field: str, *, required: bool = False) -> int | None:
    number = _coerce_float(value, field, required=required)
    if number is None:
        return None
    if not number.is_integer():
        raise ValueError(f"{field} must be a whole number.")
    return int(number)


def _require_iso_timestamp(value: Any) -> str:
    if not value:
        raise ValueError("observed_at is required.")
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be ISO 8601, e.g. 2026-10-04T09:00:00+05:30.") from exc
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.replace(microsecond=0).isoformat()


def _previous_observation(connection: sqlite3.Connection, record: dict[str, Any], observed_at: str) -> sqlite3.Row | None:
    return connection.execute(
        """SELECT * FROM observations
           WHERE property_id = ? AND condition_id = ? AND room_type = ? AND observed_at < ?
           ORDER BY observed_at DESC LIMIT 1""",
        (record["property_id"], record["condition_id"], record.get("room_type", "Best available room"), observed_at),
    ).fetchone()


def _insert_change(
    connection: sqlite3.Connection,
    *,
    property_id: str,
    condition_id: str,
    observation_id: str,
    previous_observation_id: str,
    observed_at: str,
    event_type: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    absolute_change: float | None = None,
    estimated_units_sold: int = 0,
    estimated_revenue: float = 0,
    methodology_note: str,
) -> None:
    connection.execute(
        """INSERT INTO change_events
        (event_id, property_id, condition_id, observation_id, previous_observation_id, observed_at,
         event_type, field_name, old_value, new_value, absolute_change, estimated_units_sold,
         estimated_revenue, is_estimate, methodology_note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            "EVT-" + uuid.uuid4().hex[:14].upper(), property_id, condition_id, observation_id,
            previous_observation_id, observed_at, event_type, field_name, str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None, absolute_change, estimated_units_sold,
            round(estimated_revenue, 2), methodology_note, now_iso(),
        ),
    )


def detect_changes(connection: sqlite3.Connection, current: sqlite3.Row, previous: sqlite3.Row | None) -> None:
    """Create auditable events. A visible inventory reduction is explicitly an estimate, not a booking."""
    if previous is None:
        return
    condition = connection.execute(
        "SELECT check_in, check_out FROM booking_conditions WHERE condition_id = ?", (current["condition_id"],)
    ).fetchone()
    stay_nights = max(1, (datetime.fromisoformat(condition["check_out"]).date() - datetime.fromisoformat(condition["check_in"]).date()).days)
    base = dict(
        property_id=current["property_id"], condition_id=current["condition_id"], observation_id=current["observation_id"],
        previous_observation_id=previous["observation_id"], observed_at=current["observed_at"],
    )

    old_units, new_units = previous["available_units"], current["available_units"]
    if old_units is not None and new_units is not None and new_units < old_units:
        unit_drop = int(old_units - new_units)
        rate = current["selling_rate"] if current["selling_rate"] is not None else previous["selling_rate"] or 0
        _insert_change(
            connection, **base, event_type="availability_decreased", field_name="available_units",
            old_value=old_units, new_value=new_units, absolute_change=-unit_drop,
            estimated_units_sold=unit_drop, estimated_revenue=unit_drop * float(rate),
            methodology_note=(f"Observed visible units decreased by {unit_drop}; treated as an estimated demand/sales signal. "
                              f"Estimated gross booking value = visible-unit drop × observed selling rate for {stay_nights} night(s). "
                              "This is not confirmed private booking or revenue data."),
        )
    elif old_units is not None and new_units is not None and new_units > old_units:
        _insert_change(
            connection, **base, event_type="availability_increased", field_name="available_units",
            old_value=old_units, new_value=new_units, absolute_change=float(new_units - old_units),
            methodology_note="Visible inventory increased. This can reflect release, cancellation, allocation change, or a measurement difference; it is not treated as negative sales.",
        )

    if previous["availability_status"] != current["availability_status"]:
        if current["availability_status"] == "sold_out":
            kind, note = "became_sold_out", "Property/room became sold out under the same recorded booking condition. This is a demand-pressure signal, not proof of all units being sold."
        elif previous["availability_status"] == "sold_out":
            kind, note = "became_available", "Property/room changed from sold out to available; this can reflect cancellation, release, inventory allocation, or a collection difference."
        else:
            kind, note = "room_type_changed", "Availability status changed under the same booking condition; interpret with the source reference and record quality."
        _insert_change(connection, **base, event_type=kind, field_name="availability_status", old_value=previous["availability_status"], new_value=current["availability_status"], methodology_note=note)

    old_price, new_price = previous["selling_rate"], current["selling_rate"]
    if old_price is not None and new_price is not None and float(new_price) != float(old_price):
        delta = float(new_price) - float(old_price)
        _insert_change(
            connection, **base, event_type="price_increased" if delta > 0 else "price_decreased", field_name="selling_rate",
            old_value=old_price, new_value=new_price, absolute_change=delta,
            methodology_note="Observed selling-rate change for the same property, room type, and booking condition. Prices are observational, not an assertion of transacted rate.",
        )

    old_discount, new_discount = previous["discount_amount"], current["discount_amount"]
    if old_discount is not None and new_discount is not None and float(old_discount) != float(new_discount):
        _insert_change(connection, **base, event_type="discount_changed", field_name="discount_amount", old_value=old_discount, new_value=new_discount, absolute_change=float(new_discount) - float(old_discount), methodology_note="Observed displayed discount changed under the same booking condition.")
    if previous["meal_plan"] != current["meal_plan"]:
        _insert_change(connection, **base, event_type="meal_plan_changed", field_name="meal_plan", old_value=previous["meal_plan"], new_value=current["meal_plan"], methodology_note="Observed meal-plan option changed; compare only equivalent room and guest combinations.")
    if previous["cancellation_terms"] != current["cancellation_terms"]:
        _insert_change(connection, **base, event_type="cancellation_changed", field_name="cancellation_terms", old_value=previous["cancellation_terms"], new_value=current["cancellation_terms"], methodology_note="Observed cancellation terms changed; check source evidence before treating this as a commercial policy change.")
    if previous["rating"] is not None and current["rating"] is not None and float(previous["rating"]) != float(current["rating"]):
        _insert_change(connection, **base, event_type="rating_changed", field_name="rating", old_value=previous["rating"], new_value=current["rating"], absolute_change=float(current["rating"]) - float(previous["rating"]), methodology_note="Public rating changed between snapshots.")
    if previous["review_count"] is not None and current["review_count"] is not None and int(previous["review_count"]) != int(current["review_count"]):
        _insert_change(connection, **base, event_type="review_count_changed", field_name="review_count", old_value=previous["review_count"], new_value=current["review_count"], absolute_change=float(current["review_count"] - previous["review_count"]), methodology_note="Public review count changed between snapshots.")


def ingest_observation(connection: sqlite3.Connection, record: dict[str, Any], collection_run_id: str | None = None) -> bool:
    """Validate, deduplicate, persist an immutable raw observation, and derive change events."""
    property_row = connection.execute("SELECT property_id FROM properties WHERE property_id = ?", (record.get("property_id"),)).fetchone()
    if property_row is None:
        raise ValueError(f"Unknown property_id: {record.get('property_id')!r}.")

    if record.get("availability_status") not in {"available", "limited", "sold_out", "unavailable", "on_request"}:
        raise ValueError("availability_status must be available, limited, sold_out, unavailable, or on_request.")
    if record.get("source_type") not in {"authorized_feed", "partner_export", "manual_authorized", "internal", "demo_synthetic"}:
        raise ValueError("source_type must be authorized_feed, partner_export, manual_authorized, internal, or demo_synthetic.")
    if not record.get("source_reference"):
        raise ValueError("source_reference is required for auditability and duplicate prevention.")

    condition_id = record.get("condition_id") or create_condition(
        connection,
        check_in=str(record["check_in"]), check_out=str(record["check_out"]), guests=_coerce_int(record["guests"], "guests", required=True) or 1,
        rooms=_coerce_int(record["rooms"], "rooms", required=True) or 1,
        meal_preference=record.get("meal_preference", "Any"), cancellation_preference=record.get("cancellation_preference", "Any"),
    )
    record = dict(record)
    record["condition_id"] = condition_id
    observed_at = _require_iso_timestamp(record.get("observed_at"))
    available_units = _coerce_int(record.get("available_units"), "available_units")
    public_rate = _coerce_float(record.get("public_rate"), "public_rate")
    selling_rate = _coerce_float(record.get("selling_rate"), "selling_rate")
    taxes_fees = _coerce_float(record.get("taxes_fees"), "taxes_fees")
    discount_amount = _coerce_float(record.get("discount_amount"), "discount_amount")
    rating = _coerce_float(record.get("rating"), "rating")
    if rating is not None and rating > 5:
        raise ValueError("rating cannot be greater than 5.")
    review_count = _coerce_int(record.get("review_count"), "review_count")
    room_type = record.get("room_type") or "Best available room"
    observation_id = "OBS-" + uuid.uuid4().hex[:16].upper()
    created_at = now_iso()
    previous = _previous_observation(connection, record, observed_at)
    cursor = connection.execute(
        """INSERT OR IGNORE INTO observations
        (observation_id, property_id, condition_id, observed_at, room_type, availability_status, available_units,
         public_rate, selling_rate, taxes_fees, discount_amount, currency, meal_plan, cancellation_terms,
         amenities_json, rating, review_count, source_type, source_reference, raw_payload, is_demo,
         collection_run_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            observation_id, record["property_id"], condition_id, observed_at, room_type, record["availability_status"], available_units,
            public_rate, selling_rate, taxes_fees, discount_amount, record.get("currency", "INR"), record.get("meal_plan"),
            record.get("cancellation_terms"), json.dumps(record.get("amenities", []), ensure_ascii=False), rating, review_count,
            record["source_type"], record["source_reference"], json.dumps(record.get("raw_payload", record), ensure_ascii=False),
            int(bool(record.get("is_demo", record["source_type"] == "demo_synthetic"))), collection_run_id, created_at,
        ),
    )
    if cursor.rowcount == 0:
        return False
    current = connection.execute("SELECT * FROM observations WHERE observation_id = ?", (observation_id,)).fetchone()
    detect_changes(connection, current, previous)
    return True


def list_conditions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT c.condition_id, c.check_in, c.check_out, c.guests, c.rooms, c.meal_preference,
                  c.cancellation_preference,
                  CAST(julianday(c.check_out) - julianday(c.check_in) AS INTEGER) AS stay_nights,
                  COUNT(o.observation_id) AS observation_count, MAX(o.observed_at) AS latest_observed_at
           FROM booking_conditions c LEFT JOIN observations o ON o.condition_id = c.condition_id
           GROUP BY c.condition_id
           ORDER BY c.check_in, c.check_out, c.guests, c.rooms"""
    ).fetchall()
    return as_dicts(rows)


def list_properties(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT p.*, COUNT(o.observation_id) AS observation_count, MAX(o.observed_at) AS latest_observed_at
           FROM properties p LEFT JOIN observations o ON o.property_id = p.property_id
           GROUP BY p.property_id
           ORDER BY CASE p.role WHEN 'primary' THEN 0 ELSE 1 END, p.market, p.name"""
    ).fetchall()
    return as_dicts(rows)



def list_collection_runs(connection: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    return as_dicts(connection.execute(
        """SELECT run_id, source_type, started_at, completed_at, status,
                  attempted_count, succeeded_count, failed_count,
                  authorization_reference, notes
           FROM collection_runs ORDER BY started_at DESC LIMIT ?""",
        (limit,),
    ).fetchall())


def list_observations(
    connection: sqlite3.Connection,
    *,
    condition_id: str | None = None,
    property_id: str | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if condition_id:
        clauses.append("o.condition_id = ?")
        params.append(condition_id)
    if property_id:
        clauses.append("o.property_id = ?")
        params.append(property_id)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit), 1000)))
    return as_dicts(connection.execute(
        f"""SELECT o.observation_id, o.property_id, p.name AS property_name,
                   o.condition_id, c.check_in, c.check_out, c.guests, c.rooms,
                   o.observed_at, o.room_type, o.availability_status,
                   o.available_units, o.public_rate, o.selling_rate,
                   o.taxes_fees, o.discount_amount, o.currency, o.meal_plan,
                   o.cancellation_terms, o.rating, o.review_count,
                   o.source_type, o.source_reference, o.is_demo
            FROM observations o
            JOIN properties p ON p.property_id = o.property_id
            JOIN booking_conditions c ON c.condition_id = o.condition_id
            {where}
            ORDER BY o.observed_at DESC, p.name
            LIMIT ?""",
        params,
    ).fetchall())


def list_recent_changes(connection: sqlite3.Connection, condition_id: str | None = None, limit: int = 40) -> list[dict[str, Any]]:
    sql = """SELECT e.*, p.name AS property_name, c.check_in, c.check_out, c.guests, c.rooms
             FROM change_events e JOIN properties p ON p.property_id = e.property_id
             JOIN booking_conditions c ON c.condition_id = e.condition_id"""
    params: list[Any] = []
    if condition_id:
        sql += " WHERE e.condition_id = ?"
        params.append(condition_id)
    sql += " ORDER BY e.observed_at DESC, e.created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 100)))
    return as_dicts(connection.execute(sql, params).fetchall())


class DashboardRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def _resolve_condition(self, condition_id: str | None) -> sqlite3.Row | None:
        if condition_id:
            item = self.connection.execute("SELECT * FROM booking_conditions WHERE condition_id = ?", (condition_id,)).fetchone()
            if item is None:
                raise ValueError("The selected booking condition was not found.")
            return item
        return self.connection.execute("SELECT * FROM booking_conditions ORDER BY check_in, guests, rooms LIMIT 1").fetchone()

    def build(self, condition_id: str | None = None) -> dict[str, Any]:
        condition = self._resolve_condition(condition_id)
        if condition is None:
            return {"condition": None, "metrics": {}, "competitors": [], "trend": [], "notice": "No observations have been loaded yet."}
        condition_id = condition["condition_id"]
        latest_rows = self.connection.execute(
            """WITH ranked AS (
                   SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.property_id ORDER BY o.observed_at DESC) AS rank_no
                   FROM observations o WHERE o.condition_id = ?
               )
               SELECT r.*, p.name, p.role, p.market, p.segment, p.total_units, p.inventory_basis
               FROM ranked r JOIN properties p ON p.property_id = r.property_id
               WHERE rank_no = 1
               ORDER BY CASE p.role WHEN 'primary' THEN 0 ELSE 1 END, p.name""",
            (condition_id,),
        ).fetchall()
        prior_rows = self.connection.execute(
            """WITH ranked AS (
                   SELECT o.*, ROW_NUMBER() OVER (PARTITION BY o.property_id ORDER BY o.observed_at DESC) AS rank_no
                   FROM observations o WHERE o.condition_id = ?
               ) SELECT * FROM ranked WHERE rank_no = 2""",
            (condition_id,),
        ).fetchall()
        previous = {row["property_id"]: row for row in prior_rows}
        event_rows = self.connection.execute(
            """SELECT property_id, SUM(estimated_units_sold) AS estimated_units_sold,
                      SUM(estimated_revenue) AS estimated_revenue,
                      COUNT(*) AS event_count
               FROM change_events WHERE condition_id = ? GROUP BY property_id""",
            (condition_id,),
        ).fetchall()
        event_by_property = {row["property_id"]: row for row in event_rows}
        stay_nights = max(1, (datetime.fromisoformat(condition["check_out"]).date() - datetime.fromisoformat(condition["check_in"]).date()).days)

        competitors: list[dict[str, Any]] = []
        primary: dict[str, Any] | None = None
        observed_rates: list[float] = []
        units_sold_total = 0
        estimated_revenue_total = 0.0
        availability_ratio: list[float] = []
        for row in latest_rows:
            current = dict(row)
            prior = previous.get(row["property_id"])
            event = event_by_property.get(row["property_id"])
            current_rate = current.get("selling_rate")
            prior_rate = prior["selling_rate"] if prior else None
            rate_change = (float(current_rate) - float(prior_rate)) if current_rate is not None and prior_rate is not None else None
            rate_change_pct = rate_change / float(prior_rate) if rate_change is not None and float(prior_rate) else None
            unit_delta = None
            if prior and current.get("available_units") is not None and prior["available_units"] is not None:
                unit_delta = int(current["available_units"] - prior["available_units"])
            estimate = dict(event) if event else {"estimated_units_sold": 0, "estimated_revenue": 0, "event_count": 0}
            units_sold = int(estimate["estimated_units_sold"] or 0)
            estimated_revenue = float(estimate["estimated_revenue"] or 0)
            units_sold_total += units_sold
            estimated_revenue_total += estimated_revenue
            if current_rate is not None and row["role"] == "competitor":
                observed_rates.append(float(current_rate))
            if current.get("available_units") is not None and current.get("total_units"):
                availability_ratio.append(max(0, min(1, 1 - (float(current["available_units"]) / float(current["total_units"])))))
            if current["availability_status"] == "sold_out":
                action = "Sold out — monitor release / substitution"
                priority = 3
            elif unit_delta is not None and unit_delta <= -2:
                action = "Material visible-inventory reduction"
                priority = 3
            elif rate_change_pct is not None and rate_change_pct <= -0.10:
                action = "Rate decreased by 10%+"
                priority = 2
            elif rate_change_pct is not None and rate_change_pct >= 0.10:
                action = "Rate increased by 10%+"
                priority = 2
            elif current["availability_status"] == "limited":
                action = "Limited availability"
                priority = 2
            else:
                action = "Stable / monitor"
                priority = 1
            item = {
                "property_id": current["property_id"], "name": current["name"], "role": current["role"], "market": current["market"],
                "segment": current["segment"], "current_rate": current_rate, "prior_rate": prior_rate, "rate_change": rate_change,
                "rate_change_pct": rate_change_pct, "availability_status": current["availability_status"], "available_units": current["available_units"],
                "availability_delta": unit_delta, "rating": current["rating"], "review_count": current["review_count"],
                "estimated_units_sold": units_sold, "estimated_room_nights": units_sold * stay_nights,
                "estimated_revenue": estimated_revenue, "action": action, "priority": priority,
                "observed_at": current["observed_at"], "is_demo": bool(current["is_demo"]),
            }
            if current["role"] == "primary":
                primary = item
            else:
                competitors.append(item)

        prices = [x["current_rate"] for x in competitors if x["current_rate"] is not None]
        sold_out_count = sum(x["availability_status"] == "sold_out" for x in competitors)
        available_count = sum(x["availability_status"] in {"available", "limited"} for x in competitors)
        primary_rate = primary["current_rate"] if primary else None
        market_average = mean(prices) if prices else None
        latest_stamp = max((x["observed_at"] for x in latest_rows), default=None)
        all_demo = bool(latest_rows) and all(bool(row["is_demo"]) for row in latest_rows)
        competitors.sort(key=lambda x: (-x["priority"], x["current_rate"] is None, x["current_rate"] or 0))

        trend = as_dicts(self.connection.execute(
            """SELECT o.observed_at,
                      MAX(CASE WHEN p.role = 'primary' THEN o.selling_rate END) AS primary_rate,
                      AVG(CASE WHEN p.role = 'competitor' THEN o.selling_rate END) AS competitor_average,
                      SUM(CASE WHEN p.role = 'competitor' AND o.availability_status = 'sold_out' THEN 1 ELSE 0 END) AS competitor_sold_out,
                      SUM(CASE WHEN p.role = 'competitor' AND o.availability_status IN ('available', 'limited') THEN 1 ELSE 0 END) AS competitor_available
               FROM observations o JOIN properties p ON p.property_id = o.property_id
               WHERE o.condition_id = ? GROUP BY o.observed_at ORDER BY o.observed_at""",
            (condition_id,),
        ).fetchall())
        top_changes = list_recent_changes(self.connection, condition_id=condition_id, limit=12)
        guest_mix = as_dicts(self.connection.execute(
            """SELECT c.guests, AVG(o.selling_rate) AS average_rate, COUNT(DISTINCT o.property_id) AS properties_covered,
                      SUM(CASE WHEN o.availability_status = 'sold_out' THEN 1 ELSE 0 END) AS sold_out_observations
               FROM observations o JOIN booking_conditions c ON c.condition_id = o.condition_id
               WHERE o.is_demo IN (0, 1) GROUP BY c.guests ORDER BY c.guests"""
        ).fetchall())
        weekday_vs_weekend = as_dicts(self.connection.execute(
            """SELECT CASE WHEN CAST(strftime('%w', c.check_in) AS INTEGER) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS period,
                      AVG(o.selling_rate) AS average_rate,
                      COUNT(DISTINCT o.property_id) AS properties_covered
               FROM observations o JOIN booking_conditions c ON c.condition_id = o.condition_id
               GROUP BY period ORDER BY period"""
        ).fetchall())
        room_types = as_dicts(self.connection.execute(
            """SELECT room_type, COUNT(*) AS observations, AVG(selling_rate) AS average_rate
               FROM observations WHERE condition_id = ? GROUP BY room_type ORDER BY observations DESC""",
            (condition_id,),
        ).fetchall())

        history_stats = self.connection.execute(
            """SELECT COUNT(*) AS observations,
                      COUNT(DISTINCT observed_at) AS observation_checkpoints,
                      MIN(observed_at) AS history_start,
                      MAX(observed_at) AS history_end,
                      COUNT(DISTINCT collection_run_id) AS collection_runs
               FROM observations"""
        ).fetchone()
        run_stats = self.connection.execute(
            """SELECT run_id, source_type, started_at, completed_at, status,
                      attempted_count, succeeded_count, failed_count
               FROM collection_runs ORDER BY started_at DESC LIMIT 1"""
        ).fetchone()
        metrics = {
            "properties_covered": len(latest_rows), "competitors_covered": len(competitors), "latest_observed_at": latest_stamp,
            "total_observations": int(history_stats["observations"] or 0),
            "observation_checkpoints": int(history_stats["observation_checkpoints"] or 0),
            "history_start": history_stats["history_start"],
            "history_end": history_stats["history_end"],
            "collection_runs": int(history_stats["collection_runs"] or 0),
            "latest_run": dict(run_stats) if run_stats else None,
            "primary_rate": primary_rate, "competitor_average_rate": market_average,
            "primary_rate_position_pct": ((float(primary_rate) / market_average) - 1) if primary_rate is not None and market_average else None,
            "available_competitors": available_count, "sold_out_competitors": sold_out_count,
            "estimated_units_sold": units_sold_total, "estimated_room_nights": units_sold_total * stay_nights,
            "estimated_gross_booking_value": estimated_revenue_total,
            "visible_inventory_pressure_pct": mean(availability_ratio) if availability_ratio else None,
            "occupancy_note": "Visible-inventory proxy only; total-unit assumptions must be replaced with verified inventory before interpreting as occupancy.",
            "is_demo_dataset": all_demo,
        }
        condition_payload = dict(condition)
        condition_payload["stay_nights"] = stay_nights
        return {
            "condition": condition_payload, "metrics": metrics, "primary": primary, "competitors": competitors,
            "trend": trend, "top_changes": top_changes, "guest_mix": guest_mix,
            "weekday_vs_weekend": weekday_vs_weekend, "room_types": room_types,
            "methodology": {
                "estimated_sales": "A drop in publicly observable units is recorded as an estimated demand/sales signal. It is never a confirmed booking ledger entry.",
                "estimated_revenue": "Estimated gross booking value = observed visible-unit reduction × observed selling rate for the same booking condition. Taxes, refunds, cancellations, allocations, and actual transacted price may differ.",
                "scope": "All comparative measures preserve the selected check-in/check-out dates, guest count, room quantity, meal preference, and cancellation preference.",
            },
        }


DEMO_PROPERTIES = [
    ("P001", "Della Resorts", "primary", "Lonavala", "Luxury resort", "Luxury experiential", MMT_LONAVALA_MARKET_URL),
    ("C001", "Fariyas Resort", "competitor", "Lonavala", "Resort", "Upper-upscale family", MMT_LONAVALA_MARKET_URL),
    ("C002", "The Machan", "competitor", "Lonavala", "Eco-resort", "Luxury experiential", MMT_LONAVALA_MARKET_URL),
    ("C003", "Radisson Resort & Spa Lonavala", "competitor", "Lonavala", "Resort", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C004", "Rhythm Lonavala - An All Suite Resort", "competitor", "Lonavala", "Resort", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C005", "Della DATA Resort", "competitor", "Lonavala", "Glamping resort", "Luxury experiential", MMT_LONAVALA_MARKET_URL),
    ("C006", "Hilton Shillim Estate Retreat & Spa", "competitor", "Lonavala", "Wellness resort", "Luxury wellness", MMT_LONAVALA_MARKET_URL),
    ("C007", "The Dukes Retreat", "competitor", "Khandala", "Resort", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C008", "Aamby Valley City", "competitor", "Lonavala", "Resort", "Luxury leisure", MMT_LONAVALA_MARKET_URL),
    ("C009", "The Lagoona Resort (An Eco Friendly Hotel)", "competitor", "Lonavala", "Resort", "Upper-upscale family", MMT_LONAVALA_MARKET_URL),
    ("C010", "7 Apple Resort, Lonavala", "competitor", "Lonavala", "Resort", "Mid-upscale", MMT_LONAVALA_MARKET_URL),
    ("C011", "Picaddle, The Luxury Boutique Resort Lonavala", "competitor", "Lonavala", "Boutique resort", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C012", "The Fern An Ecotel Hotel, Lonavala", "competitor", "Lonavala", "Hotel", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C013", "Fazlani Nature's Nest - A Wellness Retreat", "competitor", "Lonavala", "Wellness resort", "Luxury wellness", MMT_LONAVALA_MARKET_URL),
    ("C014", "Novotel Imagica Khopoli", "competitor", "Khopoli", "Hotel", "Upper-upscale family", MMT_LONAVALA_MARKET_URL),
    ("C015", "Enrise by Sayaji Lonavala", "competitor", "Lonavala", "Hotel", "Upper-upscale", MMT_LONAVALA_MARKET_URL),
    ("C016", "SaffronStays Artica", "competitor", "Lonavala", "Villa", "Premium villa", MMT_LONAVALA_MARKET_URL),
    ("C017", "SaffronStays Hillside Harriers (Couples)", "competitor", "Lonavala", "Villa", "Premium villa", MMT_LONAVALA_MARKET_URL),
    ("C018", "Solace Forest Villa", "competitor", "Lonavala", "Villa", "Premium villa", MMT_LONAVALA_MARKET_URL),
    ("C019", "Radisson Blu Plaza Resort & Convention Centre Karjat", "competitor", "Karjat", "Resort", "Luxury leisure", MMT_KARJAT_MARKET_URL),
    ("C020", "U Rivergate Resort & Spa, Karjat", "competitor", "Karjat", "Resort", "Upper-upscale", MMT_KARJAT_MARKET_URL),
    ("C021", "The Forest Club Resort", "competitor", "Karjat", "Resort", "Upper-upscale family", MMT_KARJAT_MARKET_URL),
    ("C022", "Oleander Farms", "competitor", "Karjat", "Resort", "Luxury leisure", MMT_KARJAT_MARKET_URL),
    ("C023", "Villament Zinc Journey by The Fern, Karjat", "competitor", "Karjat", "Villa", "Premium villa", MMT_KARJAT_MARKET_URL),
    ("C024", "Pushpam Sanskruti Suites & Villas Resort", "competitor", "Karjat", "Villa resort", "Upper-upscale family", MMT_KARJAT_MARKET_URL),
    ("C025", "Discover Resorts - Karjat", "competitor", "Karjat", "Resort", "Upper-upscale family", MMT_KARJAT_MARKET_URL),
    ("C026", "Monteria Village Themed Adventure Park", "competitor", "Karjat", "Resort", "Experiential leisure", MMT_KARJAT_MARKET_URL),
    ("C027", "Stone Water By Zuper", "competitor", "Karjat", "Resort", "Upper-upscale", MMT_KARJAT_MARKET_URL),
    ("C028", "Paramount Riverfront Resort and Spa", "competitor", "Karjat", "Resort", "Upper-upscale", MMT_KARJAT_MARKET_URL),
    ("C029", "River Estates Luxury Resort and Spa", "competitor", "Karjat", "Resort", "Upper-upscale", MMT_KARJAT_MARKET_URL),
    ("C030", "Pinewood Resort", "competitor", "Karjat", "Resort", "Mid-upscale", MMT_KARJAT_MARKET_URL),
]

DEMO_CONDITIONS = [
    ("2026-10-09", "2026-10-10", 2, 1, "Breakfast preferred", "Free cancellation preferred"),
    ("2026-10-16", "2026-10-17", 1, 1, "Any", "Any"),
    ("2026-10-22", "2026-10-23", 2, 1, "Breakfast preferred", "Free cancellation preferred"),
    ("2026-10-24", "2026-10-26", 2, 1, "Breakfast preferred", "Free cancellation preferred"),
    ("2026-10-24", "2026-10-26", 3, 1, "Any", "Any"),
    ("2026-10-24", "2026-10-26", 4, 2, "Any", "Any"),
    ("2026-12-04", "2026-12-06", 2, 1, "Breakfast preferred", "Free cancellation preferred"),
]


def seed_demo_database(db_path: Path | str) -> None:
    """Create the presentable demo database. It contains no live price/availability claim."""
    path = Path(db_path)
    if path.exists():
        path.unlink()
    initialize_database(path)
    with database_session(path) as connection:
        for ordinal, prop in enumerate(DEMO_PROPERTIES):
            property_id, name, role, market, prop_type, segment, market_url = prop
            add_property(connection, {
                "property_id": property_id, "name": name, "role": role, "market": market, "property_type": prop_type,
                "segment": segment, "total_units": 28 + stable_number(property_id, 0, 48),
                "inventory_basis": "demo_assumption", "listing_url": market_url, "listing_status": "candidate_verification",
                "source_note": "Candidate market record seeded for the examination demonstration. Verify identity and listing through an approved MakeMyTrip source before operational use.",
            })
        run_id = start_run(connection, "demo_synthetic", authorization_reference="DEMO-ONLY", notes="Synthetic fixture: no MakeMyTrip price, availability, rating, review, or booking data is present.")
        attempted = succeeded = failed = 0
        for check_in, check_out, guests, rooms, meal_preference, cancellation_preference in DEMO_CONDITIONS:
            for index, prop in enumerate(DEMO_PROPERTIES):
                property_id = prop[0]
                capacity = 28 + stable_number(property_id, 0, 48)
                for snapshot_index, observed_at in enumerate(DEMO_OBSERVED_AT):
                    attempted += 1
                    rate_seed = stable_number(f"{property_id}|{check_in}|{guests}|{rooms}", 4200, 20500)
                    if property_id == "P001":
                        rate_seed += 6500
                    is_weekend = datetime.fromisoformat(check_in).weekday() >= 4
                    nights = (datetime.fromisoformat(check_out).date() - datetime.fromisoformat(check_in).date()).days
                    rate_multiplier = (1.24 if is_weekend else 1.0) * (1 + max(0, guests - 2) * 0.06) * rooms
                    rate_movement = (-0.02, 0.015, 0.07)[snapshot_index] + ((stable_number(f"m:{property_id}", -3, 4)) / 100)
                    selling_rate = round(rate_seed * rate_multiplier * (1 + rate_movement), 0)
                    public_rate = round(selling_rate / 0.86, 0)
                    base_units = stable_number(f"u:{property_id}|{check_in}|{guests}|{rooms}", 2, 12)
                    reduction = snapshot_index * stable_number(f"d:{property_id}|{check_in}", 0, 3)
                    if stable_number(f"sold:{property_id}|{check_in}", 0, 24) == 0 and snapshot_index == 2:
                        units = 0
                    else:
                        units = max(0, base_units - reduction)
                    availability = "sold_out" if units == 0 else "limited" if units <= 2 else "available"
                    review_count = stable_number(f"review:{property_id}", 40, 4600) + snapshot_index * stable_number(f"newreviews:{property_id}", 0, 4)
                    record = {
                        "property_id": property_id, "check_in": check_in, "check_out": check_out, "guests": guests, "rooms": rooms,
                        "meal_preference": meal_preference, "cancellation_preference": cancellation_preference, "observed_at": observed_at,
                        "room_type": "Comparable lead room", "availability_status": availability, "available_units": units,
                        "public_rate": public_rate, "selling_rate": selling_rate, "taxes_fees": round(selling_rate * 0.12, 0),
                        "discount_amount": round(public_rate - selling_rate, 0), "currency": "INR",
                        "meal_plan": "Breakfast included" if (index + snapshot_index) % 3 else "Room only",
                        "cancellation_terms": "Free cancellation" if (index + snapshot_index) % 4 else "Non-refundable",
                        "amenities": ["Pool", "Parking", "Wi-Fi"], "rating": round(3.5 + stable_number(f"rating:{property_id}", 0, 14) / 10, 1),
                        "review_count": review_count, "source_type": "demo_synthetic", "source_reference": f"DEMO-{property_id}-{check_in}-{observed_at[0:10]}",
                        "is_demo": True, "raw_payload": {"fixture": True, "created_for": "examination demonstration"},
                    }
                    try:
                        if ingest_observation(connection, record, collection_run_id=run_id):
                            succeeded += 1
                    except ValueError as exc:
                        failed += 1
                        record_error(connection, run_id, attempted, property_id, str(exc), record)
        finish_run(connection, run_id, attempted, succeeded, failed)
