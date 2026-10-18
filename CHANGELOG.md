# Change log

Short log of what changed in each update, newest first.

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
