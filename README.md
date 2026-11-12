# SILONG

Mobile-first website that helps people in Batangas City during a storm or
other emergency. It shows where the nearest hospitals, clinics and evacuation
centers are, and (once built) whether those places still have space. It also
shows the weather, warnings and emergency numbers, and has a chatbot that
gives short, clear answers.

- No accounts for the public. Anyone can use the map, report, and ask the
  chatbot right away, with no sign-up and no login.
- Staff accounts (planned): **Responders** and **Super admins** sign in. There
  is no public sign-up. Responders use a phone or a computer; Super admins use
  a computer.
- Mobile first, but online only. There is no offline mode and the site is not
  meant to be installed on the home screen.
- Official advisories (PAGASA, NDRRMC, the city) always come first.
- This is a school project that runs on localhost. It is not deployed.

The full list of functions is in the project documentation (Websys - Project
documentation). `CHANGELOG.md` lists what changed in each update.

**Redesign in progress.** The screens and rules for the next version are in
[`docs/REDESIGN.md`](docs/REDESIGN.md). Until a part is built, this README
describes what the code does today, and the "Planned" rows below describe what
is designed but not built.

## What the site does

| Function | What it does | Status |
| --- | --- | --- |
| Map | Shows hospitals, clinics and evacuation centers. All pins show automatically. Tap a pin for the name, address and a tap-to-call number. | Working |
| Capacity and availability | Tap a pin to see whether a place is open, busy or full and when that was last updated. Evacuation centers also show a capacity bar ("85 / 100 people", "15 spaces left"). Anyone can update it, with no login. | Working. Planned: "Reported by a user" and "Confirmed by official" labels |
| Evacuation center manager | Add an evacuation center on the map, remove one, and restore a removed one. Removing hides a center, it never deletes it. | Working today. Planned: new places wait for admin approval, "hide" only affects one phone, admin removal is kept 30 days and then deleted |
| Weather forecast | Current weather and a short forecast. | Screen only, sample data |
| Emergency contacts | Red phone button that opens numbers to call with one tap. | Button only, not wired |
| Early warning alerts | Bottom panel with weather, official warnings and summarized internet updates. | Screen only, sample data |
| Incident report | Report an incident with a location from GPS or a point on the map. | Form works, saved on the phone only, not sent to a server |
| AI chatbot | One question in, one short answer out, from a checked guide only. No follow-ups and no live place status. Every answer ends with "AI-generated. Follow official advisories first." | Button only. Backend answers are stubbed |
| Help requests and hazard reports (replaces the incident report form) | "I need help" goes to responders only and is never shown on the map. A hazard report shows to nearby people as an approximate spot, "Unconfirmed" after 3 reports from 3 phones, "Verified" once an admin checks it. | Planned (designed, not built) |
| Responder side | Reports list, map, places and a resolve step. Phone and computer layouts. | Planned (designed, not built) |
| Super admin side | Everything a responder does, plus advisories, emergency numbers, the chatbot guide, accounts, the audit log and permanent delete. Computer only. | Planned (designed, not built) |
| FAQs, support and "My reports and places" | Menu pages. | Planned (designed, not built) |

Status is based on the code in this repository. Anything marked "Not built
yet", "not wired" or "Planned" is designed or described in the documentation
but does not work yet.

Pins show the place type as a letter (H hospital, C clinic, E evacuation
center) with a matching shape (cross, circle-cross, house, tent), so the type
is never shown by color alone.

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
for evacuation centers, how full it is. Tap **Update status** to report a new
one. The pin and the panel change right away, with no reload.

**Status** (what people can pick, and the pin color it gives):

| Status | Place | Pin |
| --- | --- | --- |
| Open - Space available | Evacuation center | Green |
| Almost full | Evacuation center | Orange |
| Full | Evacuation center | Red |
| Closed / Not in use | Evacuation center | Dark grey |
| Open - Accepting patients | Hospital, clinic | Green |
| Busy / Limited | Hospital, clinic | Orange |
| Full / Not accepting | Hospital, clinic | Red |
| Closed | Hospital, clinic | Dark grey |
| No status yet | Any | Hollow pin (never shown as "Open") |

Other pin looks: **dim with a dashed ring** means the last update is older than
6 hours ("May be outdated" in the panel). A **small blue ring** means the center
was added through the app. The letter in the pin is the type (H, C, E).

**Capacity** (evacuation centers only). The panel shows a bar when both the
maximum capacity and the people inside are known:

| People inside | Bar | Text |
| --- | --- | --- |
| Under 70% of capacity | Green | `30 / 100 people`, `70 spaces left` |
| 70% to 99% | Orange | `85 / 100 people`, `15 spaces left` |
| 100% or more | Red | `100 / 100 people`, `No spaces left` |

If the people inside are not known, only `Capacity: 100 people` is shown. A new
center has a capacity but no status yet, so it shows "No status yet" together
with its capacity. Older centers from OpenStreetMap or the manual file have no
capacity: the panel says "Capacity not set" with a small **Set capacity** button
(it opens the update form at the capacity field; a report always needs a status
too).

The update form for an evacuation center offers the four statuses above, and
optionally people inside, maximum capacity (filled in from the center), what is
available (space, food, water, power, toilets, medical) and a short note.
Hospitals and clinics keep their own form (status and a short note).

**Automatic "Full":** if the people inside reach the maximum capacity and the
status sent is "Open" or "Almost full", the server saves it as **Full** and the
page shows its message ("People inside (100) has reached the maximum capacity
(100), so this center was saved as full."). A report that leaves the capacity
out keeps the last known one. A people count of more than twice the capacity is
refused as a typo.

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

The current data file has no evacuation centers. Add one in the app (see
"Evacuation centers: add, remove, restore" below), or add one to
`backend/data/manual_facilities.json` (see "Updating facility data").

**Facility IDs:** each facility gets a permanent key (its OpenStreetMap
reference, type + name for manual entries, or `user:<n>` for centers added in
the app). On every start the backend matches the data file to the database by
that key instead of rebuilding the table, so a place keeps its ID and its
history when the file is re-fetched or reordered. A place that disappears from
the file is removed together with its history. Centers added in the app live in
their own table, so re-fetching the file never removes them.

## Evacuation centers: add, remove, restore

**Add a center**

1. Tap **Add evacuation center** (bottom left), then tap the map to place the pin.
   Drag the pin to adjust it, then tap **Continue**.
2. Fill in the form: name, type (Permanent or Temporary) and **maximum capacity**
   are required; barangay, address, contact number and a short note are optional.
   The location must be inside Batangas City (a rough box set in
   `BATANGAS_CITY_BBOX` in `config.py`). Tap **Save evacuation center**.
3. The pin appears right away with a blue ring. It shows "No status yet" and
   "Capacity: N people" until someone reports.

A center with the same name within 30 m of an existing one is refused. If that
one was removed earlier, the message says to restore it instead.

**Remove a center:** tap its pin, then **Remove from map** and **Yes, remove**.
Only evacuation centers can be removed; hospitals and clinics cannot.

**Restore a center:** tap the menu button (top left), open **Removed centers**
and tap **Restore** next to the center. Its pin comes back right away, with its
old status history.

**Soft delete:** removing never deletes anything. The center and its status
history stay in the database; a row in `facility_removals` hides it from
`GET /api/facilities` until it is restored (`restored_at` is filled in). The
hiding is kept when the backend restarts and when the facilities file is
re-fetched, and it works the same for centers from OpenStreetMap, the manual
file and the app. Adds, removals and restores are also written to `action_log`
with a hashed IP address (never the address itself). There are no accounts, so
the only protection is a limit: 10 add/remove/restore actions per IP per 10
minutes (`MANAGE_MAX_ACTIONS`, `MANAGE_WINDOW_SECONDS`).

| Action | Endpoint |
| --- | --- |
| Add | `POST /api/evacuation-centers` |
| Remove (hide) | `DELETE /api/evacuation-centers/{id}` |
| List removed | `GET /api/evacuation-centers/removed` |
| Restore | `POST /api/evacuation-centers/{id}/restore` |

**Try it** (backend and frontend running; start the backend with
`STATUS_COOLDOWN_SECONDS=0` so repeated updates are not delayed):

1. Add a center with capacity 100. The panel shows "No status yet" and
   "Capacity: 100 people".
2. Update status: **Almost full**, people inside 85. Orange pin, orange bar,
   "85 / 100 people", "15 spaces left".
3. Update status: **Open**, people inside 100. The page shows the "saved as
   full" message; the pin and bar turn red and the status is **Full**.
4. Refresh the page: the center and its status are still there.
5. Remove it, restart the backend, refresh: it stays hidden.
6. Menu, **Removed centers**, **Restore**: the pin is back.

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
│       ├── main.py             # FastAPI app, loads facilities, /api/facilities and the status routes
│       ├── routes.py           # API routes (weather and AI routes are stubs)
│       ├── evac_routes.py      # Add / remove / restore evacuation centers
│       ├── evac_service.py     # Center keys, duplicate check, soft delete, action log
│       ├── models.py           # SQL tables (facilities, status updates, user centers, removals, action log)
│       ├── schemas.py          # Request/response shapes and status rules
│       ├── config.py           # 6-hour outdated rule, rate limits, city area, duplicate distance
│       ├── rate_limit.py       # Per-IP limits (status updates, add/remove/restore)
│       ├── status_service.py   # Latest status / history, capacity rule (automatic "Full")
│       ├── database.py         # SQLite connection
│       ├── weather_service.py  # Sample weather data (stub)
│       └── ai_service.py       # Chatbot/AI answers (stub)
└── frontend/
    ├── .env.example            # Copy to .env and add your MapTiler key
    └── src/
        ├── App.tsx             # Renders MapPage
        ├── api/client.ts       # Talks to the backend
        ├── pages/MapPage.tsx   # MapLibre map + facility pins
        ├── components/         # Top bar, round buttons, alerts panel, incident form, plus:
        │   ├── FacilityPanel.tsx      # Details panel: status, last updated, remove button
        │   ├── CapacityIndicator.tsx  # Capacity bar, "Capacity: N people", "Capacity not set"
        │   ├── StatusForm.tsx         # Update status form (own statuses for centers vs hospitals)
        │   ├── statusInfo.ts          # Status labels, time labels, capacity colors
        │   ├── AddEvacCenter.tsx      # "Add evacuation center" button, pin placement
        │   ├── EvacCenterForm.tsx     # Details form for a new center
        │   ├── RemovedCenters.tsx     # "Removed centers" list with Restore (top-bar menu)
        │   └── StatusPanel.css, EvacManager.css   # Styles for the above
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
