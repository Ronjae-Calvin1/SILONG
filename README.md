# SILONG

Mobile-first website that helps people in Batangas City during a storm or
other emergency. It shows where the nearest hospitals, clinics and evacuation
centers are, and (once built) whether those places still have space. It also
shows the weather, warnings and emergency numbers, and has a chatbot that
gives short, clear answers.

- No accounts. Anyone can use it right away, with no sign-up and no login.
- Mobile first, but online only. There is no offline mode and the site is not
  meant to be installed on the home screen.
- Official advisories (PAGASA, NDRRMC, the city) always come first.

The full list of functions is in the project documentation (Websys - Project
documentation). `CHANGELOG.md` lists what changed in each update.

## What the site does

| Function | What it does | Status |
| --- | --- | --- |
| Map | Shows hospitals, clinics and evacuation centers. All pins show automatically. Tap a pin for the name, address and a tap-to-call number. | Working |
| Capacity and availability | Tap a pin to see whether a place is open, busy or full and when that was last updated. Anyone can update it, with no login. | Working |
| Weather forecast | Current weather and a short forecast. | Screen only, sample data |
| Emergency contacts | Red phone button that opens numbers to call with one tap. | Button only, not wired |
| Early warning alerts | Bottom panel with weather, official warnings and summarized internet updates. | Screen only, sample data |
| Incident report | Report an incident with a location from GPS or a point on the map. | Form works, saved on the phone only, not sent to a server |
| AI chatbot | One question in, one short answer out, from a checked guide only. | Button only. Backend answers are stubbed |

Status is based on the code in this repository. Anything marked "Not built
yet" or "not wired" is planned in the documentation but does not work yet.

## Tech stack

- **Backend:** Python (FastAPI) + SQLite
- **Frontend:** React + TypeScript (Vite) + MapLibre GL (vector map)
- **Base map:** MapTiler (needs a free API key)

## Requirements

- Python 3.10+ ([python.org](https://www.python.org/downloads/): check "Add to PATH" during install)
- Node.js LTS ([nodejs.org](https://nodejs.org): Windows Installer, defaults are fine)
- A free MapTiler account and API key (see "Map setup" below)

## How to run it

You need **two terminals** open at the same time: one for the backend, one
for the frontend. Both need to stay running while you use the app.

### 1. Backend (Terminal 1)

```
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Windows users: if `pip` isn't recognized, use `py -m pip install -r requirements.txt`
and `py -m uvicorn app.main:app --reload --port 8000` instead.

Check it worked: open `http://127.0.0.1:8000/api/facilities` in a browser.
You should see JSON data for the facilities.

### 2. Map setup (once per computer)

The map needs a MapTiler key. The key is **not** stored in this repository.

1. Make a free account at [cloud.maptiler.com](https://cloud.maptiler.com).
2. Go to **Account > API keys** and create a key.
   - **Name:** anything, for example `SILONG`.
   - **Allowed HTTP Origins:** `localhost` for testing. Type only the host
     name, without `http://`. Add your real domain here when the site goes
     online.
   - Leave **Allowed user-agent header** empty.
3. In the `frontend` folder, copy `.env.example` to `.env`.
4. Open `.env` and fill in:
   ```
   VITE_MAPTILER_KEY=your_key_here
   VITE_MAPTILER_STYLE=streets-v2
   ```
   `streets-v2` is MapTiler's standard Streets map. To use a custom map (for
   example one with the shop icons hidden and the names kept), put its map ID
   here instead. See "Using a custom map" below.

`.env` is ignored by Git, so your key will not be pushed. Never put the key in
`.env.example` or in any file that gets committed.

If `VITE_MAPTILER_KEY` is empty, the map falls back to plain OpenStreetMap so
the app still runs.

**Teammates:** each person sets up their own `.env` on their own computer. A
teammate can create their own key, but a key from a different MapTiler account
cannot load your custom map (it returns a 403 error). See "Using a custom map".

### 3. Frontend (Terminal 2: separate window, don't close Terminal 1)

```
cd frontend
npm install
npm run dev
```

Then open the URL it prints (usually `http://localhost:5173`). Restart
`npm run dev` after any change to `.env`, because Vite only reads it on start.

You should see a map of Batangas City with all the pins already on it. Tap a
pin to see its address and phone number.

## Capacity and availability

Tap a pin to see its status, when it was last updated ("15 minutes ago") and,
for evacuation centers, how many people are inside. Tap **Update status** to
report a new one. The pin changes color right away:

| Pin | Meaning |
| --- | --- |
| Green | Open |
| Orange | Almost full (evacuation center) or Busy / Limited (hospital, clinic) |
| Red | Full |
| Dark grey | Closed |
| Light grey | No status yet (never shown as "Open") |
| Dim, dashed ring | Last update is older than 6 hours: "May be outdated" |

Every update is saved as history in SQLite; the newest one is the status. People
can only send status data, never a place's name, address or phone number.

**Settings to confirm** (`backend/app/config.py`, each can also be set with an
environment variable):

- `OUTDATED_AFTER`: 6 hours (`STATUS_OUTDATED_AFTER_HOURS`). The only place this
  number lives.
- `STATUS_COOLDOWN_SECONDS`: 60, one update per place per IP.
- `STATUS_IP_MAX_UPDATES` / `STATUS_IP_WINDOW_SECONDS`: 10 updates per IP per 10 minutes.

**Try it** (backend and frontend running as above):

1. Open the site, tap a pin, tap **Update status**, pick a status, **Submit**.
2. Refresh the page: the status is still there.
3. Update the same place again within a minute: you get a "please wait" message.
   For testing, start the backend with `STATUS_COOLDOWN_SECONDS=0` to turn that off.
4. See the 6-hour rule: backdate the latest update of a place, then refresh.
   ```
   cd backend
   py scripts/backdate_status.py --list          # which places have updates
   py scripts/backdate_status.py 3 --hours 7     # make place 3's update 7 hours old
   ```
5. Call the API directly (Mac/Linux/Git Bash):
   ```
   curl -X POST http://127.0.0.1:8000/api/facilities/3/status \
     -H "Content-Type: application/json" \
     -d '{"status": "busy", "note": "Long wait at the ER"}'
   ```
   Windows Command Prompt:
   ```
   curl.exe -X POST http://127.0.0.1:8000/api/facilities/3/status -H "Content-Type: application/json" -d "{\"status\": \"busy\", \"note\": \"Long wait at the ER\"}"
   ```
   A status that does not fit the place (for example `almost_full` for a
   hospital) returns 422. Also: `GET /api/facilities` (each place has `status`,
   or `null`) and `GET /api/facilities/3/status/history?limit=10`.

The current data has no evacuation centers yet. To try the evacuation center form,
add one to `backend/data/manual_facilities.json` (see "Updating facility data")
and run the fetch script, or add an entry to `facilities.json` and restart.

**Facility IDs:** each facility gets a permanent key (its OpenStreetMap
reference, or type + name for manual entries). On every start the backend
matches the data file to the database by that key instead of rebuilding the
table, so a place keeps its ID and its history when the file is re-fetched or
reordered. A place that disappears from the file is removed together with its
history.

## Using a custom map

A custom map lets you hide icons you do not want while keeping place names.

1. In MapTiler Cloud, copy a Streets map, edit it, and **Publish** it.
2. Copy its map ID: the part between `/maps/` and `/style.json` in the map's
   style link.
3. Put the ID in `frontend/.env` as `VITE_MAPTILER_STYLE`.

A custom map belongs to one MapTiler account, and the key must come from the
same account. If a teammate needs the custom map, either share the key and map
ID privately (not through GitHub), or each person uses `streets-v2` with their
own key. The map shows pin icons either way.

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

Map data (c) OpenStreetMap contributors. Base map (c) MapTiler.

## Stopping the servers

Press `Ctrl+C` in each terminal. On Windows, it may ask
`Terminate batch job (Y/N)?`. Type `Y` and press Enter.

## Project structure

```
SILONG/
├── backend/
│   └── app/
│       ├── main.py             # FastAPI app, loads facilities, /api/facilities
│       ├── routes.py           # API routes (weather and AI routes are stubs)
│       ├── models.py           # SQL tables (facilities, status updates)
│       ├── schemas.py          # Request/response shapes and status rules
│       ├── config.py           # 6-hour outdated rule, rate limits
│       ├── rate_limit.py       # Per-IP limit on status updates
│       ├── status_service.py   # Reads latest status / history
│       ├── database.py         # SQLite connection
│       ├── weather_service.py  # Sample weather data (stub)
│       └── ai_service.py       # Chatbot/AI answers (stub)
└── frontend/
    ├── .env.example            # Copy to .env and add your MapTiler key
    └── src/
        ├── App.tsx             # Renders MapPage
        ├── api/client.ts       # Talks to the backend
        ├── pages/MapPage.tsx   # MapLibre map + facility pins
        ├── components/         # Top bar, round buttons, alerts panel, incident form,
        │                       # facility details panel and status update form
        └── _later/             # Parked pages and offline code (not used)
```

## Next steps

Based on the project documentation:

- Emergency contacts screen behind the red phone button (numbers must be
  checked with the Batangas City CDRRMO).
- Real weather (Open-Meteo) and official warnings in the Early Warning panel.
- Send incident reports to a server instead of saving them on the phone only.
- Chatbot that answers from a checked guide only, with the fixed "AI-generated.
  Follow official advisories first." line.
- Clean-up to match "online only": the offline code in `_later/` and the PWA
  install settings in `frontend/vite.config.ts` are left from an earlier plan
  and should be removed.
- Add distinct pin colors for hospitals, clinics and evacuation centers.
