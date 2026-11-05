# Typhoon Prep App

Mobile-first app for typhoon preparation — map of nearby clinics,
hospitals, and evacuation centers, weather warnings, and AI-assisted
before/during/after guidance.

Current status: backbone only. Map is working (SQLite -> FastAPI -> React +
Leaflet) with real Batangas City hospitals. Pins are hidden until you pick a
category. Weather and AI features are stubbed and not wired in yet.
See `CHANGELOG.md` for what changed in each update.

## Tech stack

- **Backend:** Python (FastAPI) + SQLite
- **Frontend:** React + TypeScript (Vite) + Leaflet (map)

## Requirements

- Python 3.10+ ([python.org](https://www.python.org/downloads/) — check "Add to PATH" during install)
- Node.js LTS ([nodejs.org](https://nodejs.org) — Windows Installer, defaults are fine)

## How to run it

You need **two terminals** open at the same time — one for the backend, one
for the frontend. Both need to stay running while you use the app.

### 1. Backend (Terminal 1)

```
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows users: if `pip` isn't recognized, use `py -m pip install -r requirements.txt`
and `py -m uvicorn app.main:app --reload --port 8000` instead.

Check it worked: open `http://127.0.0.1:8000/api/facilities` in a browser —
you should see JSON data for the 5 seeded hospitals.

### 2. Frontend (Terminal 2 — separate window, don't close Terminal 1)

```
cd frontend
npm install
npm run dev
```

Then open the URL it prints (usually `http://localhost:5173`).

You should see a map of Batangas City with no pins at first. Tap
**Hospitals** to show them, then tap a pin to see its address and phone number.

## Updating facility data

Facility coordinates come from OpenStreetMap (free, no API key). With internet:

```
cd backend
py scripts/fetch_facilities.py
```

This writes `backend/data/facilities.json`. Restart the backend to load it.
Open the file to review it and delete any wrong entries. OpenStreetMap coverage
is uneven in the Philippines, especially for evacuation centers, so confirm the
official list with the Batangas City CDRRMO. If the file is missing, the backend
uses a small hardcoded hospital list instead.

Cleaning the data (both files are in `backend/data/` and are kept when the
script is re-run):

- `exclude.txt`: facility names to drop (wrong, closed, or moved).
- `manual_facilities.json`: facilities to add by hand, such as evacuation
  centers. Each entry needs `name`, `type` (`hospital`, `clinic` or
  `evacuation_center`), `latitude` and `longitude`; `address`, `contact` and
  `notes` are optional.

The script also skips clinics named after individual doctors (M.D., Dr., ...)
and lists them in its output.

Map data (c) OpenStreetMap contributors.

## Stopping the servers

Press `Ctrl+C` in each terminal. On Windows, it may ask
`Terminate batch job (Y/N)?` — type `Y` and press Enter.

## Project structure

```
typhoon-app/
├── backend/
│   └── app/
│       ├── main.py       # FastAPI app, seeds facility list, /api/facilities endpoint
│       ├── models.py     # SQL tables (Facility, CachedResponse)
│       ├── schemas.py    # Request/response shapes
│       └── database.py   # SQLite connection
└── frontend/
    └── src/
        ├── App.tsx        # Renders MapPage
        ├── api/client.ts  # Talks to the backend
        ├── pages/MapPage.tsx  # Leaflet map + facility pins
        └── _later/        # Parked features (Before/During/After, weather,
                            # offline caching) — not wired in yet
```

## Next steps

- Wire the `_later/` pages back in (Before/During/After guides, weather page)
- Connect the offline caching (IndexedDB) so the app works with no signal
- Replace stubbed AI endpoints with real calls (prep plan, weather explainer, etc.)
- Make it installable as a PWA (manifest + service worker are scaffolded, untested)
