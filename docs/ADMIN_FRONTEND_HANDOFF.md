# SILONG admin frontend handoff

For the developer of the **admin console**: a separate frontend with its own link, one backend, one role (**Admin**).
Field-by-field shapes are in [`API.md`](API.md) and at `http://127.0.0.1:8000/docs`; rules are in [`REDESIGN.md`](REDESIGN.md); the user site checklist is [`FRONTEND_TODO.md`](FRONTEND_TODO.md). This file says, for each screen, **which calls to make, which fields to use, which errors to handle, and when to refresh**. "The admin console design" means the design notes and rules that came with the staff console mockup; "the mockup (page N)" means a page of the mockup. Neither is in this repository.

Marks used below:

- **SUPPORTED**: the server does it, as described.
- **NOT SUPPORTED YET**: the server has no endpoint or field for it. Do not build a call; show the screen as planned or leave it out.
- **NOT DESIGNED**: the server supports it but the design has no screen for it.

## 0. Setup and fixed rules

| Part | Address |
| --- | --- |
| Backend | `http://127.0.0.1:8000` (API under `/api`) |
| User site | `http://localhost:5173` |
| Admin console | `http://localhost:5174` (your project; any free port works if it is in `CORS_ORIGINS`) |

- Set `VITE_API_URL` like the user site does (default `http://127.0.0.1:8000/api`).
- CORS: the backend answers a browser only for the origins in `CORS_ORIGINS` (`backend/.env`). Default: `localhost` and `127.0.0.1` on 5173 and 5174. **It does not allow every origin** (the admin console design says it does; that is out of date since Update 16). A phone on Wi-Fi needs its address added: README, "Testing on a phone over Wi-Fi". Allowed request headers: `Authorization`, `Content-Type` (and `X-Phone-Id`, which you never send). Only `X-Total-Count` can be read from a response, so **`Retry-After` cannot be read**: use the minutes or seconds written in `detail`.
- First Admin: `cd backend`, `py scripts/create_admin.py`. Demo data: `py scripts/seed_demo.py --db demo.db --with-demo-staff` (Admins "Demo Admin" and "Demo Admin 2", passwords printed once).
- Every admin call sends `Authorization: Bearer <token>`. The role is always `"admin"`: never branch on it, never show a role label, never lock a tab. One **ADMIN** badge.
- Times are ISO strings in UTC (`...Z` or `+00:00`): convert with `new Date(iso)`. Ids are numbers. Error bodies are `{"detail": "<message>"}`; a 422 for a badly shaped body is a list of `{type, loc, msg}`. Show `detail` as written.
- A report's reference like `SIL-0142` in the mockup is **not a server field**: the server has only the number `id`. Format it the same way as the user site (suggestion: `SIL-` plus the id with 4 digits) and use `id` in every call. A hazard line uses the id of its first report.

### Notes you must follow

**(a) Take-over confirmation.** `POST /api/admin/reports/{id}/take` takes a report over from another Admin without asking. So when an item's `taken_by` is **another** Admin (not you; `is_mine` is false and `status` is `being_handled`), the screen must first ask **"<name> is handling this. Take over?"** and call take only after "Take over". When `taken_by` is empty, or is you, call take straight away. The server returns 409 only when the report is already closed.

**(b) Where the admin token is kept is not decided** (memory only, or browser storage). Whatever is chosen: it must never be reachable from the user site (the two sites are two origins; keep it that way) and must **never be put in a URL**, a query string or the `#` part. It travels only in the `Authorization` header, only to the backend.

**(c) The sign-in has no link back to the public map.** No link, button or text on any admin screen points to the user site, and the user site has no admin link. A user who opens the admin link sees only the sign-in.

## 1. Shared behaviour

### 1.1 "You were signed out" (401, 30 minutes idle, sliding)

- The server ends a sign-in after **30 minutes without any request** (`user.idle_timeout_minutes` in the sign-in answer, and in `GET /api/me`). **Every** successful call moves the timer, including your polling.
- On the next call after that, the server answers **401**. Its `detail` is one of: "Please sign in." (no token sent), "Your sign-in is no longer valid. Please sign in again." (unknown token: already ended, locked out, password reset), "You were signed out after 30 minutes without use. Please sign in again." (idle). The idle session is deleted on the first such call, so a second call gets the "no longer valid" text. **Do not tell them apart.**
- Rule: any 401 on an admin call while you hold a token: drop the token, stop all polling, show the full-screen **"You were signed out. Staff accounts sign out after 30 minutes without use. Sign in again to keep working."** (mockup page 36; say "Admin accounts") with a **Sign in** button. A 401 from `POST /api/auth/sign-in` itself is a wrong name or password, not this screen.
- A 403 on an admin call ("This account is locked..." or "This account no longer exists.") means the account was locked or removed while the sign-in was alive: handle it the same way and show `detail`.
- **Polling keeps the session alive.** The server cannot tell your 10-second poll from a person. Without help, an open console never signs out, which is not what "after 30 minutes without use" means. Decide and build one of: (1) the console tracks the person's own clicks and keystrokes, and after `idle_timeout_minutes` without any, calls `POST /api/auth/sign-out` and shows "You were signed out"; or (2) it stops polling while the tab is hidden, so the server's timer can run out. Option 1 is what the design describes.

### 1.2 Lock after 5 wrong tries (423)

`POST /api/auth/sign-in` gives **423** in two cases: five wrong tries in a row (the fifth wrong try itself returns 423, "Too many wrong tries. This account is locked for 15 minutes."; later tries say "Try again in about N minute(s).", and even the right password is refused until then), and an account locked by an Admin ("This account is locked. Ask another Admin to unlock it."). Show `detail` under the form. The static line "After 5 wrong tries, sign in is locked for 15 minutes." stays on the screen. Another Admin unlocks an account in Accounts (2.6); that also clears a wrong-tries lock.

### 1.3 Sign-in rate limit (429)

20 sign-in tries per IP per 10 minutes. `detail`: "Too many sign-in tries from your connection. Please try again in about N minute(s)." Show it and disable the button for that time (read N from the text; `Retry-After` is not readable). Change password has its own 429 (2.9). No other admin route is rate limited.

### 1.4 "Mark as false" dialog (reason required)

Title "Mark <reference> as false?". Text: "The sender is not told. After 3 false reports from one phone, that phone is blocked from sending reports." A required **reason** (the mockup shows a drop-down with "Prank or test report"; the list of reasons is not defined: you choose, and add "Other" with a text box). Send `POST /api/admin/reports/{id}/mark-false` with `{"reason": "<text>"}`: 3 to 500 characters after extra spaces are removed (else 422 "Give a reason (3 to 500 characters)."). Buttons Cancel / Mark false; the button stays disabled until a reason is chosen. Written to the audit log (`report.mark_false`) with the Admin's name. A phone with 3 false reports is blocked (audit `report.phone_blocked`); that shows in Blocked phones (2.8).

### 1.5 "Delete for good" dialog (type the name)

Title "Delete for good?". Text: "<name> and all of its status history will be deleted. This cannot be undone." Field "Type the name to confirm"; the red button stays disabled until the typed text equals the place's `name` (compare after trimming; the server does **not** check the typed name, this is the screen's job). Then `DELETE /api/admin/places/{facility_id}` -> `{"message": "Deleted for good, together with its status history."}`. Errors: 404 "Evacuation center not found."; 409 "Only a removed center or a rejected place can be deleted for good. Remove it first." Audit `place.delete`.

### 1.6 Errors on every admin call

| Code | Meaning | Screen |
| --- | --- | --- |
| 0 | server not reached (no response) | "Can't connect. SILONG needs the internet. Check your connection and try again." with Try again (mockup page 36); keep the last data on screen |
| 401 | no good sign-in | 1.1 |
| 403 | account locked or removed (also: wrong current password on change-password) | 1.1 / `detail` |
| 404 | the thing is gone (for example another Admin deleted it) | `detail`, then refresh the list |
| 409 | clashes with the current state (report already closed, name already used, own account, last Admin, place already on the map...) | `detail`, then refresh |
| 422 | a value is not accepted | `detail` (first message of the list if it is a list), keep the form open |
| 423 | sign-in only (1.2) | `detail` |
| 429 | sign-in and change-password only | `detail` |

### 1.7 What refreshes, and how often

There is no push, no text and no page to Admins (**NOT SUPPORTED YET**); screens poll.

| What | Call | When |
| --- | --- | --- |
| Report list and red alert | `GET /api/admin/reports` | every `refresh_seconds` from the answer (10), with `since` = last `server_time` (see 2.2) |
| Badges (Reports, Places, chips) | `GET /api/admin/summary` | with the report poll |
| Lists on Places, Content, Accounts, Audit log, Blocked phones | their `GET` | when the screen opens, after every action of yours, and on a Refresh button. The design gives no interval for these; a 30 to 60 second poll while the screen is open is a reasonable choice, not a rule |
| Me: recent actions | `GET /api/admin/me/activity` | when Me opens and after an action |

Pause polling when the tab is hidden if you take option 2 in 1.1. Browsers slow timers in a background tab, so the red alert can be late there.

## 2. Desktop screens

Top bar: logo, **ADMIN** badge, five tabs (Live map, Places with a badge, Content, Chatbot, Accounts), the Admin's name, **Sign out**. No lock icons and no "Super admin only" text (the mockup pages 1, 4, 5, 38 still show them: ignore). Sign out: `POST /api/auth/sign-out` (no body, answer `{"message": "You are signed out."}`, safe to call twice), then drop the token and show the sign-in.

### 2.1 Sign in

**SUPPORTED.** One screen at the admin link: Name, Password, show/hide password (screen only), Sign in.

- `POST /api/auth/sign-in` body `{"name": "...", "password": "..."}` (name max 100, not case sensitive; password max 200; any other field is a 422). Answer 200: `token`, `token_type` ("bearer"), `user` = `id`, `name`, `role` ("admin"), `idle_timeout_minutes`.
- Use: `token` (note (b)), `user.name` (top bar and Me), `user.idle_timeout_minutes` (1.1).
- Errors: 401 "The name or password is wrong." (same for an unknown name and a wrong password); 423 (1.2); 429 (1.3); 422 too long; 0.
- Refresh: none. After sign in, open Live map (desktop) or Reports (phone). `GET /api/me` (`id`, `name`, `role`, `idle_timeout_minutes`) is only needed to check a token you already hold.
- Wording: the mockup (page 15) says "SILONG ADMIN", "Staff sign in", "For responders and Super admins only", "Username", "No account? Ask a Super admin..." and has "Back to the public map". Use "Admin sign in", "For Admins only", "Name" (the server's field is `name`), "No account? Ask an Admin to create one. There is no sign-up.", and **remove the back link** (note (c)).
- **NOT SUPPORTED YET:** two-step sign in (planned after Nov 20); a self-service "forgot password" (another Admin resets it, 2.6).

### 2.2 Live map

Report list on the left, map on the right. **SUPPORTED.**

Calls:

| Purpose | Call |
| --- | --- |
| List and poll | `GET /api/admin/reports` |
| Badges | `GET /api/admin/summary` |
| Places layer on the map | `GET /api/facilities` (public, no token; approved places only) |
| Take it | `POST /api/admin/reports/{id}/take` (no body) |
| Give back | `POST /api/admin/reports/{id}/release` (no body; any Admin, any open report) |
| Resolve | `POST /api/admin/reports/{id}/resolve` body `{"what_was_done": "..."}` (3 to 500 characters) |
| Mark false | `POST /api/admin/reports/{id}/mark-false` body `{"reason": "..."}` (1.4) |
| Verify a hazard | `POST /api/admin/reports/{id}/verify` (no body; hazards only, else 422 "Only hazard reports can be verified."; safe to call twice) |
| Call | `tel:` link from `contacts[0]` (no endpoint) |

`GET /api/admin/reports` query (all optional):

- `status`: `new`, `handling`, `resolved` (resolved **and** marked false), `all` (open and closed). Anything else is 422. Not given: open reports only (new and being handled). Filters in the design: **All, New, Being handled, Resolved**. Map: New -> `new`, Being handled -> `handling`, Resolved -> `resolved`. For **All**, the design shows "All 9" next to "New 4" and "Being handled 3" (7), so it is not clear whether All includes resolved ones: omit `status` for open work only, or send `all` to include closed ones. This is a design decision to confirm.
- `kind` (`help` or `hazard`), `mine=true` (only reports you took), `include_closed` (ignored when `status` is given).
- `latitude` and `longitude` together (else 422 "Send latitude and longitude together, or neither."): adds `distance_m`. Not needed on desktop.
- `since` (ISO time): only items that changed at or after it. Closed ones that changed are included so you can **remove them** from your list. Pass the last answer's `server_time`. Merge by `id`.

Answer: `server_time`, `refresh_seconds` (10), `new_help_count`, `has_new_help`, `latest_report_id`, `since`, `items`. The three `new_help_...` / `has_new_help` / `latest_report_id` values always cover all open reports, whatever the filters. Order is the server's, "most urgent first": new help requests (longest waiting first), then other open reports (longest waiting first), then closed (newest first). Do not re-sort.

Item fields to use: `id`, `kind` (`help` -> "Needs help", `hazard` -> "Hazard"), `status` (`new`, `being_handled`, `resolved`, `false`), `is_new_help`, `category` (the card title, for example "Medical help needed"), `categories` (every category sent for a hazard), `people`, `can_move` (`yes`, `no`, `unsure`; help only), `latitude`, `longitude` (exact), `contacts` (list), `notes` (list; "Details"), `created_at` (the "2 min ago"), `updated_at`, `taken_by`, `is_mine`, `closed_by`, `resolution_note`, `false_reason`, `verified`, `verified_by`, `hazard_state` (`pending`, `unconfirmed`, `verified`), `phones`, `report_count` (the "· 3 reports").

Chips: New (red) = `status` `new`; Being handled (yellow) = `being_handled`; Resolved (green) = `resolved`; Hazard "Unconfirmed" = `hazard_state` `unconfirmed`; "Verified" = `verified`. **No design** for `status` `false` (closed as false; it is listed under the Resolved filter, so it needs a chip such as "False") and for `hazard_state` `pending` (a hazard with fewer than 3 phones, not public yet).

Selected "Needs help" card: Take it, Call, Resolve, Mark false; shows exact location, contact, details. Hazard card: **Verify** and **Mark false**, plus the report count while unconfirmed. The server also allows take, release and resolve on hazards (a hazard moves as one group); the design shows only Verify and Mark false for them. After Take, show Release as well (not in the design).

Take: note (a). Resolve: ask what was done first (3.6 has the options). Mark false: 1.4.

Map: layers **Reports, Places, Hazards, Resolved**. Reports and Hazards come from the list (use `kind`); Resolved needs `status=resolved` items; Places is `GET /api/facilities`. Selecting a card selects its pin and the other way round.

Errors for the actions: 401/403 (1.1); 404 "Report not found."; 409 "This report was already resolved." or "...marked false." (refresh, someone else closed it); 422 text length ("Say what was done (3 to 500 characters)." / "Give a reason (3 to 500 characters)."); 0. After any action, replace that item with the answer (the same shape as a list item) and poll again.

Refresh: 1.7 (every `refresh_seconds`). Red "Needs help" alert while `has_new_help` is true (desktop alert: **NOT DESIGNED**; the phone one is 3.7).

Not supported / no data:

- "Near Kumintang Ibaba", "Pallocan West", "Brgy. Cuta" under a title: **no place or barangay field** on a report. Only `latitude` and `longitude`. You can show the coordinates, or work the name out yourself from `GET /api/facilities` or a reverse lookup (your choice; the server gives nothing).
- "(±12 m)" accuracy next to the location: **no field** (reports carry no accuracy).
- "Same area: 1 other report" on a help request: **no field**. Only hazards are grouped (`report_count`, `phones`).
- "Contact (responders only)" / "Mark false" sender notification: the sender is never told (server behaviour).

### 2.3 Places

Three panels. **SUPPORTED** (forms marked NOT DESIGNED).

**Waiting for approval**

- `GET /api/admin/places` (default `status=pending`, longest waiting first). Badge on the tab = `GET /api/admin/summary` -> `pending_places`.
- Fields: `id`, `name`, `center_type` (`permanent`/`temporary`), `barangay`, `address`, `contact`, `max_capacity`, `latitude`, `longitude`, `note`, `approval_status`, `submitted_at` ("12 min ago"), `possible_duplicate` (`id`, `key`, `name`, `distance_m`, `approval_status`, `removed`; "Possible duplicate: 12 m from an existing center"), `message`.
- **Approve:** `POST /api/admin/places/{id}/approve` (no body; safe to call twice; also undoes a rejection). Answer: the place.
- **Edit:** `PATCH /api/admin/places/{id}` with only the changed fields of `name` (2 to 100), `address` (200), `barangay` (80), `contact` (60), `note` (140); an empty text clears all but the name. **Type, capacity and location cannot be edited here.** Errors: 409 when the new name matches another center within 30 m ("Another evacuation center called ... Use a different name."), 409 for a center from the data files, 422 for a hospital or a clinic and when nothing is sent. If nothing changed the answer's `message` says so. The edit form is **NOT DESIGNED**.
- **Reject:** `POST /api/admin/places/{id}/reject` body `{"reason": "..."}` optional, max 140 characters. 409 "This place is already on the map. Remove it instead of rejecting it." Safe to call twice. The reject-reason form is **NOT DESIGNED**.
- **Compare:** no endpoint. Use `possible_duplicate`: if its `approval_status` is `approved` the full place is in `GET /api/facilities` (match `id`); if `pending` it is in this same list; if `removed` is true it is in the removed list (name only). The Compare view is **NOT DESIGNED**.
- Rejected places (**NOT DESIGNED**): `GET /api/admin/places?status=rejected`. Approve brings one back; Delete for good (1.5) removes it.
- Errors: 404 "Added place not found."; 409; 422; 401/403.
- "Device ...a41f" under each row: **no field**. The server never returns a phone ID, a hash or any part of one.

**Removed centers**

- `GET /api/evacuation-centers/removed` -> `id`, `key`, `name`, `removed_at`, `removed_by`, `delete_after`, `days_left` ("24 days" of 30; 0 = deleted at the next cleanup). Badge on phone = `summary.removed_centers`.
- **Restore:** `POST /api/evacuation-centers/{id}/restore` (no body; answer is the place; a center that is not removed is returned unchanged).
- **Delete now:** `DELETE /api/admin/places/{id}` with the dialog in 1.5.
- **Remove a center** (the button that puts a center here is **NOT DESIGNED**; the design shows only the list): `DELETE /api/evacuation-centers/{id}` -> `id`, `name`, `removed_at`, `removed_by`, `delete_after`, `days_left`, `message`. Errors: 404; 422 "Only evacuation centers can be added, removed or restored here." (hospital or clinic); 409 "This place is waiting for approval. Reject it instead of removing it." / "This place was rejected, so it is not on the map."

**Status history**

- Pick a place on the map or from `GET /api/facilities` (no admin list of "places that look wrong" exists: build it from that list yourself, for example by `status.source` `user` and the age).
- `GET /api/admin/facilities/{id}/status-history?limit=50` (1 to 200) -> rows newest first: `id`, `kind` (`report`, `override`, `capacity`), `status`, `people_inside`, `max_capacity`, `resources`, `note`, `updated_at`, `source` (`user`/`official`), `source_label` ("Reported by a user" / "Confirmed by official"), `changed_by` (the Admin's name on official rows). 404 "Facility not found."
- **Override latest:** `POST /api/admin/facilities/{id}/status-override` body `status` (required: evacuation center `open`, `almost_full`, `full`, `closed`; hospital or clinic `open`, `busy`, `full`, `closed`), `people_inside` (0 to 100000), `max_capacity` (1 to 50000), `resources` (any of `space`, `food`, `water`, `power`, `toilets`, `medical`; evacuation centers only), `note` (140), `reason` (140, audit only). Answer 201: the new status (`source` "official"); its `message` says when the server changed what you sent (people reached capacity, so saved as full). 422: wrong status for the type, people more than twice the capacity, hospital with a count. 404 for a place that is not on the map.
- **Correct capacity:** `POST /api/admin/facilities/{id}/capacity-correction` body `max_capacity` (1 to 50000), `reason` (140, optional). 422 "This center has no status yet. Override its status and send the capacity together with it." (a newly approved place has no status, so use Override with `max_capacity`); 422 for a hospital or clinic; 422 when people inside is more than twice the new number. Users cannot change the capacity afterwards.
- Both forms are **NOT DESIGNED** (fields above). "Nothing is erased, and your name is recorded" is true (new history rows, audit `status.override`, `capacity.correct`).
- "Device ...c3d1" and "(looks wrong)" in the mockup history: **no fields** (no device; "looks wrong" is the Admin's own judgement, not data).

Refresh: 1.7 (lists on open, after actions, optional 30 to 60 s).

### 2.4 Content

Emergency numbers, advisories, official sources. **SUPPORTED** (add/reorder/sources/list actions NOT DESIGNED).

**Emergency numbers**

- List: `GET /api/emergency-numbers` (public) -> `id`, `number`, `name`, `description`, `position`, `category` (`medical`, `accident`, `flood`, `violence`, `missing_person`, or null). Already in display order. Only 911 exists at first.
- Edit: `PATCH /api/admin/emergency-numbers/{id}` (only the fields to change; `number` max 30, digits, spaces and `+ - ( ) * #`, at least 3 digits; `name` max 80; `description` max 140; `category`; `null` clears description or category). Remove: `DELETE /api/admin/emergency-numbers/{id}` (204). Add (**NOT DESIGNED**): `POST /api/admin/emergency-numbers` `number`, `name`, optional `description`, `category` (201). Reorder (**NOT DESIGNED**): `PUT /api/admin/emergency-numbers/order` body `{"ids": [...]}` every id exactly once, answer is the new list; 422 "The order must list every emergency number exactly once."
- Errors: 404 "That emergency number was not found."; 422.
- "Not set yet" rows (Batangas City CDRRMO, City hospital) in the mockup **cannot exist**: a number is required (at least 3 digits). To "reserve" a row, leave it out until the number is confirmed.

**Advisories**

- List (for the admin list): `GET /api/advisories?limit=50` (public; `official=true` for official only) -> `id`, `title`, `details`, `organization`, `source_url`, `is_official`, `pinned`, `published_at`, `updated_at` (`summary` repeats `details`). Pinned first, then newest.
- Post: `POST /api/admin/advisories` body `title` (max 120), `details` (max 1000), `organization` (max 80, for example "PAGASA"), `source_url` (**required**, http or https, max 500), `pinned` (default false). 201.
- Edit: `PATCH /api/admin/advisories/{id}` (`title`, `details`, `organization`, `source_url`; at least one; not `pinned`). Delete: `DELETE .../{id}` (204). Pin / unpin: `POST .../{id}/pin`, `POST .../{id}/unpin` (safe to call twice).
- The mockup's form has title, details, a source chip and "Expires tomorrow 6 PM" and **no link field**: the link is required, add it. **There is no expiry on the server** (**NOT SUPPORTED YET**): do not build "Expires". The advisory list with Edit, Delete, Pin, Unpin is **NOT DESIGNED**.
- Errors: 404 "That advisory was not found."; 422 (empty, too long, bad link).

**Official sources** (**NOT DESIGNED**)

- `GET /api/admin/advisory-sources` -> `id`, `name`; `POST` `{"name": "..."}` (max 80, 201); `PATCH /api/admin/advisory-sources/{id}` `{"name": "..."}`; `DELETE` (204; its advisories stay but stop showing as official). 409 "That source is already on the official list."; 404. An advisory is official when its `organization` equals a listed name (case and extra spaces ignored); starts with PAGASA, NDRRMC, Batangas City CDRRMO.

**Contact settings** (**NOT DESIGNED** on desktop; the phone Me screen reads the control-room number)

- `GET /api/admin/contact-settings` -> `control_room_number`, `support_email`, `support_number`, `updated_at`, `updated_by` (`null` = not set). `PATCH` the same fields (send only what changes; `null` or empty clears; at least one field, else 422; email must look like an email; numbers follow the emergency number rules). The control-room number is never in a public answer. The support pair is what the user site's Contact support page shows.

### 2.5 Chatbot

**NOT SUPPORTED YET.** The tab exists in the design ("Checked guide", Edit buttons on topics, the chatbot "Report a wrong answer" inbox) but the server has **no guide table, no guide editor and no wrong-answer route**. `POST /api/chat` is a public placeholder with a fixed answer. Mark the tab "Planned" (or disable it) and **call nothing**. When it is built, the backend owner adds the routes.

### 2.6 Accounts

**SUPPORTED** (everything except Reset password and Lock is **NOT DESIGNED**).

- `GET /api/admin/users` -> `id`, `name`, `role` (always `admin`), `status` (`active`, `locked_by_admin`, `locked_for_wrong_tries`), `locked_until`, `created_at`, `created_by`, `last_sign_in_at` ("Today 21:40"; null if never). Show no role column, or one ADMIN label.
- New account: `POST /api/admin/users` `{"name": ..., "password": ...}` (name 2 to 50 characters and not used by another account, password 8 to 200 characters). Leave `role` out (accepted and ignored for one release, then refused). 201.
- Lock: `POST /api/admin/users/{id}/lock` (the person is signed out at once). Unlock: `POST .../{id}/unlock` (also clears a wrong-tries lock). Reset password: `POST .../{id}/reset-password` `{"new_password": "..."}`; the person is signed out everywhere; the Admin must tell them the password, it is never shown again. Remove: `DELETE /api/admin/users/{id}` (audit entries stay).
- Errors: 404 "Account not found."; 409 "An account with that name already exists.", "You cannot lock your own account.", "You cannot lock the last active Admin.", "You cannot remove your own account.", "You cannot remove the last active Admin.", "To change your own password, use Change password with your current password."; 422 name or password length. Hide Lock, Remove and Reset password on the Admin's own row.
- Refresh: 1.7. Status labels, New account, Unlock and Remove screens are **NOT DESIGNED**.

### 2.7 Audit log

**SUPPORTED, NOT DESIGNED** (the mockup has no screen; where it sits on the desktop is undecided: a sub-view of Accounts is one option).

- `GET /api/admin/audit-log` query: `limit` (1 to 200, default 50), `offset`, `before_id`, `action` (exact, for example `report.resolve`), `actor` (exact name), `person` (part of a name), `from`, `to` (`YYYY-MM-DD`, UTC, whole days). A bad date or `from` after `to` is 422.
- Newest first. **Total in the `X-Total-Count` response header** (matches before `limit`/`offset`): use it for paging.
- Item: `id`, `created_at`, `actor_id`, `actor_name`, `actor_role`, `action`, `target` (for example `report:12`), `detail` (JSON: reasons and notes typed by Admins, never passwords, tokens or phone IDs). Actions in use: `auth.sign_in`, `auth.sign_out`, `auth.auto_lock`, `auth.change_password`, `user.create`, `user.lock`, `user.unlock`, `user.reset_password`, `user.remove`, `user.role_migrated`, `report.take` (detail may hold `taken_over_from`), `report.release`, `report.resolve`, `report.mark_false`, `report.verify`, `report.phone_blocked`, `report.phone_unblocked`, `report.block_expired`, `report.purge`, `place.approve`, `place.edit`, `place.reject`, `place.remove`, `place.restore`, `place.delete`, `place.purge`, `status.update` (an Admin's normal status update), `status.override`, `capacity.correct`, `advisory.create`, `advisory.update`, `advisory.pin`, `advisory.unpin`, `advisory.delete`, `advisory_source.add`, `advisory_source.update`, `advisory_source.remove`, `emergency_number.add`, `emergency_number.update`, `emergency_number.remove`, `emergency_number.reorder`, `settings.contact_update` (read from the code; show an unknown action as plain text). Old entries keep the role they had at the time (`admin`, `responder`, `super_admin`).

### 2.8 Blocked phones

**SUPPORTED, NOT DESIGNED** (the design lists "Blocked phones with Unblock" as missing).

- `GET /api/admin/blocked-phones` -> `id`, `blocked_at`, `false_reports`, `expires_at` (null = never ends by itself). **No phone ID and no hash, on purpose**: show the row number and the date.
- `POST /api/admin/blocked-phones/{id}/unblock` (no body) -> `{"message": "The phone can send reports again."}`; its false-report count starts again. 404 "That blocked phone was not found. It may already have been unblocked."

### 2.9 Change password

**SUPPORTED, NOT DESIGNED on desktop** (design page 11 has it only on the phone Me screen; put it under the Admin's name).

- `POST /api/auth/change-password` `{"current_password": ..., "new_password": ...}` (each max 200; new at least 8 characters, different from the current one). Answer `{"message": "Your password was changed. You were signed out on N other device(s)."}`; your other sign-ins end, this one stays.
- Errors: 403 "The current password is wrong." (counted: 5 per person and 20 per IP per 10 minutes); 429 "Too many wrong passwords. Please try again in about N minute(s)." (read N from the text); 422 "The password must be at least 8 characters." / "The new password must be different from the current one."; 401.

## 3. Phone screens

Header: logo, ADMIN badge (the mockup says STAFF and RESPONDER: use ADMIN), the Admin's name. Bottom bar: **Reports** (badge), **Map**, **Places** (badge), **Me**. Content, Chatbot, Accounts, Audit log and Blocked phones are **not on the phone** in the design (the server does not stop a phone from calling them).

Badges: `GET /api/admin/summary` -> `new_reports` (Reports badge and "New 4"), `being_handled` ("Handling 3"), `mine` ("Mine 1"), `pending_places` (Places badge and "Approval 3"), `removed_centers` ("Removed 2"), `server_time`. A hazard counts once. There is no count for Resolved.

### 3.1 Reports

- Same list call as 2.2. Chips: **New** (`status=new`), **Mine** (`mine=true`; add `status=handling` to match the mockup's "Mine" chip on open reports, or leave it out to list everything you took), **Handling** (`status=handling`), **Resolved** (`status=resolved`).
- Send the Admin's own position as `latitude` and `longitude` to get `distance_m` (metres; show "0.8 km"). GPS needs a secure page: `http://localhost` works, `http://192.168.x.x` does not. Without permission, leave both out and show no distance.
- Card: kind and chip as in 2.2 (the "Mine" chip is `is_mine`), title = `category` (hazard: add "· N reports" from `report_count`), place text (**no field**, see 2.2), distance, time from `created_at`. "Most urgent first · updated 5 s ago" = now minus the last `server_time`.
- Refresh: every `refresh_seconds`, with `since` (2.2). Tap a card -> 3.5.

### 3.2 Map

- Layers: **Reports**, **Hazards**, **Places** (no "Resolved" layer on the phone). Data as in 2.2. The selected report shows a card: kind, chip, title, **Take it**, **Navigate**, **Open** (-> 3.5). Take it follows note (a).
- Navigate: a link built from `latitude` and `longitude`. **Which maps app it opens is undecided.**

### 3.3 Places

- Chips **Approval** (count = `pending_places`), **Fix a status**, **Removed** (count = `removed_centers`).
- Approval: the list, Approve / Edit / Reject / Compare, exactly as in 2.3 (cards show name, barangay, type, capacity, `submitted_at`, the duplicate warning).
- "Looks wrong? Fix a status": a list of places with their latest status and a **Fix** button (Override latest and Correct capacity, 2.3). The server has **no list of suspicious statuses**; build it from `GET /api/facilities` (for example places whose `status.source` is `user`).
- Removed on the phone, Restore: calls as in 2.3 (**NOT DESIGNED** on the phone).

### 3.4 Me

- Name: `GET /api/me` (or the sign-in answer). The mockup shows "Responder · jsantos": there is **one** `name` field (also the sign-in name); show the name only, no role, no separate username.
- **Change password** -> 2.9. **Signs out by itself after 30 minutes without use**: `idle_timeout_minutes` (1.1).
- **My recent actions**: `GET /api/admin/me/activity?limit=20` (1 to 100) -> `handled_today` ("Handled 6 reports today": different reports you took and kept, resolved, marked false or verified since local midnight, `today_starts_at`), `server_time`, `items` (`id`, `created_at`, `action`, `target`, `detail`; your own actions only, sign-ins left out). "Today" uses the server setting `ADMIN_DAY_UTC_OFFSET_HOURS` (default 8).
- **Call the control room**: `control_room_number` from `GET /api/admin/contact-settings`; `null` = not set: show "Number not set yet" and no call button; else a `tel:` link. The mockup says "Number set by the Super admin": say "set by an Admin". (There is no designed screen to set it: 2.4.)
- **Sign out**: `POST /api/auth/sign-out`.
- Footnote in the mockup ("managed by a Super admin on a computer"): say "managed by an Admin on a computer".

### 3.5 Report detail

- Opens from a card, the map card (**Open**) or the red alert. Data: the list item (re-fetch with `GET /api/admin/reports?status=all` is not needed; reuse the item, refreshed by polling). There is **no single-report endpoint**.
- Shows: small map pin, kind chip and status chip, title (`category`), the text (`notes`, in quotes; several for a hazard), "Location 13.7565, 121.0583" (**no accuracy**), "Distance 0.8 km from you" (`distance_m`), "Same area" (**no field**), people and can-move for help (`people`, `can_move`; not in the mockup, but the data is there), Contact (`contacts`) with **Call**, sent time (`created_at`).
- Fixed bottom buttons: **Take it** (note (a)), **Navigate**, **Resolve** (3.6), **Mark false** (1.4). Add Release when it is yours or being handled.
- Label "Contact (responders only)": say "Contact (Admins only)".
- Mobile **hazard detail** (report count, phones, Verify) is **NOT DESIGNED**: the data is `report_count`, `phones`, `categories`, `contacts`, `notes`, `hazard_state`, and the call is Verify.

### 3.6 Resolve sheet

- Title "Resolve <reference>", text "What was done? The sender sees "Resolved"." Options: **Helped on site, Moved to a center, Sent to a hospital, Could not find them, Other**; optional note ("Short note for the team"); Cancel / Resolve.
- The server has **one text field**, `what_was_done` (3 to 500 characters), no separate option. Send the chosen option's words, plus ": " and the note when there is one (for example "Helped on site: ambulance sent"). "Other" alone is 5 characters and passes. Keep the total under 500.
- `POST /api/admin/reports/{id}/resolve`; errors as in 2.2. The sender then sees "Resolved" (no text from you reaches them).

### 3.7 New-help alert

- A red banner at the top: "New: Needs help", "<place text> · 0.8 km · just now", button **Open** (-> 3.5 for that report). Not designed for desktop.
- Trigger: after a poll, `has_new_help` is true and there is an item with `is_new_help` that you have not shown before (the highest `id`; `latest_report_id` also rises with any new report, help or hazard, so do not use it alone). Hide it when that report is no longer `is_new_help` (taken by someone), when you tap Open, or when the person closes it.
- It is a banner inside the open page only. **Texts, pages, push and sound are NOT SUPPORTED YET** (the server cannot send them); a sound or vibration would be your own choice.

## 4. Gaps and contradictions

### 4.1 In the design, no endpoint (**NOT SUPPORTED YET**)

| Design item | What the server has |
| --- | --- |
| Chatbot tab: checked guide, Edit topic, "Report a wrong answer" | nothing (2.5) |
| Two-step sign in | planned after Nov 20 |
| Texts or pages to Admins | nothing; polling only |
| "Expires tomorrow 6 PM" on an advisory | no expiry field |
| "Not set yet" emergency number rows | a number is required |
| Place or barangay under a report ("Near Kumintang Ibaba") | only `latitude`, `longitude` |
| Location accuracy "(±12 m)" | not stored |
| "Same area: 1 other report" for a help request | only hazards are grouped |
| "Device ...a41f" on places and status history | never returned |
| "(looks wrong)" on a status | no field |
| A list of statuses that "look wrong" (phone "Fix a status") | none: build from `GET /api/facilities` |
| Separate username and display name ("J. Santos" / "jsantos") | one `name` |
| `SIL-0142` reference | only `id` |
| Resolve options as data | one text, `what_was_done` |
| Editing capacity or type of a pending place | `PATCH` changes name, address, barangay, contact, note only |
| A count of Resolved reports and an "All" count | `summary` has none |

### 4.2 In the server, no designed screen (**NOT DESIGNED**)

Mobile hazard detail; desktop red alert; Place edit form, reject reason, Compare view; Status override and Correct capacity forms; rejected places list; Remove a center button; Removed centers and Restore on the phone; Audit log with filters and paging; Blocked phones with Unblock; Official sources; advisory list with Edit, Delete, Pin, Unpin; emergency numbers Add and reorder; contact settings (control-room number, support email and number); Accounts: New account, Unlock, Remove, status labels; desktop Change password; a "False" chip and a "pending" hazard chip; Release; where Audit log, Blocked phones and Change password sit in the five-tab desktop layout.

### 4.3 Contradictions found

1. **CORS.** The admin console design says the backend allows calls from any origin and needs no change for the second port. Since Update 16 it allows only the origins in `CORS_ORIGINS` (default: the four localhost addresses). A different port or a phone address must be added (0).
2. **Idle sign-out.** The design says "after 30 minutes without use". The server counts any request, so polling keeps a session alive (1.1).
3. **Backend roles.** The design's section "Backend still has two roles" is out of date: Update 13 merged them; `role` is always `admin`, and old accounts were migrated.
4. **Take over.** The design says to ask first; the server never asks and has no "handled by someone else" error any more (note (a)). `docs/API.md`'s table of common error codes still lists "already handled" under 409 and says to wait for `Retry-After`: both are out of date for the console (409 on take now means closed; `Retry-After` is not readable from the browser).
5. **Hazard actions.** The design shows Verify and Mark false for hazards only; the server also accepts take, release and resolve on them.
6. **Resolved filter.** In the design "Resolved" means done; the server's `resolved` filter also lists reports marked false.
7. **Mockup wording.** Pages 1, 4, 5, 8, 11, 15, 16, 17, 18, 31, 38 still say Staff, Responder, Super admin, "Super admin only" or "Back to the public map", and page 30 shows an "Admin sign in" row in the user menu. The design notes override them: one role, one ADMIN badge, no locks, no back link, no admin row in the user menu.

## 5. Leftovers in the user site

The user site must not mention the admin console or the old roles. These places still do (do not edit them as part of the docs work; each is a change for the user site's developer):

| File | What it has | Change |
| --- | --- | --- |
| `frontend/src/components/HamburgerMenu.tsx` (about line 219, the `<footer className="hm-footer">`) | the row "Admin sign in" with `navigate("/admin")` | delete the row and the footer (4.13 in FRONTEND_TODO) |
| `frontend/src/components/HamburgerMenu.css` (the "Footer: Admin sign in" block, `.hm-footer`) | styles for that footer | delete with the row |
| `frontend/src/App.tsx` | `import { AdminSignInPage }`, the comment about `/admin`, `<Route path="/admin" ...>` | delete the import, the comment and the route; build the real sign-in in the admin console |
| `frontend/src/pages/AdminSignInPage.tsx` and `AdminSignInPage.css` | placeholder "Staff sign in ... for Responders and Super admins ... is not available yet", with a link back to `/map` | delete both files |
| `frontend/src/components/TopBarNav.css` | `.topbar-admin` rules ("Admin sign in" on the right of the bar) and a comment; nothing in `TopBar.tsx` uses the class | delete the rules and the comment |
| `frontend/src/components/MenuPages.tsx` (line 10 comment, line 137) | "Contact details are set by the Super admin" and a comment about staff accounts | say "set by an Admin" (or remove the line); read the values from `GET /api/support-contact` (FRONTEND_TODO 4.15) |
| `frontend/src/components/MenuPages.tsx` (FAQ answer, line 66) | "It is meant for responders only" | "It is meant for Admins only" |
| `frontend/src/components/IncidentPanel.tsx` (lines 13, 20 comments; messages at 234, 321, 442, 553) | "responders" in "Please enter a phone number so responders can reach you.", "Goes to responders only...", "(required, only responders see it)", "This report goes to responders only..." | "Admins". The server's own answer text already says "Admins" |
| `frontend/src/pages/MapPage.tsx` (line 85 comment) | lists "Admin sign in" among the menu items | update the comment |
| `frontend/src/_later/` | parked code | not checked; it is not used |

Also: the mockup pages for the user site (12, 30, 31, 32, 35) say "responders", "Admin sign in" and "Super admin": when those screens are built, use "Admins" and leave the menu row out. The user site's calls to `/api/responder/*`, if any exist in a branch, are `/api/admin/*` now; the user site makes **no** admin calls at all.

## 6. Open decisions for the admin frontend

- Where the admin token is kept (note (b)). Fixed rules: never reachable from the user site, never in a URL.
- How the console signs out on real inactivity (1.1).
- Which maps app **Navigate** opens.
- What "All" means on the Live map (2.2).
- Where Audit log, Blocked phones, Change password and Contact settings sit on the desktop.
- The reasons in the "Mark as false" list (1.4).
- How place names are shown on a report (2.2).
