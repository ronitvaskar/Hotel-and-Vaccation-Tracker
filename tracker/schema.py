"""SQLite schema. Raw observations are immutable; derived changes are recalculable."""

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS properties (
    property_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('primary', 'competitor')),
    market TEXT NOT NULL,
    property_type TEXT NOT NULL,
    segment TEXT,
    total_units INTEGER CHECK(total_units IS NULL OR total_units >= 0),
    inventory_basis TEXT NOT NULL DEFAULT 'not_recorded',
    listing_url TEXT,
    listing_status TEXT NOT NULL DEFAULT 'candidate_verification',
    source_note TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_primary_property
    ON properties(role) WHERE role = 'primary';

CREATE TABLE IF NOT EXISTS booking_conditions (
    condition_id TEXT PRIMARY KEY,
    check_in TEXT NOT NULL,
    check_out TEXT NOT NULL,
    guests INTEGER NOT NULL CHECK(guests > 0),
    rooms INTEGER NOT NULL CHECK(rooms > 0),
    meal_preference TEXT NOT NULL DEFAULT 'Any',
    cancellation_preference TEXT NOT NULL DEFAULT 'Any',
    created_at TEXT NOT NULL,
    UNIQUE(check_in, check_out, guests, rooms, meal_preference, cancellation_preference)
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'completed_with_errors', 'failed')),
    attempted_count INTEGER NOT NULL DEFAULT 0,
    succeeded_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    authorization_reference TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL REFERENCES properties(property_id),
    condition_id TEXT NOT NULL REFERENCES booking_conditions(condition_id),
    observed_at TEXT NOT NULL,
    room_type TEXT NOT NULL DEFAULT 'Best available room',
    availability_status TEXT NOT NULL CHECK(availability_status IN ('available', 'limited', 'sold_out', 'unavailable', 'on_request')),
    available_units INTEGER CHECK(available_units IS NULL OR available_units >= 0),
    public_rate REAL CHECK(public_rate IS NULL OR public_rate >= 0),
    selling_rate REAL CHECK(selling_rate IS NULL OR selling_rate >= 0),
    taxes_fees REAL CHECK(taxes_fees IS NULL OR taxes_fees >= 0),
    discount_amount REAL CHECK(discount_amount IS NULL OR discount_amount >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    meal_plan TEXT,
    cancellation_terms TEXT,
    amenities_json TEXT,
    rating REAL CHECK(rating IS NULL OR (rating >= 0 AND rating <= 5)),
    review_count INTEGER CHECK(review_count IS NULL OR review_count >= 0),
    source_type TEXT NOT NULL CHECK(source_type IN ('authorized_feed', 'partner_export', 'manual_authorized', 'internal', 'demo_synthetic')),
    source_reference TEXT NOT NULL,
    raw_payload TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0 CHECK(is_demo IN (0, 1)),
    collection_run_id TEXT REFERENCES collection_runs(run_id),
    created_at TEXT NOT NULL,
    UNIQUE(property_id, condition_id, observed_at, room_type, source_reference)
);

CREATE INDEX IF NOT EXISTS idx_observations_lookup
    ON observations(condition_id, property_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_observations_property
    ON observations(property_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS change_events (
    event_id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL REFERENCES properties(property_id),
    condition_id TEXT NOT NULL REFERENCES booking_conditions(condition_id),
    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
    previous_observation_id TEXT REFERENCES observations(observation_id),
    observed_at TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN ('availability_decreased', 'availability_increased', 'became_sold_out', 'became_available', 'price_increased', 'price_decreased', 'discount_changed', 'room_type_changed', 'meal_plan_changed', 'cancellation_changed', 'rating_changed', 'review_count_changed')),
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    absolute_change REAL,
    estimated_units_sold INTEGER NOT NULL DEFAULT 0 CHECK(estimated_units_sold >= 0),
    estimated_revenue REAL NOT NULL DEFAULT 0 CHECK(estimated_revenue >= 0),
    is_estimate INTEGER NOT NULL DEFAULT 1 CHECK(is_estimate IN (0, 1)),
    methodology_note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_changes_condition
    ON change_events(condition_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_errors (
    error_id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES collection_runs(run_id),
    source_row INTEGER,
    property_id TEXT,
    error_message TEXT NOT NULL,
    raw_row TEXT,
    retryable INTEGER NOT NULL DEFAULT 0 CHECK(retryable IN (0, 1)),
    created_at TEXT NOT NULL
);
"""
