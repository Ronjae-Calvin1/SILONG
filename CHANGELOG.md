# Change log

Short log of what changed in each update, newest first.

## Update 6 — Capacity and availability
- Tap a pin to open a details panel: name, type, address, tap-to-call phone,
  status, "Last updated: <time> (15 minutes ago)", people inside ("85 / 100"),
  resources and note. **Update status** opens a phone-friendly form with big
  buttons; on success the pin and panel update immediately.
- Pins are colored by status (green open, orange almost full / busy, red full,
  grey closed, light grey no status yet, dim with dashed ring when older than
  6 hours). A letter in the pin shows the type (H, C, E).
- Backend: new `status_updates` table (history; newest = current), validation
  per facility type (422 with a clear message), `POST /api/facilities/{id}/status`,
  `GET /api/facilities/{id}/status/history`, and `/api/facilities` now includes
  each place's latest `status` (or `null`) with a server-computed `is_outdated`.
- Facility IDs are now stable: facilities carry a permanent `key` and are synced
  by key at startup instead of deleted and re-inserted.
- Spam protection without login: 1 update per place per IP per minute and 10 per
  IP per 10 minutes, in memory. The page shows the friendly "please wait" message.
- The page re-checks the server every minute and refreshes "x minutes ago" labels.
- New files: `backend/app/config.py` (6-hour rule and limits, to confirm),
  `rate_limit.py`, `status_service.py`, `scripts/backdate_status.py` (test the
  outdated rule), and `frontend/src/components/` `FacilityPanel.tsx`,
  `StatusForm.tsx`, `statusInfo.ts`, `StatusPanel.css`.
- Old databases are upgraded automatically (the facilities table is rebuilt once).
- To confirm with the documentation: the 6-hour threshold and the rate limits.

## Update 5 — Hospital list cleanup
- `backend/scripts/fetch_facilities.py`: removes same-name duplicate points
  within 100 m (Jesus of Nazareth was listed twice) and moves health centers and
  maternity/lying-in places tagged "hospital" into the clinic category. Both
  are printed when the script runs.
- `backend/data/exclude.txt`: prefilled. Active: a doctor's office and the Red
  Cross (both tagged hospital), laboratories, drug testing, skin/laser
  clinics. Commented out (your decision): other private clinics.
- Checked the 11 hospital entries against the Batangas City official list: all
  6 official hospitals are present.

## Update 4 — Cleaner clinic data
- `backend/scripts/fetch_facilities.py`: skips clinics whose names look like an
  individual doctor's office (M.D., Dr., Dra., DMD...), which caused stacked
  pins on one building. Prints every skipped name so the filter can be checked.
  Hospitals are never filtered.
- New `backend/data/exclude.txt`: names to always drop (wrong, closed, moved).
  Survives re-running the script.
- New `backend/data/manual_facilities.json`: facilities added by hand (for
  example evacuation centers). Merged in on every run.
- `README.md`: documented both files.
- Limits: the filter is a name-based guess and cannot tell if a place has moved
  or closed. Check the final pins against real life before submission.

## Update 3 — Fetch facilities from OpenStreetMap
- New `backend/scripts/fetch_facilities.py`: pulls hospitals, clinics and
  assembly points for Batangas City from the free Overpass API (OpenStreetMap)
  and saves them to `backend/data/facilities.json`. Standard library only.
- `backend/app/main.py`: loads `data/facilities.json` on startup if it exists,
  otherwise falls back to the hardcoded hospital list.
- `README.md`: added "Updating facility data".
- Not tested against the live API (no network access where this was written):
  run it, check the output, and report any errors.

## Update 2 — Batangas City map data + cleaner map
- `backend/app/main.py`: replaced the 3 made-up Rosario facilities with 5 real
  Batangas City hospitals (Batangas Medical Center, Golden Gate General,
  Jesus of Nazareth, St. Patrick's, United Doctors of St. Camillus de Lellis).
  Facilities are now reset from the list in code on every backend start.
- `frontend/src/pages/MapPage.tsx`: map starts with no pins; category buttons
  (Hospitals / Clinics / Evacuation centers) turn pins on and off. Map height
  now fits the screen instead of a fixed 500px. Popups show a tap-to-call number.
- `README.md`: updated for Batangas City.
- Known gaps: coordinates (except Batangas Medical Center) are approximate and
  need checking in Google Maps; no clinics or evacuation centers yet (need the
  official list from the Batangas City CDRRMO / barangay halls); Batangas
  Healthcare Specialists Medical Center is not added (no coordinates found).

## Update 1 — Initial backbone
- FastAPI + SQLite facilities API, React + TypeScript frontend, Leaflet map.
- Placeholder Rosario sample data (replaced in Update 2).
