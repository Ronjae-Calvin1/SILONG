# SILONG

Mobile-first website that helps people in Batangas City during a storm or
other emergency. It shows where the nearest hospitals, clinics and evacuation
centers are, and (once built) whether those places still have space. It also
shows the weather, warnings and emergency numbers, and has a chatbot that
gives short, clear answers.

- No accounts for the public. Anyone can use the map, report, and ask the
  chatbot right away, with no sign-up and no login.
- Staff accounts: **Responders** and **Super admins** sign in. There is no
  public sign-up. Responders use a phone or a computer; Super admins use a
  computer. The accounts, sign in, roles and audit log work on the server
  (backend only so far; the sign-in screens are not built yet).
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
| Capacity and availability | Tap a pin to see whether a place is open, busy or full and when that was last updated. Evacuation centers also show a capacity bar ("85 / 100 people", "15 spaces left"). Anyone can update it, with no login. Each update says who it came from: "Reported by a user" or "Confirmed by official" (a signed-in responder or Super admin). | Working on the server (`source` and `source_label` in `/api/facilities`). Planned: showing the label in the screens |
| Evacuation center manager | A place a user adds waits for a responder or Super admin to approve it, and only its sender sees it until then. "Hide on this phone" only affects that phone. Removing a center for everyone is an admin action; it is kept 30 days (restorable), then deleted with its history. Only a Super admin can delete one sooner. | Working on the server (add, approve, reject, remove, restore, 30-day purge, permanent delete). The frontend still has no screen to approve places or to send the phone ID with an added place (see below) |
| Weather forecast | Current weather and a short forecast. | Screen only, sample data |
| Emergency contacts | Red phone button that opens numbers to call with one tap. | Button only, not wired |
| Early warning alerts | Bottom panel with weather, official warnings and summarized internet updates. | Screen only, sample data |
| Incident report | Report an incident with a location from GPS or a point on the map. | Form works, saved on the phone only, not sent to a server |
| AI chatbot | One question in, one short answer out, from a checked guide only. No follow-ups and no live place status. Every answer ends with "AI-generated. Follow official advisories first." | Button only. Backend answers are stubbed |
| Help requests and hazard reports (replaces the incident report form) | "I need help" goes to responders only and is never shown on the map. A hazard report shows to nearby people as an approximate spot, "Unconfirmed" after 3 reports from 3 phones, "Verified" once an admin checks it. | Working (backend only, no screens yet). The old incident form above still saves on the phone only |
| Responder side | Reports list, map, places and a resolve step. Phone and computer layouts. | The endpoints work on the server: reports (list, take, resolve, mark false, verify), places (approve, reject, remove, restore) and status corrections (override, capacity). Planned: the screens |
| Staff accounts and sign in | Responder and Super admin accounts, sign in and out, lock after 5 wrong tries, sign out after 30 minutes idle, role checks on the server. | Working (backend only, no screens yet) |
| Audit log | Every admin action is recorded with the person's name. A Super admin reads it. | Working (backend only, no screens yet) |
| Super admin side | Everything a responder does, plus advisories, emergency numbers, the chatbot guide, accounts, the audit log and permanent delete. Computer only. | Accounts, audit log and permanent delete work on the server. Planned: screens, advisories, emergency numbers, chatbot guide |
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
"Evacuation centers: add, approve, remove, restore" below), or add one to
`backend/data/manual_facilities.json` (see "Updating facility data").

**Who reported it, and corrections by staff:** every status update records its
source. A normal update is `"source": "user"` (`"Reported by a user"`). When a
signed-in responder or Super admin sends the same update with their token
(`Authorization: Bearer ...`), it is `"source": "official"` (`"Confirmed by
official"`) with their name kept on the row, and it is not slowed down by the
per-place cooldown. Both fields are inside `status` in `GET /api/facilities`
(new fields only, nothing was renamed). A wrong or expired token counts as no
sign-in: the update is saved as a user report.

Staff can also correct a place (every one of these is audited with their name,
and none of them erases anything; each adds a row to the status history):

| Action | Endpoint | Who |
| --- | --- | --- |
| Override the latest status | `POST /api/responder/facilities/{id}/status-override` | Responder, Super admin |
| Correct the maximum capacity | `POST /api/responder/facilities/{id}/capacity-correction` | Responder, Super admin |
| Full history with staff names | `GET /api/responder/facilities/{id}/status-history` | Responder, Super admin |

An override takes the same fields as a user report (and the same "at capacity
means full" rule) plus an optional `reason`. A capacity correction needs a status
to sit on; it never makes an old status look fresh, and it is not a status in the
public history. After an official has set a center's capacity, a user report
cannot change it (the form always sends the number, so the server keeps the
official one and says so in `message`); a later official change can.

**Facility IDs:** each facility gets a permanent key (its OpenStreetMap
reference, type + name for manual entries, or `user:<n>` for centers added in
the app). On every start the backend matches the data file to the database by
that key instead of rebuilding the table, so a place keeps its ID and its
history when the file is re-fetched or reordered. A place that disappears from
the file is removed together with its history. Centers added in the app live in
their own table, so re-fetching the file never removes them.

## Evacuation centers: add, approve, remove, restore

**Add a center (anyone, no login)**

1. Tap **Add evacuation center** (bottom left), then tap the map to place the pin.
   Drag the pin to adjust it, then tap **Continue**.
2. Fill in the form: name, type (Permanent or Temporary) and **maximum capacity**
   are required; barangay, address, contact number and a short note are optional.
   The location must be inside Batangas City (a rough box set in
   `BATANGAS_CITY_BBOX` in `config.py`). Tap **Save evacuation center**.
3. The place starts as **pending** (`"approval_status": "pending"`). Only the phone
   that sent it sees it (the phone ID is the `X-Phone-Id` header, the same one the
   reports use, stored hashed). Nobody else gets it in `/api/facilities`, and nobody
   else can read or update it by guessing its number. It shows "No status yet" and
   "Capacity: N people" until someone reports.
4. A responder or Super admin approves it (everybody sees it from then on) or
   rejects it (nobody but staff sees it). Staff see a list of pending places with
   the exact details.

A place with the same name within 30 m of an existing one (an approved one, one
still pending, or one that was removed) is **not refused**: it is flagged, and the
staff list shows `possible_duplicate` with the other place, its distance and
whether it was removed. The same phone cannot send the same place twice while it
waits (409), and one phone can have at most 5 places waiting
(`PENDING_PLACES_PER_PHONE`).

**Hide on this phone** happens in the browser only. The server never hears about
it and it never hides a center for anybody else. Hospitals and clinics cannot be
hidden. Nothing a user does can remove a center for everyone.

**Remove for everyone (responder or Super admin):** an approved evacuation center
is hidden from the map for all users. Its data and status history are kept for
**30 days** (`REMOVED_CENTERS_KEEP_DAYS` in `config.py`, or the environment
variable of the same name). A responder or Super admin can restore it until then.
After 30 days it is **deleted together with its history** by the purge (below).
Only a Super admin can delete one sooner. Hospitals and clinics cannot be removed.

| Action | Endpoint | Who |
| --- | --- | --- |
| Add (starts pending) | `POST /api/evacuation-centers` | Anyone (header `X-Phone-Id`, optional) |
| List places waiting for approval | `GET /api/responder/places` (`?status=rejected` for rejected ones) | Responder, Super admin |
| Approve | `POST /api/responder/places/{id}/approve` | Responder, Super admin |
| Reject (optional `reason`) | `POST /api/responder/places/{id}/reject` | Responder, Super admin |
| Remove for everyone | `DELETE /api/evacuation-centers/{id}` | Responder, Super admin |
| List removed centers (with the day each is deleted) | `GET /api/evacuation-centers/removed` | Responder, Super admin |
| Restore | `POST /api/evacuation-centers/{id}/restore` | Responder, Super admin |
| Delete for good, now (a removed center or a rejected place) | `DELETE /api/admin/places/{id}` | Super admin |

Every approve, reject, remove, restore and delete is written to the audit log with
the person's name. Adding is written to `action_log` with a hashed IP address
(never the address itself) and limited to 10 adds per IP and per phone per 10
minutes (`MANAGE_MAX_ACTIONS`, `MANAGE_WINDOW_SECONDS`).

**The purge:** `purge_removed_centers` deletes every center that has been removed
for more than 30 days, with its status history, its removal history and its old
action-log lines. Places that were rejected more than 30 days ago go too. A center
that was restored is never touched, and pending places are not purged. It runs
when the backend starts and from a script (run it from the `backend` folder, for
example once a day):

```
py scripts/purge_removed_centers.py
```

A center that comes from a data file (OpenStreetMap or `manual_facilities.json`)
would be read from the file again on the next start, so its key is also written to
the `deleted_facilities` table and skipped. To bring such a center back, delete
its row from that table. The audit log is never purged.

**Older databases** are upgraded by themselves on the next start (new columns on
`user_evacuation_centers`, `facility_removals` and `status_updates`, new table
`deleted_facilities`): centers that were already on the map become "approved",
older status updates become user reports, nothing is lost.

**Try it** (backend and frontend running; start the backend with
`STATUS_COOLDOWN_SECONDS=0` so repeated updates are not delayed; sign in with
`POST /api/auth/sign-in` for the staff steps):

1. Add a center with capacity 100. You see it, with a dashed blue ring once the
   screens show `approval_status`; open the map from another browser and you do not.
2. As a responder, `GET /api/responder/places`, then approve it. Now everybody sees it.
3. Update status: **Almost full**, people inside 85. Orange pin, orange bar,
   "85 / 100 people", "15 spaces left".
4. Update status: **Open**, people inside 100. The page shows the "saved as
   full" message; the pin and bar turn red and the status is **Full**.
5. As a responder, remove it, restart the backend, refresh: it stays hidden.
   `GET /api/evacuation-centers/removed` lists it with `days_left`; restore it.

## Staff accounts and roles

Two roles. A **Super admin** can do everything a **responder** can, plus manage
accounts and read the audit log. The public has no account, and there is no
public sign-up. Permissions are checked on the server (`backend/app/auth.py`),
not only hidden in the screens.

**Create the first Super admin** (once, from the backend folder):

```
cd backend
py scripts/create_super_admin.py
```

It asks for a name and a password (not shown while you type, at least 8
characters). It refuses to run when a Super admin already exists. The Super
admin then signs in and creates the other accounts. The script uses the same
database as the backend (`typhoon.db` in the folder you run it from).

**How sign in works.** `POST /api/auth/sign-in` with a name and password returns
a `token`. Send it on every later request as `Authorization: Bearer <token>`.
The name is not case sensitive. Wrong name and wrong password give the same
message. After **5 wrong tries in a row** the account is locked for **15
minutes** (even the right password is refused until then, unless a Super admin
unlocks it). A session ends after **30 minutes without use**; each request
moves the timer forward.

| Method | Path | Who | What it does |
| --- | --- | --- | --- |
| POST | `/api/auth/sign-in` | Anyone with an account | Sign in, returns the token |
| POST | `/api/auth/sign-out` | Signed in | End this sign-in (safe to call twice) |
| GET | `/api/me` | Responder, Super admin | Who is signed in and their role |
| GET | `/api/admin/users` | Super admin | List accounts and whether they are locked |
| POST | `/api/admin/users` | Super admin | Create an account (`name`, `password`, `role`) |
| POST | `/api/admin/users/{id}/lock` | Super admin | Lock until unlocked; signs the person out |
| POST | `/api/admin/users/{id}/unlock` | Super admin | Unlock (also clears a wrong-tries lock) |
| DELETE | `/api/admin/users/{id}` | Super admin | Remove the account (its audit entries stay) |
| GET | `/api/admin/audit-log` | Super admin | Newest first. `limit`, `before_id`, `action`, `actor` |

No token or an expired one gives 401. A signed-in responder on a Super admin
route gets 403. You cannot lock or remove your own account. The existing map,
status and evacuation center endpoints still need no sign-in; they get their
role checks in the later parts.

**Audit log.** Every admin action is saved with the person's name, their role,
what it was done to and the time (UTC). Sign in, sign out and automatic locks
are logged too. Passwords and tokens are never logged, the IP is stored hashed
only, and entries are never edited or deleted. Later parts add an entry from
their admin routes with one call:

```python
from . import audit
audit.record(db, user, "report.resolve", target="report:12", detail={"note": "Team sent"}, request=request)
db.commit()   # commit together with the change itself
```

**Security details.** Passwords are stored hashed with scrypt. A sign-in token
is random and only its hash is stored. Sign-in is also limited per IP (20
attempts per 10 minutes).

**Settings to confirm** (`backend/app/config.py`, each can also be set with an
environment variable):

- `STAFF_IDLE_MINUTES`: 30 (`STAFF_IDLE_MINUTES`)
- `SIGNIN_MAX_WRONG_TRIES`: 5 (`SIGNIN_MAX_WRONG_TRIES`)
- `SIGNIN_LOCK_MINUTES`: 15 (`SIGNIN_LOCK_MINUTES`)
- `SIGNIN_IP_MAX_ATTEMPTS` / `SIGNIN_IP_WINDOW_SECONDS`: 20 per IP per 10 minutes
- `MIN_PASSWORD_LENGTH`: 8

**Run the checks** (needs `pip install -r requirements-dev.txt` once):

```
cd backend
py tests/test_accounts.py
```

It uses its own temporary database. It checks lockout and unlock, the idle
timeout, a responder blocked from Super admin routes, no token blocked, and the
audit entries.

**Not built yet:** the sign-in screens, changing your own password, and a
password reset by a Super admin. Until then a Super admin sets each person's
first password, and a forgotten password means removing the account and
creating it again.

## Help requests and hazard reports

Two kinds of report, sent without an account. There are **no photos and no name
field**. A report has a `category`, a location and a short optional `note`; a
help request also has a required `contact` (a phone number the responders can
call) and optional `people` and `can_move`. The exact location and the contact are
visible only to responders and Super admins (`backend/app/report_service.py`).

| Field | Help request | Hazard |
| --- | --- | --- |
| `kind` | `"help"` | `"hazard"` |
| `category` | Required, 1 to 40 characters: what the need is (for example "Trapped") | Required, 1 to 40 characters: what the hazard is (for example "Flooded road") |
| `latitude`, `longitude` | Required, inside Batangas City | Required, inside Batangas City |
| `contact` | **Required** | Optional |
| `note` | Optional, up to 140 characters | Optional, up to 140 characters |
| `people` | Optional whole number, 1 to 999 | Refused (422) |
| `can_move` | Optional: `"yes"`, `"no"` or `"unsure"` | Refused (422) |

Any other field (a name, a photo) is refused with 422. The incident form in the
frontend sends its type as `kind`, its text as `details`, `people` and `canMove`;
the API names them `category`, `note`, `people` and `can_move`, and its own `kind`
is the form's help / hazard mode.

- **"I need help"** (`"kind": "help"`) goes to responders only and is never
  public. The sender sees only their own reports and a status: **New**, **Being
  handled** or **Resolved**.
- **Hazard** (`"kind": "hazard"`): people within **1 km** see an approximate spot
  with no details. It shows as **Unconfirmed** once **3 different phones**
  reported it, and as **Verified** once a responder or Super admin verifies it.
  Before either, a hazard is visible only to responders and to the phones that
  sent it.

**Phone ID.** The browser makes a random value (16 to 64 letters, digits, `-` or
`_`; a UUID works) and sends it on every request as the header `X-Phone-Id`. It
is used for "my reports". It is **not proof of identity**, and clearing browser
data gives the phone a new one. Only its SHA-256 hash is stored.

| Method | Path | Who | What it does |
| --- | --- | --- | --- |
| POST | `/api/reports` | Public (`X-Phone-Id`) | Send a report (fields above). 201 (200 if this phone already reported this hazard) |
| GET | `/api/reports/mine` | Public (`X-Phone-Id`) | This phone's own reports, newest first: its own location, its `category` and a status. No contact, no people, no handler, no reason |
| GET | `/api/hazards/nearby` | Public | `latitude`, `longitude` in the query. Unconfirmed or Verified hazards within the near-me range: an approximate spot, a status and the `category`, nothing else |
| GET | `/api/responder/reports` | Responder, Super admin | The list for the responder screens (poll about every 10 seconds). `include_closed`, `kind` filters |
| POST | `/api/responder/reports/{id}/take` | Responder, Super admin | New to Being handled. 409 if another person already has it |
| POST | `/api/responder/reports/{id}/resolve` | Responder, Super admin | Needs `what_was_done` |
| POST | `/api/responder/reports/{id}/mark-false` | Responder, Super admin | Needs a `reason` |
| POST | `/api/responder/reports/{id}/verify` | Responder, Super admin | Hazards only. The public then sees it as Verified |

Responder endpoints use the sign-in token from the accounts section
(`Authorization: Bearer <token>`). No token gives 401. Take, resolve, mark false
and verify are each written to the audit log with the person's name
(`report.take`, `report.resolve`, `report.mark_false`, `report.verify`).

**Responder list.** Each call returns `refresh_seconds` (10), `new_help_count`
and `has_new_help` (true while any help request is still New: show the red
"Needs help" alert), `latest_report_id`, and `items`. Help requests nobody has
taken come first, longest waiting first. An item has the exact `latitude` and
`longitude`, `category` (and `categories`, every different category sent for a
hazard), `people` and `can_move` (help requests only, empty on hazards),
`contacts` and `notes`, who took or closed it, and for a hazard its
`hazard_state` (`pending`, `unconfirmed`, `verified`) and how many different
`phones` sent it. Use an item's `id` in the action endpoints.

**How hazards are grouped.** A hazard report within **100 m** of the first report
of an open hazard counts as the same hazard, whatever its category. The public and
the responder item show the category of the first report. One phone counts once per hazard
(sending it again returns the earlier report). Take, resolve, mark false and
verify on a hazard apply to all its reports. A resolved or false hazard is closed:
a new report at that place starts a new hazard.

**The approximate spot.** The public sees the middle of a 250 m square around the
real spot. The same hazard always gives the same spot, and the near-me distance is
measured to that spot, not to the real one. Your position in `/api/hazards/nearby`
is used for the answer only and is not stored.

**False reports.** After 3 reports from one phone are marked false, that phone is
blocked from sending reports (403, the message says to call 911 in an emergency).
It can still read its own reports. This slows casual pranks only. Marking a hazard
false counts as one false report for each phone in it. The count is taken over the
reports still kept, and a block is kept after the reports are deleted. A report
marked false shows to its sender as "Resolved", without the reason.

**Limits.** Sending a report is limited per phone (a 30 second cooldown per kind,
6 an hour) and per IP (30 an hour), with the same sliding-window style as the other
limits (`backend/app/rate_limit.py`). Reading "my reports" and nearby hazards is
limited to 60 a minute per IP and per phone. IP addresses are stored hashed only.

**Deleting old reports.** Reports are deleted 30 days after they were sent. This
runs each time the server starts, and by script:

```
cd backend
py scripts/purge_reports.py
```

A server that stays running does not purge by itself until the next start, so run
the script now and then (for example once a day) if it runs for weeks.

**Settings to confirm** (`backend/app/config.py`, each can also be set with an
environment variable of the same name):

| Setting | Value |
| --- | --- |
| `REPORTS_KEEP_DAYS` | 30 |
| `REMOVED_CENTERS_KEEP_DAYS` | 30 (removed centers are deleted with their history after this many days) |
| `PENDING_PLACES_PER_PHONE` | 5 |
| `HAZARD_UNCONFIRMED_PHONES` | 3 |
| `FALSE_REPORTS_BEFORE_BLOCK` | 3 |
| `NEAR_ME_KM` | 1 |
| `RESPONDER_REFRESH_SECONDS` | 10 |
| `HAZARD_MERGE_METERS` | 100 |
| `HAZARD_APPROX_METERS` | 250 |
| `REPORT_PHONE_COOLDOWN_SECONDS` / `REPORT_PHONE_MAX` / `REPORT_IP_MAX` / `REPORT_WINDOW_SECONDS` | 30 / 6 / 30 / 3600 |
| `REPORT_READ_MAX` / `REPORT_READ_WINDOW_SECONDS` | 60 / 60 |

**Run the checks** (needs `pip install -r requirements-dev.txt` once):

```
cd backend
py tests/test_reports.py
```

It uses its own temporary database. It checks that a help request is never
public, that a hazard is hidden beyond 1 km, that 3 different phones (not 3 reports
from one phone) make it Unconfirmed, Verified, the false report block, the purge,
the limits and the role checks.

**Checking the places rules (update 10):**

```
cd backend
py tests/test_places.py
```

It checks that a pending place is seen only by its sender, approve, reject, that
a user cannot remove or restore for everyone, admin removal and restore, the
30-day purge (also from the script and on start), "Reported by a user" versus
"Confirmed by official", that an override and a capacity correction keep the
history and record the name, and upgrading an older database. To run all three
test files one after the other: `py tests/run_all.py` (each file needs its own
process, so do not run them in one `pytest` call).

**Older databases.** The `category`, `people` and `can_move` columns are added to
an existing `reports` table automatically when the server starts (and when
`scripts/purge_reports.py` runs). Reports sent before that keep working and show
an empty category.

**Not built yet:** the report screens and the responder screens (the frontend
still has the old incident form), and a way for a Super admin to lift a phone
block.

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
│   ├── scripts/                # create_super_admin.py (first Super admin), purge_reports.py, purge_removed_centers.py, fetch/backdate helpers
│   ├── tests/                  # test_accounts.py, test_reports.py, test_places.py, run_all.py (runs them all)
│   └── app/
│       ├── main.py             # FastAPI app, loads facilities, /api/facilities and the status routes
│       ├── routes.py           # API routes (weather and AI routes are stubs)
│       ├── evac_routes.py      # Add a place (public, starts pending); remove / restore / removed list (staff)
│       ├── evac_service.py     # Center keys, duplicate check, what is hidden from whom, action log
│       ├── place_routes.py     # Staff: pending list, approve, reject, delete for good, status override, capacity correction
│       ├── place_service.py    # Approval and removal rules, 30-day purge, upgrade of older databases
│       ├── status_admin.py     # Status override and capacity correction (history rows, audited)
│       ├── models.py           # SQL tables (facilities, status updates, user centers, removals, action log, users, sessions, audit log, reports, blocked phones)
│       ├── schemas.py          # Request/response shapes and status rules
│       ├── config.py           # 6-hour outdated rule, rate limits, city area, duplicate distance, sign-in rules
│       ├── rate_limit.py       # Per-IP and per-phone limits (status updates, add/remove/restore, sign in, reports)
│       ├── account_routes.py   # Sign in/out, /api/me, accounts, audit log endpoints
│       ├── account_schemas.py  # Request/response shapes for the above
│       ├── accounts.py         # Create, sign in, sessions, lock/unlock/remove
│       ├── auth.py             # Role check for admin routes (require_responder, require_super_admin, optional_staff)
│       ├── audit.py            # audit.record(...) helper for admin actions
│       ├── security.py         # Password hashing, token hashing
│       ├── report_routes.py    # Send a report, my reports, nearby hazards, responder list and actions
│       ├── report_schemas.py   # Request/response shapes for reports
│       ├── report_service.py   # Report rules: hazard groups, approximate spot, false reports, purge
│       ├── status_service.py   # Latest status / history, source of an update, capacity rule (automatic "Full")
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
- Connect the frontend to the places rules (backend is ready): send the `X-Phone-Id`
  header with `/api/facilities`, the status update and the add-place call (a pending
  place disappears from its sender's map after a reload without it); show
  `approval_status` (dashed blue ring while pending) and `status.source_label`; the
  approve / reject screens and the "Removed centers" list for staff. `RemovedCenters.tsx`
  is not used by any page and would now need a staff sign-in.
- Connect the report screens to the report endpoints (the backend is ready, the old incident form still saves on the phone only).
- Chatbot that answers from a checked guide only, with the fixed "AI-generated.
  Follow official advisories first." line.
- Clean-up to match "online only": the offline code in `_later/` and the PWA
  install settings in `frontend/vite.config.ts` are left from an earlier plan
  and should be removed.
- Add distinct pin colors for hospitals, clinics and evacuation centers.
