# SILONG redesign: rules, roles and build order

This file describes the redesign: the rules, and what is **not built yet**. The
README describes what the code does today. When a part here is built, move it
into the README and mark it "Working" here.

## Build status

| Part | What | Status |
| --- | --- | --- |
| 1 | Staff accounts, roles, sign in, audit log | **Working** on the server (no screens yet) |
| 2, 2b | Help requests and hazard reports, the two visibility kinds, responder actions, purge of old reports | **Working** on the server (no screens yet) |
| 3 | Places rules (pending, approve, reject, admin removal, 30-day purge, permanent delete), status source, overrides and capacity corrections | **Working** on the server (no screens yet) |
| 4 | Advisories, emergency numbers, chatbot guide | Not built |
| Frontend | Responder and Super admin screens, the phone ID on every public call, labels and pin looks for pending places and "Confirmed by official" | Not built |
| After Nov 20 | Two-step sign in | Planned |

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
| Responder | Yes | Phone and computer | See and handle reports, verify hazards, approve or reject added places, correct statuses |
| Super admin | Yes | Computer only | Everything a responder can do, plus advisories, emergency numbers, chatbot guide, accounts, audit log, permanent delete |

There is no public sign-up. A Super admin creates, locks and removes accounts.
The first Super admin is created with a setup script. Every admin action is
written to the audit log with the person's name. Permissions are checked on the
server, not only hidden in the screens.

The phone ID used for "my reports" and "hidden on this phone" is a random value
kept in the browser. It is not proof of who someone is, and clearing browser
data resets it.

## Rules by feature

### Map and places (boards 1, 2, 14-19) (working on the server)
- All pins show automatically. A pin shows the type as a letter plus a shape.
- Pin looks: hollow = no status yet, dashed and dim = update older than 6 hours,
  small blue ring = added through the app, dashed blue = waiting for approval
  (only the sender sees it).
- Users can add a place. It is visible only to them until a responder or Super
  admin approves it. Possible duplicates (same name within 30 m) are flagged.
- Hiding a center ("Hide on this phone") only affects that phone and can be
  undone from the menu. Hospitals and clinics cannot be hidden.
- Admin removal hides a center for everyone. It is kept 30 days, then deleted
  with its history. Only a Super admin can delete one sooner.

How the server does this (choices the design left open):
- A pending place is tied to the hashed phone ID (`X-Phone-Id`), like "my reports".
  Without the header the place is still saved as pending, but only staff will ever
  see it. The sender's phone sees it in `/api/facilities` as `approval_status: pending`.
- A possible duplicate does not stop a place from being added. It is flagged, and the
  responder sees the other place (approved, pending or removed) with its distance.
- A responder or Super admin can approve or reject. A rejection can be undone by
  approving. A place already on the map is removed, not rejected. Rejected places are
  deleted after the same 30 days.
- A responder or Super admin can remove and restore. A Super admin can delete a removed
  center or a rejected place at once. A center from a data file is noted in
  `deleted_facilities` so the next start does not read it again.
- At most 5 pending places per phone; adding is limited per IP and per phone.

### Status and capacity (boards 3, 16, 17) (working on the server)
- Status words and pin colors are in the README.
- A user update is shown as "Reported by a user". An update by a responder or
  Super admin is shown as "Confirmed by official".
- Admins can override the latest status or correct the capacity. An override is
  added to the history. Nothing is erased, and the person's name is recorded.

How the server does this (choices the design left open):
- "Official" means the request carries a valid responder or Super admin token. A
  wrong or expired token counts as a user. Officials are not held back by the
  per-place cooldown.
- A capacity correction is a history row that copies the status it sits on. It is not
  shown as a status and does not make an old status look fresh.
- After an official sets a center's capacity, a user's report cannot change it (the
  form always sends the field). A later official change can.
- The public never gets a staff name. Staff read it in the full history.

### Help requests and hazard reports (boards 5, 21, 22, 30-35, 38, 39) (working on the server)
- "I need help": goes to responders only. Never shown on the map. The sender
  sees their own pin and a status: New, Being handled, Resolved.
- Hazard: shown to people within the nearby range as an approximate spot with
  no details. It shows as "Unconfirmed" after 3 reports from 3 different phones,
  and as "Verified" once a responder or Super admin verifies it.
- Responder actions: Take it, Call, Navigate, Resolve (asks what was done),
  Mark false (asks for a reason).
- A new "Needs help" report shows a red alert on the responder screens. The
  screens refresh about every 10 seconds. The site cannot text or page anyone.
- Reports no longer have photos or a name field. Exact location and contact
  details are visible only to responders and Super admins.
- Reports are deleted after a set number of days.
- The site is not a replacement for calling 911 and says so.

### Weather, warnings and contacts (boards 4, 6, 23, 27)
- Weather comes from Open-Meteo and is cached. If it fails, the last good
  forecast stays with its time.
- Advisories are posted by hand by a Super admin and can be pinned. Only listed
  sources count as "official". Automatic fetching of warnings is added only
  where a reliable source exists.
- Emergency numbers are edited in the app by a Super admin. Only 911 is filled
  in until the Batangas City CDRRMO confirms the others.

### Chatbot (boards 9-13, 28, 42)
- One question in, one answer out. No follow-ups and no history. A new question
  starts fresh.
- Answers come from the checked guide only. The bot matches the meaning of the
  question to a guide entry. If nothing fits, it says it does not know and the
  Call 911 strip stays visible. No live place status, no map links.
- Every answer ends with: "AI-generated. Follow official advisories first."
- "Report a wrong answer" sends the question and answer to the Super admin.
  A Super admin edits the guide.

### Errors and empty states (board 41)
Location off, map did not load, no search results, can't connect (online only),
and signed out after being idle.

## Security basics (accounts, role checks, limits, hashing and the false-report block are working)
- Passwords are stored hashed. After 5 wrong tries, sign in is locked for 15
  minutes. Staff sessions sign out after 30 minutes without use.
- Admin routes check the role on the server. Users can only send status, report
  and suggestion data, never a place's name, address or phone number directly.
- Per-IP and per-phone limits and cooldowns on every public action. IP
  addresses are stored hashed only.
- After 3 false reports from one phone, that phone is blocked from sending
  reports. This slows casual pranks only. Admin verification is the real
  safeguard.
- Keys live in `.env`, never in the repository.
- Two-step sign in is planned after Nov 20.

## Settings to confirm
Each should live in `backend/app/config.py` and be changeable with an
environment variable.

| Setting | Planned value |
| --- | --- |
| Removed centers kept before permanent delete | 30 days (`REMOVED_CENTERS_KEEP_DAYS`, working) |
| Reports kept before deletion | 30 days (`REPORTS_KEEP_DAYS`, working) |
| Phones needed for a hazard to show as Unconfirmed | 3 |
| False reports before a phone is blocked | 3 |
| "Near me" range for hazard reports | 1 km |
| Staff idle sign out | 30 minutes |
| Wrong sign-in tries before lock | 5 (locked 15 minutes) |
| Responder screen refresh | about 10 seconds |

## Build order and split
Two people: one on the backend, one on the frontend.

1. **Nov 12:** agree the data fields and endpoints together (statuses, places,
   reports, roles, sign in). This is the only step that needs both of you.
2. **Nov 12-15:** backend builds sign in, roles, audit log, status and approval
   rules, hide and removal rules, reports and the two visibility kinds, and the
   admin endpoints (**done** on the server: parts 1, 2, 2b and 3). Frontend
   applies the layout, builds the user screens, then the responder phone screens
   against fake data.
3. **Nov 16-17:** connect both sides. Then weather and advisories, emergency
   numbers, and the chatbot guide editor.
4. **Nov 18-19:** test on the real phone, check every role's permissions, fix
   bugs.
5. **Nov 20:** buffer.

If time runs short, shrink the last items (automatic warnings, the guide
editor). Keep the security rules and the status rules.

## Testing on a phone
GPS only works on a secure page. `localhost` counts as secure, but
`http://192.168.x.x` does not. Connect the phone by USB and forward the port so
the phone opens `localhost`, or use local HTTPS (for example with mkcert).

## Not in this version
- A Filipino language option.
- A tablet layout.
- Photo upload on reports.
- Offline mode or installing the site on the home screen.
