# Operating Runbook

## 1. Before the first collection

1. Confirm the selected primary property. The seed is Della Resorts, Lonavala; change it only after deciding the examination focus.
2. Review the 30 candidate comparable records in the property master. Confirm the property identity, location, listing URL, and relevance through an approved source.
3. Obtain and record the data-source authority (approved feed, partner account, written permission, or governed export process).
4. Record verified total inventory only when it is genuinely available. Do not infer it from a booking page.

## 2. Booking-condition matrix

Use a controlled matrix rather than random searches. The starter set covers:

| Purpose | Guests | Rooms | Stay pattern | Lead time |
|---|---:|---:|---|---|
| Near-term weekday | 2 | 1 | 1 night | 5–10 days |
| Single traveller | 1 | 1 | 1 night | 10–20 days |
| Core weekday | 2 | 1 | 1 night | 14–30 days |
| Weekend couple | 2 | 1 | 2 nights | 14–30 days |
| Weekend group | 3 | 1 | 2 nights | 14–30 days |
| Multi-room group | 4 | 2 | 2 nights | 14–30 days |
| Future stay | 2 | 1 | 2 nights | 45–90 days |

Keep the room type, meal selection, and cancellation preference as consistent as the authorised source permits.

## 3. Recommended collection frequency

- **Daily at a fixed time** for the next 30 days: captures price and availability reaction close to stay dates.
- **Twice daily** for the next 7–14 days and high-demand weekends: captures faster visible-inventory movement.
- **Weekly** for 31–90 days: sufficient for forward pricing and weekend-premium monitoring.
- **Before/after promotions and public holidays**: adds a named event to the collection-run note.

The application can accept any cadence. A fixed cadence makes velocity and changes defensible.

## 4. Import an approved batch

1. Copy the exact headers from `data/snapshot_import_template.csv`.
2. Fill `source_reference` with the approved feed ID, export identifier, or governed capture reference—not a vague label.
3. Run the importer with a source type and an authorisation reference.
4. Run `python scripts/validate_dataset.py`.
5. Start `python app.py`, then inspect the relevant booking condition in the dashboard.

The collection run and row-level errors are retained in the database. Correct only invalid source rows and import again; valid observations remain untouched.

## 5. What to review each morning

1. Sold-out transitions and material visible-unit reductions.
2. Properties that changed price by at least ±10% under the same condition.
3. Primary rate position versus comparable average.
4. Weekend premium versus weekday pricing.
5. Coverage gaps: properties/conditions without a fresh observation.
6. Data quality: confirm all records have evidence and an approved source.

## 6. Production guardrails

- Never describe observed availability changes as confirmed bookings.
- Never describe estimated gross booking value as confirmed revenue.
- Do not insert data that came from an unapproved automated collection process.
- Do not overwrite a historic observation to “correct” a market outcome; insert a corrected record with its own source reference and annotate the collection run.
