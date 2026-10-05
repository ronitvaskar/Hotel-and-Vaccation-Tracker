# Technical Architecture

## Design goal

Produce an auditable historical intelligence system for one primary leisure property and a scalable comparable set. The design is intentionally independent of one marketplace: MakeMyTrip is the Version 1 source boundary, while the data model supports future Booking.com or other approved sources.

```text
Approved feed / partner export / authorised manual review
                         │
                         ▼
              CSV import or source adapter
                         │
              validation + duplicate prevention
                         │
       ┌─────────────────┴─────────────────┐
       ▼                                   ▼
immutable observations                 ingestion_errors
       │                                   │
       ▼                                   ▼
change-event derivation             collection-run audit log
       │
       ▼
SQLite historical database ─────► Local dashboard / JSON API
                                      │
                                      ▼
                       rates · availability · estimates · trends
```

## Components

| Component | Implementation | Responsibility |
|---|---|---|
| Local dashboard | Python `ThreadingHTTPServer` + vanilla HTML/CSS/JS | Presents an interactive analytical view without external runtime dependencies. |
| Persistent store | SQLite | Stores the property master, booking conditions, immutable observations, events, runs, and errors. |
| Ingestion | `scripts/import_snapshots.py` | Validates an approved CSV export, creates a collection run, logs failed rows, and continues with the rest. |
| Change detector | `detect_changes()` | Compares each newly inserted observation to the prior record for the same property, condition, and room type. |
| Estimation model | Dashboard query layer | Converts observed unit reductions into explicitly labelled estimated room-night and gross booking-value signals. |
| Readiness checks | `scripts/validate_dataset.py` | Confirms data coverage and integrity before a demonstration. |

## Data model

### `properties`

One primary property and an unlimited number of comparable properties. `inventory_basis` distinguishes a verified property inventory from an assumption. `listing_status` prevents candidate records from being mistaken for verified source identities.

### `booking_conditions`

A reusable, deduplicated definition of the search context: check-in, check-out, guests, rooms, meal preference, and cancellation preference. This makes weekday/weekend, lead-time, multi-night, and guest-count analysis comparable rather than mixing unlike searches.

### `observations`

The core fact table. Each row is an immutable answer to “what did the authorised source show at this time under this booking condition?” It holds rate components, availability, room type, conditions, amenities, ratings, source evidence, and a raw payload. A unique key prevents the same observation from being inserted twice.

### `change_events`

Derived, traceable events connect an observation to its immediate predecessor. A single observation can create several events—for example, a price increase and visible-unit reduction. The previous observation ID, old/new values, calculation amount, and methodology note are retained.

### `collection_runs` and `ingestion_errors`

These make the pipeline supportable. A failed row/property does not terminate an import. The run records total attempts, successes, and failures; individual error records preserve the raw row and whether a retry would be appropriate.

## Change logic

Changes are compared only when the property ID, booking condition, and room type match. The system detects:

- visible units decreased or increased;
- a property became sold out or became available;
- selling rate increased or decreased;
- discount, meal plan, cancellation, rating, or review-count change.

The comparison is directionally useful, but a source-visible inventory increase can reflect a cancellation, release, allocation adjustment, or source measurement difference. It is never automatically converted into a negative booking count.

## Scale and resilience

The first build uses SQLite and a single local importer because this is simple, reproducible, and sufficient for an examination demo. It scales without redesigning the schema:

1. Add any number of property records to `properties`.
2. Split the property list into source batches (for example 25–50 properties per job).
3. Use bounded concurrent workers for approved-feed calls and a queue for retryable source failures.
4. Preserve the existing idempotency key when writing back to the database.
5. Move the writer to PostgreSQL when multi-user or high-frequency ingestion makes SQLite locking inappropriate.

This prevents one unavailable property or source response from stopping the full portfolio collection.

## Source governance

The source adapter is deliberately separated from the analysis application. Do not add automated page collection unless the platform provides written permission or an applicable approved interface. A valid production source should populate `source_type`, `source_reference`, and `authorization_reference` for every run.
