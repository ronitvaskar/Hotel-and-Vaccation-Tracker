# Submission Checklist

## Mandatory assignment coverage

- [x] One primary Lonavala/Karjat property configured
- [x] 30 comparable competitor records configured
- [x] Competitor list is data-driven; adding properties does not require code changes
- [x] Persistent database with immutable observations
- [x] Duplicate prevention on observation key
- [x] Booking conditions covering 1, 2, 3 and 4 guests, multiple room quantities, weekday/weekend and different stay lengths
- [x] Historical observations retained
- [x] Availability change detection
- [x] Price change detection
- [x] Discount / meal / cancellation / rating / review change detection
- [x] Estimated units sold, room nights and gross booking value
- [x] Explicit distinction between observable signals and confirmed private bookings
- [x] Competitor comparison dashboard
- [x] Guest-count and weekday/weekend analysis
- [x] Room-type analysis
- [x] CSV observation export
- [x] Collection-run audit log
- [x] Row-level ingestion error isolation
- [x] Automated regression tests
- [x] Readiness validation script

## Important before claiming a live MakeMyTrip demonstration

The included demo database is synthetic and is intentionally labelled as such. Replace or supplement it with observations collected through an authorised MakeMyTrip source, partner export, approved API/feed, or authorised manual capture. The assignment requires a live-data demonstration and asks students to respect access controls and permissions.

## Final commands

```powershell
python -m unittest discover -s tests -v
python scripts/validate_dataset.py
python app.py
```

Open `http://127.0.0.1:8765`.

For a clean synthetic demonstration:

```powershell
python app.py --seed-demo
```
