# Examination Demonstration Script

## Set-up

Open the dashboard at `http://127.0.0.1:8765` after running `python app.py --seed-demo`. The included setup demonstrates system capability with synthetic values. For the live-data portion, use only an approved source and identify the collection-run authorisation reference.

## Suggested 8–10 minute walkthrough

### 1. State the business question (30 seconds)

“This application monitors the Lonavala–Karjat leisure market around one primary property, Della Resorts. It preserves comparable booking-condition observations over time so rates, availability, and demand signals can be compared rather than viewed as one-off quotes.”

### 2. Show the property master and coverage (60 seconds)

Run `python scripts/validate_dataset.py`. Show that there is one primary record, 30 comparable records, multiple booking conditions, historical snapshots, change events, and no duplicate observation keys. Explain that the candidate set is scalable; the schema does not hard-code 30.

### 3. Explain booking combinations (60 seconds)

Open the condition selector. Demonstrate the choices for 1, 2, 3 and 4 guests; the two-room group case; weekday and weekend stays; near-term and future dates; and one- versus two-night stays. Explain that all rate comparisons are scoped to the selected condition.

### 4. Show repeated tracking and history (90 seconds)

Select a condition with multiple observations. Point to the historical line chart and change ledger. Explain that `observations` is immutable and the change detector compares a new row to the prior row for the same property, condition, and room type.

### 5. Show market intelligence (90 seconds)

Use the rate-position chart and portfolio table to identify sold-out properties, visible-unit reductions, rate moves, and the primary property’s position against the comparable average. Change to a weekend condition and then a different guest count to show the difference in market position.

### 6. Explain estimated sales/revenue responsibly (90 seconds)

Open the estimation disclosure. State clearly: “A drop in visible units is an estimated demand/sales signal, not a confirmed private booking. Estimated gross value is visible-unit drop times observed selling rate, and is not confirmed revenue.”

### 7. Show the live/authorised pipeline (90 seconds)

Open `data/snapshot_import_template.csv` and `scripts/import_snapshots.py`. Show the mandatory source reference and authorisation reference. For a live approved export, import a small authorised CSV, run the readiness check, refresh the dashboard, and show the new stored observation/change. Do not use a non-approved automated website collector.

### 8. Close on scale and reliability (30 seconds)

Explain that each collection is a run, invalid rows are logged without halting the batch, and the schema supports 50, 100, or more properties. In a larger rollout, approved-source polling workers would use bounded concurrency and queues while retaining the same idempotency key and historical database.

## Live-data checklist

Before stating that the demonstration is live, confirm all of the following:

- written permission, approved feed, partner agreement, or governed export is available;
- the collection run records its authorisation reference;
- each imported row carries a source reference;
- dates, guests, rooms, room type, meals, and cancellation conditions are recorded;
- the app is not showing the synthetic fixture as live data.
