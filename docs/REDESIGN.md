# SILONG redesign: rules, roles and build order

> **One role: Admin.** There is only one role, Admin, as in the admin console design (the design notes that came with the staff console mockup). Every Admin sees every screen and can do every action. The old `/api/responder/*` routes are `/api/admin/*`. Screens for Admins are described in [`ADMIN_FRONTEND_HANDOFF.md`](ADMIN_FRONTEND_HANDOFF.md).

This file describes the redesign: the rules, and what is **not built yet**. The
README describes what the code does today. When a part here is built, move it
into the README and mark it "Working" here.

## Build status

| Part | What | Status |
| --- | --- | --- |
| 1 | Admin accounts (one role), sign in, audit log | **Working** on the server (no screens yet) |
| 2, 2b | Help requests and hazard reports, the two visibility kinds, Admin actions, purge of old reports | **Working** on the server (no screens yet) |
| 3 | Places rules (pending, approve, reject, admin removal, 30-day purge, permanent delete), status source, overrides and capacity corrections | **Working** on the server (no screens yet) |
| 4 | Weather, advisories, emergency numbers | **Working** on the server (no screens yet) |
| 5 | Operations: `.env` loading, change and reset password, unblock phones, edit place details, audit-log filters, scheduled cleanup, demo data script, `docs/API.md` | **Working** on the server (no screens yet) |
| 4 | Chatbot | **Placeholder, AI not connected** (`POST /api/chat` gives a fixed answer). The checked guide, the guide editor and "Report a wrong answer" are not built |
| Frontend | The admin console (a separate frontend: desktop full, phone simple), the phone ID on every public call, labels and pin looks for pending places and "Confirmed by official" | Not built |
| After Nov 20 | Two-step sign in | Planned |

Frontend checklist: [`FRONTEND_TODO.md`](FRONTEND_TODO.md).

The sections below say "(working)" where the server already follows them. The
"Settings to confirm" table says which settings exist in `config.py`.

The screens are in the design canvas "SILONG Revised Layout" (43 boards).
Board numbers below point to it.

Target: **Nov 20, 2026** as a safe margin. It can slip. SILONG is a project
site that runs on localhost; nothing is deployed.

## Roles

| Role | Account | Where | What they can do |
| --- | --- | --- | --- |
| User | None | Phone (mobile first) | See the map, update a status, add or hide a place on their own phone, send reports, ask the chatbot |
| Admin | Yes | Computer (full) and phone (simple) | Everything: see and handle reports, verify hazards, approve, edit or reject added places, correct statuses and capacity, remove, restore or delete centers, post and pin advisories, manage official sources, edit emergency numbers, edit the chatbot guide (planned), create, lock, unlock, reset the password of and remove Admin accounts, read the audit log, unblock phones |

There is no public sign-up, and no locked tabs or "Super admin only" labels: every
Admin sees every screen. An Admin creates, locks and removes Admin accounts. The first
Admin is created with a setup script (`scripts/create_admin.py`). Every Admin action is
written to the audit log with the person's name. Permissions are checked on the
server, not only hidden in the screens.

The admin console lives at its own link, apart from the user site (two frontends, one
backend; see "Two sites, one backend" below). The user site does not point to it.

The phone ID used for "my reports" and "hidden on this phone" is a random value
kept in the browser. It is not proof of who someone is, and clearing browser
data resets it.

## Rules by feature

### Map and places (boards 1, 2, 14-19) (working on the server)
- All pins show automatically. A pin shows the type as a letter plus a shape.
- Pin looks: hollow = no status yet, dashed and dim = update older than 6 hours,
  small blue ring = added through the app, dashed blue = waiting for approval
  (only the sender sees it).
- Users can add a place. It is visible only to them until an Admin approves it. Possible duplicates (same name within 30 m) are flagged.
- Hiding a center ("Hide on this phone") only affects that phone and can be
  undone from the menu. Hospitals and clinics cannot be hidden.
- Admin removal hides a center for everyone. It is kept 30 days, then deleted
  with its history. An Admin can delete one sooner ("Delete now", the name typed to confirm).

How the server does this (choices the design left open):
- A pending place is tied to the hashed phone ID (`X-Phone-Id`), like "my reports".
  Without the header the place is still saved as pending, but only Admins will ever
  see it. The sender's phone sees it in `/api/facilities` as `approval_status: pending`.
- A possible duplicate does not stop a place from being added. It is flagged, and the
  Admin sees the other place (approved, pending or removed) with its distance.
- An Admin can approve or reject. A rejection can be undone by
  approving. A place already on the map is removed, not rejected. Rejected places are
  deleted after the same 30 days.
- An Admin can remove and restore, and can delete a removed
  center or a rejected place at once. A center from a data file is noted in
  `deleted_facilities` so the next start does not read it again.
- At most 5 pending places per phone; adding is limited per IP and per phone.

### Status and capacity (boards 3, 16, 17) (working on the server)
- Status words and pin colors are in the README.
- A user update is shown as "Reported by a user". An update by an Admin is shown as
  "Confirmed by official".
- Admins can override the latest status or correct the capacity. An override is
  added to the history. Nothing is erased, and the person's name is recorded.

How the server does this (choices the design left open):
- "Official" means the request carries a valid Admin token. A
  wrong or expired token counts as a user. Officials are not held back by the
  per-place cooldown.
- A capacity correction is a history row that copies the status it sits on. It is not
  shown as a status and does not make an old status look fresh.
- After an official sets a center's capacity, a user's report cannot change it (the
  form always sends the field). A later official change can.
- The public never gets an Admin's name. Admins read it in the full history.

### Help requests and hazard reports (boards 5, 21, 22, 30-35, 38, 39) (working on the server)
- "I need help": goes to Admins only. Never shown on the map. The sender
  sees their own pin and a status: New, Being handled, Resolved.
- Hazard: shown to people within the nearby range as an approximate spot with
  no details. It shows as "Unconfirmed" after 3 reports from 3 different phones,
  and as "Verified" once an Admin verifies it.
- Admin actions: Take it, Call, Navigate, Resolve (asks what was done),
  Mark false (asks for a reason). Taking a report another Admin is handling asks first ("<name> is handling this. Take over?") and then reassigns it to you.
- A new "Needs help" report shows a red alert on the Admin screens. The
  screens refresh about every 10 seconds. The site cannot text or page anyone.
- Reports no longer have photos or a name field. Exact location and contact
  details are visible only to Admins.
- Reports are deleted after a set number of days.
- The site is not a replacement for calling 911 and says so.

### Weather, warnings and contacts (boards 4, 6, 23, 27) (working on the server)
- Weather comes from Open-Meteo and is cached. If it fails, the last good
  forecast stays with its time.
- Advisories are posted by hand by an Admin and can be pinned. Only listed
  sources count as "official". Automatic fetching of warnings is added only
  where a reliable source exists.
- Emergency numbers are edited in the app by an Admin. Only 911 is filled
  in until the Batangas City CDRRMO confirms the others.

How the server does this (choices the design left open):
- Weather is for one point in Batangas City, cached 10 minutes. A failed call serves the last
  good forecast with `is_stale` and the time it was received (a copy is kept in the database).
  With no good forecast ever, the answer is a plain 503. A reply with a missing number counts
  as failed; nothing is filled in. `cyclone` is always null (no reliable source).
- An advisory has a title, details, the organization that issued it, and a required link to the
  original (http or https). It is official when the organization is on the list in the
  `advisory_sources` table (PAGASA, NDRRMC, Batangas City CDRRMO at first), compared without case
  or extra spaces. An Admin edits the list. Pinned advisories come first, then newest first.
- Emergency numbers are one list in the database, shown in an Admin's order. Only 911 at first.
- Every change is audited with the person's name.

### Chatbot (boards 9-13, 28, 42) (placeholder, AI not connected)
- One question in, one answer out. No follow-ups and no history. A new question
  starts fresh.
- Answers come from the checked guide only. The bot matches the meaning of the
  question to a guide entry. If nothing fits, it says it does not know and the
  Call 911 strip stays visible. No live place status, no map links.
- Every answer ends with: "AI-generated. Follow official advisories first."
- "Report a wrong answer" sends the question and answer to an Admin.
  An Admin edits the guide.

Today the server has the placeholder only: `POST /api/chat` gives a fixed answer (Silo is not
available yet, call 911, follow official advisories) with the ending line. No guide, no AI, no key,
no cost, and nothing about the question or the person asking is stored. A future AI plugs in at one
place (`chat_service.py`); see "Plugging in an AI later" in the README. Not built: the guide table,
the guide editor and the wrong-answer report.

### Errors and empty states (board 41)
Location off, map did not load, no search results, can't connect (online only),
and signed out after being idle.

## Security basics (accounts, role checks, limits, hashing and the false-report block are working; the chat endpoint has a per-IP limit and a question length limit)
- Passwords are stored hashed. After 5 wrong tries, sign in is locked for 15
  minutes. Admin sessions sign out after 30 minutes without use ("You were signed out"; each request restarts the timer).
- Admin routes check the role on the server. Users can only send status, report
  and suggestion data, never a place's name, address or phone number directly.
- Per-IP and per-phone limits and cooldowns on every public action. IP
  addresses are stored hashed only.
- After 3 false reports from one phone, that phone is blocked from sending
  reports. This slows casual pranks only. Admin verification is the real
  safeguard. An Admin can unblock a phone (the count starts again), and
  `BLOCK_EXPIRES_DAYS` can end blocks by themselves (0 = never) (working).
- Changing your own password needs the current one; wrong tries are limited per
  person and per IP. An Admin resets a forgotten password (working).
- Old reports, removed centers, rejected places, idle sign-ins and expired blocks
  are deleted on a schedule while the server runs (working).
- Keys live in `.env`, never in the repository.
- Two-step sign in is planned after Nov 20.

## Settings to confirm
Each should live in `backend/app/config.py` and be changeable with an
environment variable.

| Setting | Planned value |
| --- | --- |
| Removed centers kept before permanent delete | 30 days (`REMOVED_CENTERS_KEEP_DAYS`, working) |
| Reports kept before deletion | 30 days (`REPORTS_KEEP_DAYS`, working) |
| Phone blocks end by themselves after | never (`BLOCK_EXPIRES_DAYS`, 0, working) |
| Scheduled cleanup | every 60 minutes (`PURGE_INTERVAL_MINUTES`, 0 = off, working) |
| Wrong current passwords when changing a password | 5 per person, 20 per IP, per 10 minutes (`PASSWORD_CHANGE_MAX_WRONG`, `PASSWORD_CHANGE_IP_MAX_WRONG`, `PASSWORD_CHANGE_WINDOW_SECONDS`, working) |
| Phones needed for a hazard to show as Unconfirmed | 3 |
| False reports before a phone is blocked | 3 |
| "Near me" range for hazard reports | 1 km |
| Admin idle sign out | 30 minutes (`STAFF_IDLE_MINUTES`) |
| Wrong sign-in tries before lock | 5 (locked 15 minutes) |
| Admin screen refresh | about 10 seconds (`RESPONDER_REFRESH_SECONDS`; the setting name is kept so existing `.env` files keep working) |
| Weather cache | 10 minutes (`WEATHER_CACHE_MINUTES`, working); wait 30 seconds after a failed call (`WEATHER_RETRY_SECONDS`) |
| Longest chatbot question | 200 characters (`CHAT_MAX_QUESTION_LENGTH`, working) |
| Chatbot questions per IP | 15 per 10 minutes (`CHAT_IP_MAX_QUESTIONS`, `CHAT_IP_WINDOW_SECONDS`, working) |
| Chatbot provider and its timeout | `placeholder`; 15 seconds for a future provider (`CHAT_PROVIDER`, `CHAT_TIMEOUT_SECONDS`, working) |

## Build order and split
Two people: one on the backend, one on the frontend.

1. **Nov 12:** agree the data fields and endpoints together (statuses, places,
   reports, roles, sign in). This is the only step that needs both of you.
2. **Nov 12-15:** backend builds sign in, roles, audit log, status and approval
   rules, hide and removal rules, reports and the two visibility kinds, and the
   admin endpoints (**done** on the server: parts 1, 2, 2b and 3). Frontend
   applies the layout, builds the user screens, then the Admin phone screens
   against fake data.
3. **Nov 16-17:** connect both sides. Then weather and advisories, emergency
   numbers (backend **done**: part 4), and the chatbot guide editor (not built).
4. **Nov 18-19:** test on the real phone, check every role's permissions, fix
   bugs.
5. **Nov 20:** buffer.

If time runs short, shrink the last items (automatic warnings, the guide
editor, connecting an AI). Keep the security rules and the status rules.

## Two sites, one backend
The admin console is a separate frontend with its own link. On localhost that means two
frontends and one backend:

| Part | Address | Who uses it |
| --- | --- | --- |
| Backend (FastAPI) | `http://127.0.0.1:8000` | Both sites. Same server, same database |
| User site | `http://localhost:5173` | Users |
| Admin console | `http://localhost:5174` | Admins |

- The two site ports are examples; any two free ports work if both are in `CORS_ORIGINS` (`backend/.env`).
  The backend answers a browser only for the listed origins (default: `localhost` and `127.0.0.1` on 5173 and 5174), so no
  other website can read data with an Admin's browser.
- Both frontends set `VITE_API_URL` the same way (default `http://127.0.0.1:8000/api`).
- Two ports are two origins: the user site cannot read the admin console's browser data, and the Admin token never sits in the user site.
- The admin console shares no pages, menu or routes with the user site. The user site has no admin link, button or text, and the admin sign-in has no link back to the public map.
- A separate link only hides the door. The sign-in and the server's token check keep users out (no token or an expired one is 401; an account locked or removed while its sign-in is still alive is 403).

## Testing on a phone
GPS only works on a secure page. `localhost` counts as secure, but
`http://192.168.x.x` does not. Connect the phone by USB and forward the ports
(5173, 5174 and 8000) so the phone opens `localhost`, or use local HTTPS (for example with mkcert).
Over Wi-Fi the phone opens the computer's address (for example `http://192.168.1.20:5173`): add that
origin to `CORS_ORIGINS` and restart the backend (README, "Testing on a phone over Wi-Fi"). GPS will not work on that page.

## Not in this version
- A Filipino language option.
- A tablet layout.
- Photo upload on reports.
- Offline mode or installing the site on the home screen.
- Texts or pages to Admins (the Admin screens refresh instead).
- Two-step sign in (planned after Nov 20).
