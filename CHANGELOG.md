# Change log

Short log of what changed in each update, newest first.

## Update 17 — Admin hand-off docs (docs only)
Documentation for the admin frontend developer and the move to one role in the docs. No code, test, path, field or answer changed.
- **New `docs/ADMIN_FRONTEND_HANDOFF.md`.** For every desktop screen (sign in, Live map, Places, Content, Chatbot, Accounts, Audit log, Blocked phones, Change password), every phone screen (Reports, Map, Places, Me, report detail, resolve sheet, new-help alert) and the shared behaviour ("You were signed out", lock after 5 wrong tries, sign-in rate limit, "Mark as false", "Delete for good"): the exact endpoints, query and body fields, response fields used, error codes and refresh rules. It states the take-over question ("<name> is handling this. Take over?"), that the Admin token must never be reachable from the user site or put in a URL, and that the sign-in has no link to the public map. Every screen or action the server does not support (chatbot guide, two-step sign in, texts or pages, advisory expiry, place names on reports, device and accuracy fields) is marked, and so is every endpoint with no designed screen.
- **Contradictions written down** (not fixed, no code changed): the admin console design says the backend allows any origin (since Update 16 only `CORS_ORIGINS`); polling keeps an Admin session alive, so "30 minutes without use" needs help from the screen; `Retry-After` cannot be read by the browser; `docs/API.md`'s intro still lists "already handled" under 409 and tells screens to read `Retry-After`.
- **Leftovers in the user site** listed with the change each needs (`HamburgerMenu.tsx`, `App.tsx`, `AdminSignInPage.tsx`, `TopBarNav.css`, `MenuPages.tsx`, `IncidentPanel.tsx`, `MapPage.tsx`). Not edited.
- **README.** One role, the two frontends and one backend with their ports, creating the first Admin, `CORS_ORIGINS` including testing from a phone over Wi-Fi, a "Run the tests" section, the new files in the project structure, and a few "staff" words changed to "Admin". The reference to a file that is not in the repository was replaced.
- **`docs/REDESIGN.md`.** Responder and Super admin replaced by Admin (roles table, rules, settings table); new "Two sites, one backend" section; the phone-testing note names the three ports and the Wi-Fi case.
- **`docs/FRONTEND_TODO.md`.** Responder and Super admin replaced by Admin; sections 5.2 and 5.3 merged into one "Admin console" section (now also covering `mine`, `release`, `since`, distance, `/api/admin/summary`, `/api/admin/me/activity`, contact settings and emergency number categories); 4.13 now removes the "Admin sign in" row and the `/admin` route from the user site; new 4.15 (support contact); stale lines fixed (CORS, support contact, take-over, hospital edit is 422).
- `docs/API.md` did not change (`py scripts/generate_api_doc.py --check` is up to date).

## Update 16 — Two-origin hardening (backend only)
Makes the two-frontend setup (user site 5173, admin console 5174, backend 8000) safe and proves it with tests. No path, method or
answer shape changed. The only behaviour change is CORS; the rest is new checks of things that already held.
- **CORS.** `main.py` allowed every origin (`"*"`). It now allows only the origins in `CORS_ORIGINS` (`backend/.env`, read in
  `config.py`, comma separated). Default: `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:5174`,
  `http://127.0.0.1:5174`. Not set or empty means the default. `*` works only if it is written in `CORS_ORIGINS`, and the backend
  logs a warning at start when it is. Allowed request headers are now `Authorization`, `X-Phone-Id` and `Content-Type` (before:
  all), allowed methods `GET HEAD POST PUT PATCH DELETE OPTIONS`; `X-Total-Count` is still exposed. Credentials stay off (the token
  is a header, not a cookie). Documented in `backend/.env.example`, README and `docs/API.md`.
- **Admin route sweep.** `test_accounts.py` found admin routes by reading six hand-listed router modules, so the four routes in
  `console_routes.py` and `settings_routes.py` (`/api/admin/summary`, `/api/admin/me/activity`, `/api/admin/contact-settings` GET
  and PATCH) were never checked for 401/403. It now reads every route of the app (`tests/route_helpers.py`), 44 admin routes instead
  of 40, and a new test checks that route list against the app's own OpenAPI list. New guard: a route under `/api/admin` without
  `require_admin` fails the test, by name. (The routes themselves were already protected.)
- **Public leak sweep.** New `tests/test_public_leaks.py`: seeded demo data (help requests with contacts, hazards, a pending place, a
  removed center, a report taken by an Admin, a blocked phone, Admin-written advisories and settings), every public GET called as no
  token, a phone ID, a wrong token, an expired Admin token and a locked Admin's token. It fails on a report contact, a phone ID or hash,
  an exact help or hazard coordinate, an Admin's name, the control-room number, an audit or internal field. It also checks the answers
  of the public routes that take an optional token (a wrong, expired or locked token counts as a user, never as an Admin). Nothing
  leaked; the sweep itself is tested against injected leaks.
- **Token handling.** New `tests/test_security.py`: the token is read only from the `Authorization` header (a query, a cookie or another
  header counts for nothing on any admin route; no route has a token parameter), it is not in the audit log, the audit-log answer or
  the server log, only its hash is stored, and sign-out, the idle limit, lock, removal, password reset and password change end the
  session on the server (the row is gone). Nothing needed fixing.
- Tests: `test_security.py` (17 checks), `test_public_leaks.py` (8), two new checks in `test_accounts.py` (route list complete, admin dependency guard) and the four routes added to its list. `docs/API.md` regenerated
  (a CORS paragraph in the introduction; no route changed).
- Not done: no frontend, CSS or chatbot changes. The admin console's own code is not in this repository.

## Update 15 — Takeover and the status filter (backend only)
Stops a report from getting stuck on an Admin who went offline, and adds the status filter the console design asks for. No path or
answer shape changed; the only new thing in an answer is the audit detail below.
- **Takeover.** `POST /api/admin/reports/{id}/take`: any Admin can take a report another Admin is handling; it is reassigned to the
  caller (a whole hazard group moves together). The audit entry `report.take` has `taken_over_from` (the previous Admin's name) in its
  detail. A second tap by the same Admin is still a no-op and logs nothing.
- **Release by anyone.** `POST /api/admin/reports/{id}/release`: any Admin can give an open report back to New, also one another Admin
  took. The audit entry `report.release` has `released_by` and `was_handled_by` in its detail. Already New: no-op, nothing logged.
- **Still 409:** only a closed report (resolved or marked false), for both take and release. The old "X is already handling this
  report" and "only they can release it" errors are gone.
- **Status filter.** `GET /api/admin/reports?status=new|handling|resolved|all` (anything else is 422). **`resolved` means every
  closed report, resolved and marked false**, the same grouping the sender sees and what `include_closed` already lists; **`all` is open
  and closed together**. Not given: open reports only, or everything with `include_closed`, exactly as before. When `status` is given it
  decides the statuses and `include_closed` adds nothing. It combines with `mine`, `kind`, `since` (only changed items, narrowed to the
  status) and `latitude`/`longitude`. `new_help_count`, `has_new_help` and `latest_report_id` still cover everything.
- **`handled_today`** (`GET /api/admin/me/activity`) now drops a report another Admin took over from you or released, so it is
  counted for the Admin who has it.
- Tests: new takeover, release, closed-409, audit detail, hazard group, `handled_today` and status-filter checks in `tests/test_console.py`;
  two old checks that expected the 409 for another Admin were changed. `docs/API.md` regenerated.
- Not done: no frontend, CSS or chatbot changes.

## Update 14 — Admin console gaps (backend only)
Filled the gaps between the admin console design (the 38-page mockup and its notes) and the API. Everything below is additive:
no path, method or answer shape that existed changed, and every public answer is the same plus, at most, new optional fields.
- **Mine and release.** `GET /api/admin/reports` takes `mine=true` (only reports you took; with `include_closed` also the ones you
  took and closed). Each item has `is_mine` for the "Mine" chip. New `POST /api/admin/reports/{id}/release`: Being handled -> New,
  nobody assigned; only the Admin who took it (409 for others, and for a closed report), safe to call twice, a whole hazard group
  moves together, audited as `report.release`. The assigned Admin's name was already in `taken_by`.
- **Badge counts.** New `GET /api/admin/summary`: `new_reports`, `being_handled`, `mine`, `pending_places`, `removed_centers`
  (a few COUNT queries, no lists; a hazard counts once for all its reports).
- **Recent activity.** New `GET /api/admin/me/activity` (`limit`, default 20, max 100): the signed-in Admin's own audit entries
  newest first (sign-ins and sign-outs left out) and `handled_today`: different reports they took (and did not release), resolved,
  marked false or verified since local midnight. Midnight uses `ADMIN_DAY_UTC_OFFSET_HOURS` (default 8; the Philippines has no
  daylight saving, so no time zone database is needed on Windows).
- **Contact settings.** New table `app_settings` (made by `create_all`; old databases need nothing). `GET /api/support-contact`
  (public) gives `support_email` and `support_number`; `GET` and `PATCH /api/admin/contact-settings` (Admin) also give and change
  `control_room_number`, which is never in a public answer. A value not set, or cleared (send `null` or an empty text), is `null`,
  never placeholder text. A real change is audited as `settings.contact_update` (changed fields and their old values); sending the
  same value again logs nothing. Numbers follow the emergency-number rules; the email is checked loosely (max 120 characters).
- **Emergency number categories.** New nullable column `emergency_numbers.category`: `medical`, `accident`, `flood`, `violence`,
  `missing_person`, or `null` for a general number. Added to an existing database on startup by `content_service.upgrade_number_columns`
  (idempotent, keeps every row; existing numbers, 911 included, stay untagged). `category` is accepted on `POST` and `PATCH
  /api/admin/emergency-numbers` (`null` clears it), is in every number's answer, and `GET /api/emergency-numbers?category=` filters
  (untagged numbers are only in the unfiltered list, so the sheet pins 911 itself).
- **Polling and distance.** `GET /api/admin/reports` takes `latitude` and `longitude` together (422 for one alone): each item gets
  `distance_m` (null otherwise; the order stays most urgent first). `since` (ISO 8601, no zone = UTC) returns only items that changed at
  or after it, **including closed ones**, so a screen can drop a report another Admin just closed; send the last answer's `server_time`
  (now taken before the query, so a change made while it runs is seen by the next poll). `new_help_count`, `has_new_help` and
  `latest_report_id` still cover everything. The answer echoes `since`.
- **Already there, not changed:** hazard detail for Admins (`report_count`, `phones`, `hazard_state` pending/unconfirmed/verified,
  `verified`, `verified_by`, and `verify` and `mark-false` on the same item), and the assigned Admin's name (`taken_by`).
- Tests: new `tests/test_console.py` (12 checks, including an old database with an emergency_numbers table that has no `category`,
  started twice). `docs/API.md` regenerated. New setting in `.env.example`.
- Not done: no frontend, CSS or chatbot changes. The admin console design asks for a mine/status filter on the list; only `mine` was
  asked for, so the Resolved filter still uses `include_closed`.

## Update 13 — One role: Admin (Admin console, backend part 1)
- **One role, `admin`.** The rank system, `require_responder` and `require_super_admin` are gone; `auth.require_admin` is the one
  check. `optional_staff` still gives a signed-in Admin (or None) to public routes, which count that Admin as an "official".
  Everything that was Super-admin-only (accounts, audit log, delete a center now, advisories, sources, emergency numbers,
  unblock phones, reset password) is open to every Admin. Nothing is locked by role.
- **Renamed, old paths removed (breaking):** `/api/responder/reports*`, `/api/responder/places*` and
  `/api/responder/facilities/{id}/{status-override,capacity-correction,status-history}` are now under `/api/admin/`. Same
  methods, bodies and answers. `/api/evacuation-centers/removed`, `DELETE /api/evacuation-centers/{id}` and `.../restore` keep their
  paths (Admin only, as before). Public endpoints are unchanged.
- **Migration on startup** (`accounts.migrate_roles`, called from `main.py`): accounts with role `responder` or `super_admin`
  become `admin`. Idempotent, never wipes anything, one audit entry per account (`user.role_migrated`, by `(system)`, with the old
  role) and a server log line. Old audit entries keep the role they had.
- **Safeguards:** you cannot lock or remove yourself, and the last active Admin cannot be locked or removed (409).
- **401 vs 403:** no token, an unknown token or an idle sign-in is 401. A sign-in that is still alive but whose account is locked or
  was removed is now 403 (and the sign-in is deleted). Locking or removing through the API still ends the sessions at once, so
  the old token then gets 401.
- **Bodies and answers:** `role` in `/api/me`, sign-in and the account list is always `"admin"`. `POST /api/admin/users` no longer
  needs `role`; a legacy `role` (`admin`, `responder`, `super_admin`) is **accepted and ignored for one release** (the answer's
  `message` says so), then it will be rejected. Public wording that said "responders" now says "Admins".
- **Scripts:** `create_super_admin.py` is replaced by `create_admin.py` (first Admin only, password prompt, same checks).
  `seed_demo.py --with-demo-staff` makes "Demo Admin" and "Demo Admin 2" (a second one so lock and remove can be tried).
  `generate_api_doc.py` and `docs/API.md` regenerated.
- Setting names `STAFF_IDLE_MINUTES` and `RESPONDER_REFRESH_SECONDS` are kept so existing `.env` files keep working.
- Tests: all five files use the single role. New: 401 on every admin route (found from the routes themselves), 403 for a locked or
  removed account on every admin route, the migration (in process and against an old database on startup), the last-Admin rule,
  the legacy `role` field, `create_admin.py`.
- **Frontend not changed** and still calls `/api/responder/*`: it needs the new paths. `ADMIN_CONSOLE.md` was not available while
  doing this; README, `docs/REDESIGN.md` and `docs/FRONTEND_TODO.md` got only the factual fixes and a pointer to it.

## Update 12 — Operations: .env, passwords, phone blocks, place edits, audit filters, cleanup, demo data, API reference (redesign part 5, backend only)
- **`backend/.env` is loaded automatically** by `config.py` (no new dependency). Blank lines and `#`
  comments are skipped, simple quotes removed, a real environment variable is never overridden, a missing file
  is fine. `database.py` now imports `config` first so `DATABASE_URL` can live in the file. `backend/.env` is
  ignored by Git; `.env.example` lists the new settings.
- **Passwords.** New `POST /api/auth/change-password` (signed in): wrong current password = 403 and counted per person
  and per IP (then 429); same minimum length as account creation; the new password must differ; the person's OTHER
  sessions end. New `POST /api/admin/users/{id}/reset-password` (Super admin): sets the password the admin typed, ends all
  that person's sessions, clears wrong tries and the automatic lock (a lock a Super admin set stays; not for your own
  account). Both audited (`auth.change_password`, `user.reset_password`); passwords are never logged or returned.
  README no longer says a forgotten password needs the account recreated.
- **Phone blocks.** New `GET /api/admin/blocked-phones` (id, blocked_at, false_reports, expires_at; never the phone ID or
  hash) and `POST /api/admin/blocked-phones/{id}/unblock` (audited as `report.phone_unblocked`), Super admin. New setting
  `BLOCK_EXPIRES_DAYS` (default 0 = never); expired blocks stop counting at once and are removed by the cleanup
  (`report.block_expired`). An unblocked or expired phone starts with a fresh false-report count (new table `forgiven_phones`,
  made automatically).
- **Place details.** New `PATCH /api/responder/places/{id}` (responder, Super admin): name, address, barangay, contact,
  note, same limits as adding; the 30 m duplicate rule is re-checked on a name change (409); audited as `place.edit`
  with old and new values. Only centers added through the app (they are rebuilt from their own row at startup, so
  edits stay). Centers from the data files, hospitals and clinics are refused with a plain message, because the data
  files overwrite them at every start.
- **Audit log.** `GET /api/admin/audit-log` keeps its shape and parameters and adds `person` (part of a name, any capitals),
  `from`, `to` (YYYY-MM-DD, UTC, `to` includes that day) and `offset`. The match count is in the `X-Total-Count` header
  (exposed to browsers in the CORS settings). A bad date is a plain 422.
- **Scheduled cleanup.** One background task (`app/maintenance.py`) runs the purges every `PURGE_INTERVAL_MINUTES` (default
  60, 0 = off): reports, removed centers and rejected places, idle sessions, expired blocks. A failing job does not stop
  the others; the log has job names and counts only; it stops cleanly with the server. Off in the tests.
- **Demo data.** `backend/scripts/seed_demo.py`: marked DEMO reports, hazards, pending and approved places, advisories, and with
  `--with-demo-staff` two demo accounts (passwords printed once). Refuses `typhoon.db` and non-SQLite databases without
  `--force`; prints the database; safe to run twice; `--db` or `DATABASE_URL` for a separate file.
- **`docs/API.md`** is generated by `backend/scripts/generate_api_doc.py` from `app.openapi()` (introduction, roles, error
  codes, four example flows, a table per area with request and response fields).
- New settings: `BLOCK_EXPIRES_DAYS`, `PURGE_INTERVAL_MINUTES`, `PASSWORD_CHANGE_MAX_WRONG`, `PASSWORD_CHANGE_IP_MAX_WRONG`,
  `PASSWORD_CHANGE_WINDOW_SECONDS`. New table `forgiven_phones` (created on start). No existing table changes. No new
  dependency. Every existing endpoint and response shape is unchanged. Frontend not changed.
- New test file `backend/tests/test_ops.py` (in `run_all.py`).

## Update 11 — Weather, advisories, emergency numbers, chatbot placeholder (redesign part 4 of 4, backend only)
- **Weather is real.** `GET /api/weather` reads Open-Meteo (no key) for Batangas City and
  caches it for 10 minutes (`WEATHER_CACHE_MINUTES`). If the call fails, the last good
  forecast is served with `is_stale: true`, a plain `notice` and `fetched_at` (a copy is
  kept in the database, so it also works after a restart). With no good forecast ever,
  the answer is a plain 503; numbers are never made up. Replaces the sample-data stub.
- **Advisories**, posted by hand by a Super admin (no automatic fetching): public
  `GET /api/advisories` (pinned first, then newest; `?official=true` for the Warnings tab),
  Super admin `POST /api/admin/advisories`, `PATCH`, `POST .../pin`, `POST .../unpin`,
  `DELETE`. Only sources on a list count as official: it starts with PAGASA, NDRRMC and
  Batangas City CDRRMO, and a Super admin edits it (`/api/admin/advisory-sources`).
- **Emergency numbers** in the database: public `GET /api/emergency-numbers`, Super admin
  add, edit, remove and `PUT /api/admin/emergency-numbers/order`. Only 911 is filled in.
- **Chatbot placeholder, AI not connected.** `POST /api/chat` takes `{ question }` and gives
  `{ answer, topic }`, which is what the chat screen reads. The answer is fixed text
  (not available yet, call 911, follow official advisories). No AI model, no external call,
  no key, no cost, no new dependency, nothing stored about who asked or what. Every answer
  ends with "AI-generated. Follow official advisories first.", added in one place for all
  providers. `chat_service.answer(question)` is the one entry point; a marked empty slot
  (`gemini`) is ready for later. `CHAT_PROVIDER` names the provider; an unbuilt name falls
  back to the placeholder with one warning. Limits: 200 characters per question and 15
  questions per 10 minutes per IP (settings in `config.py`). `backend/.env.example` is new,
  with a commented `GEMINI_API_KEY=` for later. README has "Plugging in an AI later".
- Every admin action above is audited with the person's name (`advisory.*`,
  `advisory_source.*`, `emergency_number.*`).
- **Removed:** `ai_service.py` and `routes.py` (never mounted; the old `/weather`,
  `/ai/prep-plan`, `/ai/weather-explainer`, `/ai/damage-report` and `/ai/ask` were stubs) and the
  schemas only they used. Nothing imported them.
- New tables, made automatically on the next start of an existing database: `advisories`,
  `advisory_sources`, `emergency_numbers`. No existing table gets a new column. The starting
  rows are made once, when a table is first created.
- **Frontend not changed. Things to know when connecting it** (the backend already fits
  the field names, shapes and limits the screens use; these are the places it cannot):
  - `EmergencyHotlines` / `hotlineData.ts` hardcode two numbers: 911 (National Emergency)
    and 143 (Philippine Red Cross). The database has 911 only. 143 is not confirmed
    and was not copied in.
  - The chat screen shows "AI-generated. Follow official advisories first." in its footer and
    the answer now ends with the same line, so it shows twice.
  - `UpdatesTab` sorts official first and ignores pinned, and always shows an
    "AI-summarized" chip and a "summaries are generated by AI" note. Advisories are written by
    a person. The server sends `pinned` and `is_official`.
  - `UpdatesTab` needs a link on every card, so `source_url` is required for an advisory.
  - Advisory `id` is a number; the screens type it as a string (convert with `String(id)`).
  - Times are ISO strings in UTC (`published_at`, `fetched_at`); the screens expect `Date`.
  - `AlertsSheet` still uses fixed "unavailable" states and sample updates; `WeatherStrip`
    takes `headline` and `detail`, which the server sends as `strip`.

## Update 10 — Places rules, status source, overrides (redesign part 3 of 4, backend only)
- **A place a user adds starts pending.** Only the phone that sent it (hashed
  `X-Phone-Id`, the same handling as the reports) sees it, in `GET /api/facilities`
  with `"approval_status": "pending"`. Nobody else can see it, read its history or
  update its status. A responder or Super admin approves it (public) or rejects it
  (staff only). The duplicate rule (same name within 30 m) is kept, but it now
  **flags** the place for the staff list (`possible_duplicate`) instead of refusing it.
  The same phone cannot send the same place twice while it waits (409) and can have
  at most 5 waiting (`PENDING_PLACES_PER_PHONE`).
- **Removing is staff only.** `DELETE /api/evacuation-centers/{id}`, `POST .../restore`
  and `GET /api/evacuation-centers/removed` now need a responder or Super admin
  sign-in (401 / 403 otherwise), are audited, and are no longer limited per IP.
  "Hide on this phone" stays in the browser; the server never hides a center for
  everyone because a user asked.
- **30 days, then deleted.** A removed center is kept `REMOVED_CENTERS_KEEP_DAYS`
  days (30, environment override), then deleted with its status history by
  `place_service.purge_removed_centers`: on start and with
  `py scripts/purge_removed_centers.py`. Places rejected that long ago are deleted
  too. A center from a data file is noted in the new `deleted_facilities` table so
  the next start does not bring it back. A Super admin can delete one sooner
  (`DELETE /api/admin/places/{id}`, only a removed center or a rejected place).
- **Where a status came from.** Every update has `source` (`user` or `official`) and
  `source_label` ("Reported by a user" / "Confirmed by official"), inside `status`
  in `/api/facilities`. It is official when a signed-in responder or Super admin
  sends it. A wrong or expired token counts as a user, not an error.
- **Overrides and capacity corrections** (responder or Super admin, audited with
  the name): `POST /api/responder/facilities/{id}/status-override`,
  `POST .../capacity-correction`, `GET .../status-history`. Each adds a row to the
  status history; nothing is erased. After an official sets a capacity, a user
  report cannot change it.
- New endpoints: `GET /api/responder/places`, `POST /api/responder/places/{id}/approve`,
  `POST /api/responder/places/{id}/reject`.
- New columns and table, added automatically to an existing database on the next
  start: `user_evacuation_centers` (`approval_status`, `phone_hash`, `reviewed_by`,
  `reviewed_at`, `reject_reason`), `facility_removals` (`removed_by`),
  `status_updates` (`source`, `kind`, `changed_by`), table `deleted_facilities`.
  Places already on the map become "approved"; old updates become user reports.
- `/api/facilities` only gained fields (`approval_status`, `status.source`,
  `status.source_label`). The removal response gained `removed_by`, `delete_after`,
  `days_left`.
- Docs: README and `docs/REDESIGN.md` now mark accounts, reports and the places
  rules as working (on the server).
- Tests: `py tests/test_places.py` (32 checks). `py tests/run_all.py` runs it with
  `test_accounts.py` and `test_reports.py` (each needs its own process).
  `test_accounts.py` had one check changed: the list of removed centers now
  answers 401 without a sign-in.
- Changed: `models.py`, `schemas.py`, `config.py`, `main.py`, `auth.py`,
  `evac_routes.py`, `evac_service.py`, `status_service.py`, `tests/test_accounts.py`.
  New: `place_service.py`, `place_routes.py`, `status_admin.py`,
  `scripts/purge_removed_centers.py`, `tests/test_places.py`, `tests/run_all.py`.
  No frontend change.

## Update 9b — Report fields: category, people, can move (backend only)
- Small change to the reports from update 9, to match the incident form.
- `POST /api/reports` now needs a **`category`** (1 to 40 characters: what the
  hazard or need is, for example "Flooded road" or "Trapped"). Help requests
  may also send **`people`** (whole number, 1 to 999) and **`can_move`**
  (`"yes"`, `"no"` or `"unsure"`). Both are refused with a clear 422 on a hazard.
  Any other field is still refused.
- **`contact` is now required for help requests** and stays optional for hazards.
- Responders see `category`, `people` and `can_move` in the list and in the
  take / resolve / mark-false / verify responses (a hazard also lists every
  different `categories`). The public hazard output (`/api/hazards/nearby`)
  gets `category` and nothing else. "My reports" shows the sender's own
  `category`. People and can move are never shown to the public.
- Hazards within 100 m still group together whatever the category; the first
  report's category is the one shown.
- New columns `category`, `people`, `can_move` on `reports`, added
  automatically to an existing database on the next start. Old reports keep
  their data and show an empty category.
- Tests: `py tests/test_reports.py` has new checks for all of the above,
  including upgrading a database made by update 9.
- Changed: `report_schemas.py`, `report_service.py`, `report_routes.py`,
  `models.py`, `config.py`, `main.py`, `scripts/purge_reports.py`,
  `tests/test_reports.py`. No frontend change.

## Update 9 — Help requests and hazard reports (redesign part 2 of 4, backend only)
- Two kinds of report, sent without an account: **"I need help"** and **hazard**.
  No photos and no name field. A report has a location, an optional short note and
  an optional contact. The exact location and the contact are visible only to
  responders and Super admins.
- **Phone ID**: a random value the browser sends as the header `X-Phone-Id`, used
  for "my reports". Not proof of identity. Only its hash is stored.
- Help requests go to responders only and are never public. The sender sees their
  own reports and a status: New, Being handled, Resolved (`GET /api/reports/mine`).
- Hazards: people within 1 km see an approximate spot with no details
  (`GET /api/hazards/nearby`). Unconfirmed after 3 reports from 3 different phones,
  Verified once a responder or Super admin verifies it. Reports about the same
  place (within 100 m) count as one hazard; one phone counts once.
- Responder actions, all in the audit log: take it, resolve (needs what was done),
  mark false (needs a reason), verify a hazard. After 3 false reports from one
  phone, that phone is blocked from sending reports.
- Responder list `GET /api/responder/reports` for polling about every 10 seconds,
  with `has_new_help` / `new_help_count` for the red "Needs help" alert.
- Reports are deleted after 30 days: when the server starts, and with
  `py scripts/purge_reports.py`.
- Per-phone and per-IP limits and cooldowns on the public report endpoints. IP
  addresses are stored hashed only.
- New tables: `reports`, `blocked_phones` (created on the next start; existing
  data is untouched).
- New settings in `backend/app/config.py` (each can be set with an environment
  variable): `REPORTS_KEEP_DAYS` (30), `HAZARD_UNCONFIRMED_PHONES` (3),
  `FALSE_REPORTS_BEFORE_BLOCK` (3), `NEAR_ME_KM` (1), `RESPONDER_REFRESH_SECONDS`
  (10), plus `HAZARD_MERGE_METERS`, `HAZARD_APPROX_METERS` and the `REPORT_*`
  limits.
- Tests: `py tests/test_reports.py` (uses its own temporary database).
- New files: `backend/app/report_routes.py`, `report_schemas.py`,
  `report_service.py`, `backend/scripts/purge_reports.py`,
  `backend/tests/test_reports.py`. Changed: `models.py`, `config.py`,
  `rate_limit.py`, `main.py`.
- Not in this part: the report and responder screens (the frontend is unchanged
  and the old incident form still saves on the phone only), places approval,
  weather, advisories, chatbot.

## Update 8 — Staff accounts and roles (redesign part 1 of 4, backend only)
- Staff accounts with two roles: **responder** and **super_admin**. The public
  still has no account and there is no public sign-up. A Super admin creates,
  locks, unlocks and removes accounts.
- Sign in with a name and password (`POST /api/auth/sign-in`) and sign out
  (`POST /api/auth/sign-out`). After 5 wrong tries in a row the account is locked
  for 15 minutes (a Super admin can unlock it sooner). A staff session ends after
  30 minutes without use. Passwords are stored hashed (scrypt); sign-in tokens
  are stored as hashes only.
- A reusable server-side role check for admin routes (`backend/app/auth.py`:
  `require_responder`, `require_super_admin`) and `GET /api/me`.
- Audit log: every admin action is written with the person's name
  (`backend/app/audit.py`, helper `audit.record(...)` for the next parts).
  Super admins read it at `GET /api/admin/audit-log`. Entries are never edited
  or deleted, and the IP is stored hashed only.
- New tables: `users`, `auth_sessions`, `audit_log`. They are created on the
  next start; existing data is untouched.
- New settings in `backend/app/config.py` (each can be set with an environment
  variable): `STAFF_IDLE_MINUTES` (30), `SIGNIN_MAX_WRONG_TRIES` (5),
  `SIGNIN_LOCK_MINUTES` (15), plus `SIGNIN_IP_MAX_ATTEMPTS` /
  `SIGNIN_IP_WINDOW_SECONDS` (20 per IP per 10 minutes) and `MIN_PASSWORD_LENGTH` (8).
- First Super admin: `py scripts/create_super_admin.py` (asks for a name and a password).
- Tests: `py tests/test_accounts.py` (uses its own temporary database).
- `/api/facilities`, the status routes and the evacuation center routes are
  unchanged and still need no sign-in (they get their role checks in later parts).
- New files: `backend/app/account_routes.py`, `account_schemas.py`, `accounts.py`,
  `auth.py`, `audit.py`, `security.py`, `backend/scripts/create_super_admin.py`,
  `backend/tests/test_accounts.py`, `backend/requirements-dev.txt`.
- Not in this part: reports, places approval, weather, advisories, chatbot, and
  any change to the frontend.

## Update 7 — Evacuation center manager
- Evacuation centers can be added, removed and restored in the app. **Add
  evacuation center** (bottom left): tap the map, drag the pin, fill in the form
  (name, type, maximum capacity, optional barangay/address/contact/note). The pin
  shows up right away with a small blue ring. **Remove from map** (in the details
  panel, with a confirmation step) hides a center; the menu button (top left)
  opens **Removed centers** with a **Restore** button for each.
- Removing is a soft delete: nothing is erased. The center and its status
  history stay in the database, a row in `facility_removals` hides it, and it
  stays hidden after a backend restart or a new `facilities.json`.
- Details panel for evacuation centers: status label (Open - Space available,
  Almost full, Full, Closed / Not in use), "Last updated" with a relative label,
  "May be outdated", and a capacity bar (under 70% green, 70-99% orange, 100% or
  more red) with "85 / 100 people" and "15 spaces left". Without a status it says
  "No status yet" together with "Capacity: N people" (never a fake default
  status). Without a capacity (older OpenStreetMap or manual centers) it says
  "Capacity not set" with a small **Set capacity** button.
- Update status form for evacuation centers: only open, almost full, full and
  closed; optional people inside, maximum capacity (filled in from the center),
  resources and a note. Hospitals and clinics keep their own form. If the server
  saves the report as full (people inside reached the capacity), the page shows
  its message. The pin and panel update immediately; if sending fails, what was
  typed is kept and the button says "Try again".
- Pins: green open, orange almost full, red full, grey closed, hollow for no
  status, dim with a dashed ring when older than 6 hours, and a small blue ring
  on centers added through the app. The type letters stay.
- Backend: `POST /api/evacuation-centers`, `DELETE /api/evacuation-centers/{id}`,
  `GET /api/evacuation-centers/removed`, `POST /api/evacuation-centers/{id}/restore`;
  new tables `user_evacuation_centers`, `facility_removals`, `action_log` (hashed
  IP only); `/api/facilities` hides removed centers and gives evacuation centers
  `people_inside`, `max_capacity`, `spaces_left`, `percent_full`, `source` and
  `center_type`; the status route saves "full" when people inside reach the
  maximum capacity and returns a `message`; duplicate names within 30 m are
  refused; the location must be inside Batangas City.
- New files: `backend/app/evac_routes.py`, `evac_service.py`, and in
  `frontend/src/components/` `AddEvacCenter.tsx`, `EvacCenterForm.tsx`,
  `evacCenterDraft.ts`, `CapacityIndicator.tsx`, `RemovedCenters.tsx`,
  `EvacManager.css`. `README.md` has the status table, the add/remove/restore
  steps and the project structure.
- To confirm with the documentation: the 70% / 100% bar colors, the automatic
  "full" rule, the limit of 10 add/remove/restore actions per IP per 10 minutes,
  the 30 m duplicate distance and the Batangas City area (`config.py`).
- Limits: there are no accounts, so anyone can remove or restore a center; the
  per-IP limit and the action log are the only protection. **Set capacity** opens
  the update form because the backend only accepts a capacity together with a
  status report. Not tried on a real phone yet.

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
