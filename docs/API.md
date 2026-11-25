# SILONG API reference

This file is **generated** by `backend/scripts/generate_api_doc.py` from the app's own OpenAPI schema.
Do not edit it by hand: change the code (or the introduction inside the script) and run the script again.
The same information is live at `/docs` while the backend runs.

## How it works

**Base URL.** Every path below starts with `/api`. Bodies and answers are JSON.

**Sign-in (Admins only).** There is no public sign-up. An Admin signs in with
`POST /api/auth/sign-in` (`name`, `password`) and gets a `token`. Send it on every Admin request as
`Authorization: Bearer <token>`. A sign-in ends after **30 minutes without any request** (each request
starts the 30 minutes again). **A `401` means sign in again**: the token is missing, unknown, or ran out.

**Phone ID (public reports and places).** The public has no account. The browser makes a random ID once
and sends it as the header `X-Phone-Id`: **16 to 64 letters, digits, `-` or `_`** (for example
`k3J9x-Qe7_Lm2Pz0aB4c`). It is how "my reports" and "my pending places" work. It is not proof of who
someone is, and the server stores only a hash of it.

**Roles.** There is one role, Admin. Nothing is locked by role: every Admin can use every Admin endpoint.

| Role | Who | Can do |
| --- | --- | --- |
| Public | Anyone, no sign-in | Read the map, weather, advisories and numbers; send a status update, a report or a new place (some need `X-Phone-Id`) |
| Admin | Signed-in Admin (`role` is always `"admin"`) | Everything public, plus everything under `/api/admin`: reports, places to approve, status overrides, accounts, the audit log, blocked phones, advisories, official sources and emergency numbers. Removing, restoring and listing removed centers (`/api/evacuation-centers`) are Admin endpoints too |

You cannot lock or remove your own account, and the last active Admin cannot be locked or removed.
`POST /api/admin/users` still accepts a legacy `role` (`admin`, `responder` or `super_admin`) for one release and
ignores it: every new account is an Admin. Stop sending it.

**Common error codes.** The body is `{"detail": "<plain-language message>"}` (a `422` from a badly shaped
body is a list of `{type, loc, msg}`). Show `detail` to the person when it is a text.

| Code | Meaning |
| --- | --- |
| 400 | The `X-Phone-Id` header is missing or not in the right format |
| 401 | Not signed in, or the sign-in ran out. Sign in again |
| 403 | The sign-in belongs to an account that is locked or was removed; or a wrong current password; or this phone is blocked from reports |
| 404 | The thing does not exist, or this caller may not see it |
| 409 | It clashes with the current state (already handled, a duplicate name, locked by someone else) |
| 422 | A value is not accepted (too short, too long, outside Batangas City, wrong date format). The message says which |
| 423 | The account is locked (too many wrong passwords, or locked by an Admin) |
| 429 | Too many requests. Wait the number of seconds in the `Retry-After` header |

## Example flows

**1. Sign in**

1. `POST /api/auth/sign-in` with `{"name": "Ana Cruz", "password": "..."}`. Answer: `{"token": "...", "token_type": "bearer", "user": {"id", "name", "role", "idle_timeout_minutes"}}`.
2. Keep the token in memory. Send `Authorization: Bearer <token>` from now on.
3. `GET /api/me` tells you who is signed in. On any `401`, go back to step 1.
4. `POST /api/auth/sign-out` when done.

**2. Send a hazard report (public)**

1. Send the header `X-Phone-Id: <your 16 to 64 character ID>`.
2. `POST /api/reports` with `{"kind": "hazard", "category": "Flooded road", "latitude": 13.7565, "longitude": 121.0583, "note": "Knee deep"}`. Answer `201`: `{"id", "kind", "status": "new", "label", "created_at", "message"}`.
3. `GET /api/reports/mine` lists this phone's reports and their status. `GET /api/hazards/nearby?latitude=..&longitude=..` shows hazards others can see.
4. A `403` means this phone was blocked after false reports; a `429` means wait `Retry-After` seconds.

**3. An Admin takes and resolves a help request**

1. Sign in (flow 1). `GET /api/admin/reports` lists open reports; poll it about every `refresh_seconds`.
2. `POST /api/admin/reports/{id}/take` (no body). A `409` says someone else is already handling it.
3. `POST /api/admin/reports/{id}/resolve` with `{"what_was_done": "Team sent, family moved to the gym"}`.
4. Use `mark-false` (`{"reason": "..."}`) instead of `resolve` for a false report.

**4. A user adds a place and an Admin approves it**

1. With `X-Phone-Id`, `POST /api/evacuation-centers` with `{"name", "center_type": "temporary", "max_capacity", "latitude", "longitude", ...}`. Answer `201`, with `"approval_status": "pending"`.
2. `GET /api/facilities` with the same header shows that phone its own pending place; everybody else does not see it yet.
3. An Admin signs in, `GET /api/admin/places` (the queue; `possible_duplicate` is set when a same-name center is within 30 m), then `POST /api/admin/places/{id}/approve` (or `.../reject` with an optional `reason`).
4. An Admin can fix details later with `PATCH /api/admin/places/{id}`.

This reference lists **54 endpoints** in 8 areas.


---

## Sign-in and accounts

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/auth/sign-in` | Public | Sign in with a name and password. Locked for 15 minutes after 5 wrong tries in a row. |
| `POST` | `/api/auth/sign-out` | Public (sends the token it wants to end) | Ends this sign-in. Safe to call twice. |
| `POST` | `/api/auth/change-password` | Any signed-in Admin | Change your own password. A wrong current password is refused (403) and counted toward a limit per person and per IP (429 when it is used up). Your other sign-ins end; this one stays. |
| `GET` | `/api/me` | Admin | Who is signed in. |
| `GET` | `/api/admin/users` | Admin | List Users |
| `POST` | `/api/admin/users` | Admin | Create an Admin account. There is no public sign-up. `role` is a legacy field: it is ignored (every account is an Admin) and accepted for one release only; leave it out. |
| `POST` | `/api/admin/users/{user_id}/lock` | Admin | Lock an account until an Admin unlocks it. The person is signed out right away. Not your own account, and not the last active Admin. |
| `POST` | `/api/admin/users/{user_id}/unlock` | Admin | Unlock an account (also clears a lock from too many wrong tries). |
| `POST` | `/api/admin/users/{user_id}/reset-password` | Admin | Set a new password for someone else (a forgotten password). The person is signed out everywhere and their wrong-try count and automatic lock are cleared. Tell them the new password yourself: it is never shown again. Not for your own account (use change-password). |
| `DELETE` | `/api/admin/users/{user_id}` | Admin | Remove an account. Its audit entries are kept. Not your own account, and not the last active Admin. |
| `GET` | `/api/admin/audit-log` | Admin | Newest first. The body is the same list as before; the number of entries that match the filters (before limit and offset) is in the X-Total-Count response header. |

### `POST /api/auth/sign-in`

**Who:** Public

Sign in with a name and password. Locked for 15 minutes after 5 wrong tries in a row.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required | in body; max length 100 |
| `password` | string | required | in body; max length 200 |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `token` | string | required |  |
| `token_type` | string | optional | default `bearer` |
| `user` | MeOut | required |  |

### `POST /api/auth/sign-out`

**Who:** Public (sends the token it wants to end)

Ends this sign-in. Safe to call twice.

**Request fields**

None.

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | required |  |

### `POST /api/auth/change-password`

**Who:** Any signed-in Admin

Change your own password. A wrong current password is refused (403) and counted toward a limit per person and per IP (429 when it is used up). Your other sign-ins end; this one stays.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `current_password` | string | required | in body; max length 200 |
| `new_password` | string | required | in body; max length 200 |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | required |  |

### `GET /api/me`

**Who:** Admin

Who is signed in.

**Request fields**

None.

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `idle_timeout_minutes` | integer | required |  |

### `GET /api/admin/users`

**Who:** Admin

List Users

**Request fields**

None.

**Response** `200`

A list of `UserOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### `POST /api/admin/users`

**Who:** Admin

Create an Admin account. There is no public sign-up. `role` is a legacy field: it is ignored (every account is an Admin) and accepted for one release only; leave it out.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required | in body; max length 100 |
| `password` | string | required | in body; max length 200 |
| `role` | one of `admin`, `responder`, `super_admin` or null | optional | in body; Deprecated and ignored: every account is an Admin. Accepted for one release. |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### `POST /api/admin/users/{user_id}/lock`

**Who:** Admin

Lock an account until an Admin unlocks it. The person is signed out right away. Not your own account, and not the last active Admin.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### `POST /api/admin/users/{user_id}/unlock`

**Who:** Admin

Unlock an account (also clears a lock from too many wrong tries).

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### `POST /api/admin/users/{user_id}/reset-password`

**Who:** Admin

Set a new password for someone else (a forgotten password). The person is signed out everywhere and their wrong-try count and automatic lock are cleared. Tell them the new password yourself: it is never shown again. Not for your own account (use change-password).

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | integer | required | in path |
| `new_password` | string | required | in body; max length 200 |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### `DELETE /api/admin/users/{user_id}`

**Who:** Admin

Remove an account. Its audit entries are kept. Not your own account, and not the last active Admin.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `user_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | required |  |

### `GET /api/admin/audit-log`

**Who:** Admin

Newest first. The body is the same list as before; the number of entries that match the filters (before limit and offset) is in the X-Total-Count response header.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `limit` | integer | optional | in query |
| `offset` | integer | optional | in query; Paging: skip this many entries (newest first) |
| `before_id` | integer or null | optional | in query; Paging: only entries older than this id |
| `action` | string or null | optional | in query; Only this action, e.g. user.create |
| `actor` | string or null | optional | in query; Only this exact person's name |
| `person` | string or null | optional | in query; Name search: part of a name, any capitals |
| `from` | string or null | optional | in query; First day to include, YYYY-MM-DD (UTC) |
| `to` | string or null | optional | in query; Last day to include, YYYY-MM-DD (UTC) |

**Response** `200`

A list of `AuditEntryOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `actor_id` | integer or null | optional |  |
| `actor_name` | string | required |  |
| `actor_role` | string or null | optional |  |
| `action` | string | required |  |
| `target` | string or null | optional |  |
| `detail` | any | optional |  |

Response header `X-Total-Count`: How many entries match the filters, before limit and offset.

---

## Phone blocks

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/admin/blocked-phones` | Admin | Blocked phones, newest first. `expires_at` is null when blocks never expire. |
| `POST` | `/api/admin/blocked-phones/{block_id}/unblock` | Admin | Let this phone send reports again. Its count of false reports starts from zero, so it takes a fresh set of false reports to block it again. |

### `GET /api/admin/blocked-phones`

**Who:** Admin

Blocked phones, newest first. `expires_at` is null when blocks never expire.

**Request fields**

None.

**Response** `200`

A list of `BlockedPhoneOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `blocked_at` | string (date and time, UTC) | required |  |
| `false_reports` | integer | required |  |
| `expires_at` | string (date and time, UTC) or null | optional |  |

### `POST /api/admin/blocked-phones/{block_id}/unblock`

**Who:** Admin

Let this phone send reports again. Its count of false reports starts from zero, so it takes a fresh set of false reports to block it again.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `block_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | required |  |

---

## Help requests and hazard reports

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/reports` | Public (X-Phone-Id required) | Send a help request ("kind": "help") or a hazard report ("kind": "hazard"). Both need a `category`; a help request also needs a `contact` and may have `people` and `can_move` (not allowed on a hazard). Field rules are in ReportIn. |
| `GET` | `/api/reports/mine` | Public (X-Phone-Id required) | This phone's own reports, newest first, with a status: New, Being handled or Resolved. |
| `GET` | `/api/hazards/nearby` | Public (X-Phone-Id optional) | Hazards within the near-me range (config.NEAR_ME_KM) that are Unconfirmed or Verified, as an approximate spot with a status and no details. The position you send is used for this answer only and is not stored. |
| `GET` | `/api/admin/reports` | Admin | Poll this about every `refresh_seconds` (10). `has_new_help` is true while any help request is still New: show the red "Needs help" alert. Open reports only, unless include_closed is set. A hazard is one line for all reports about the same place. |
| `POST` | `/api/admin/reports/{report_id}/take` | Admin | Take it: New -> Being handled. 409 if someone else already has it. Safe to call twice. |
| `POST` | `/api/admin/reports/{report_id}/resolve` | Admin | Resolve. Needs `what_was_done`. The sender then sees Resolved. |
| `POST` | `/api/admin/reports/{report_id}/mark-false` | Admin | Mark false. Needs a `reason`. A phone with 3 false reports is blocked from sending reports. |
| `POST` | `/api/admin/reports/{report_id}/verify` | Admin | Verify a hazard: the public then sees it as Verified. Hazards only. Safe to call twice. |

### `POST /api/reports`

**Who:** Public (X-Phone-Id required)

Send a help request ("kind": "help") or a hazard report ("kind": "hazard"). Both need a `category`; a help request also needs a `contact` and may have `people` and `can_move` (not allowed on a hazard). Field rules are in ReportIn.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | required | in header |
| `kind` | one of `help`, `hazard` | required | in body |
| `category` | string | required | in body |
| `latitude` | number | required | in body |
| `longitude` | number | required | in body |
| `contact` | string or null | optional | in body |
| `note` | string or null | optional | in body |
| `people` | integer or null | optional | in body |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved` | required |  |
| `label` | string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `message` | string | required |  |

### `GET /api/reports/mine`

**Who:** Public (X-Phone-Id required)

This phone's own reports, newest first, with a status: New, Being handled or Resolved.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | required | in header |

**Response** `200`

A list of `MyReportOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved` | required |  |
| `label` | string | required |  |
| `category` | string or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |

### `GET /api/hazards/nearby`

**Who:** Public (X-Phone-Id optional)

Hazards within the near-me range (config.NEAR_ME_KM) that are Unconfirmed or Verified, as an approximate spot with a status and no details. The position you send is used for this answer only and is not stored.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | optional | in header |
| `latitude` | number | required | in query |
| `longitude` | number | required | in query |

**Response** `200`

A list of `NearbyHazardOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `status` | one of `unconfirmed`, `verified` | required |  |
| `label` | string | required |  |
| `category` | string or null | optional |  |

### `GET /api/admin/reports`

**Who:** Admin

Poll this about every `refresh_seconds` (10). `has_new_help` is true while any help request is still New: show the red "Needs help" alert. Open reports only, unless include_closed is set. A hazard is one line for all reports about the same place.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `include_closed` | boolean | optional | in query; Also list resolved and false reports |
| `kind` | one of `help`, `hazard` or null | optional | in query |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `server_time` | string (date and time, UTC) | required |  |
| `refresh_seconds` | integer | required |  |
| `new_help_count` | integer | required |  |
| `has_new_help` | boolean | required |  |
| `latest_report_id` | integer or null | optional |  |
| `items` | array of AdminReportOut | required |  |

### `POST /api/admin/reports/{report_id}/take`

**Who:** Admin

Take it: New -> Being handled. 409 if someone else already has it. Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `report_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved`, `false` | required |  |
| `is_new_help` | boolean | required |  |
| `category` | string or null | optional |  |
| `categories` | array of string | optional | default `[]` |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contacts` | array of string | required |  |
| `notes` | array of string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `taken_by` | string or null | optional |  |
| `closed_by` | string or null | optional |  |
| `resolution_note` | string or null | optional |  |
| `false_reason` | string or null | optional |  |
| `verified` | boolean | required |  |
| `verified_by` | string or null | optional |  |
| `hazard_state` | one of `pending`, `unconfirmed`, `verified` or null | optional |  |
| `phones` | integer | required |  |
| `report_count` | integer | required |  |

### `POST /api/admin/reports/{report_id}/resolve`

**Who:** Admin

Resolve. Needs `what_was_done`. The sender then sees Resolved.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `report_id` | integer | required | in path |
| `what_was_done` | string | required | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved`, `false` | required |  |
| `is_new_help` | boolean | required |  |
| `category` | string or null | optional |  |
| `categories` | array of string | optional | default `[]` |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contacts` | array of string | required |  |
| `notes` | array of string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `taken_by` | string or null | optional |  |
| `closed_by` | string or null | optional |  |
| `resolution_note` | string or null | optional |  |
| `false_reason` | string or null | optional |  |
| `verified` | boolean | required |  |
| `verified_by` | string or null | optional |  |
| `hazard_state` | one of `pending`, `unconfirmed`, `verified` or null | optional |  |
| `phones` | integer | required |  |
| `report_count` | integer | required |  |

### `POST /api/admin/reports/{report_id}/mark-false`

**Who:** Admin

Mark false. Needs a `reason`. A phone with 3 false reports is blocked from sending reports.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `report_id` | integer | required | in path |
| `reason` | string | required | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved`, `false` | required |  |
| `is_new_help` | boolean | required |  |
| `category` | string or null | optional |  |
| `categories` | array of string | optional | default `[]` |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contacts` | array of string | required |  |
| `notes` | array of string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `taken_by` | string or null | optional |  |
| `closed_by` | string or null | optional |  |
| `resolution_note` | string or null | optional |  |
| `false_reason` | string or null | optional |  |
| `verified` | boolean | required |  |
| `verified_by` | string or null | optional |  |
| `hazard_state` | one of `pending`, `unconfirmed`, `verified` or null | optional |  |
| `phones` | integer | required |  |
| `report_count` | integer | required |  |

### `POST /api/admin/reports/{report_id}/verify`

**Who:** Admin

Verify a hazard: the public then sees it as Verified. Hazards only. Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `report_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved`, `false` | required |  |
| `is_new_help` | boolean | required |  |
| `category` | string or null | optional |  |
| `categories` | array of string | optional | default `[]` |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contacts` | array of string | required |  |
| `notes` | array of string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `taken_by` | string or null | optional |  |
| `closed_by` | string or null | optional |  |
| `resolution_note` | string or null | optional |  |
| `false_reason` | string or null | optional |  |
| `verified` | boolean | required |  |
| `verified_by` | string or null | optional |  |
| `hazard_state` | one of `pending`, `unconfirmed`, `verified` or null | optional |  |
| `phones` | integer | required |  |
| `report_count` | integer | required |  |

---

## Evacuation centers (add, remove, restore)

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/evacuation-centers` | Public (X-Phone-Id optional) | Add an evacuation center. Field rules live in schemas.EvacCenterIn. The place starts as PENDING ("approval_status": "pending"): you see it, nobody else does, until an Admin approves it. Send the X-Phone-Id header (the same one the reports use), or you will not see it again after a reload. A possible duplicate (same name within 30 m) does not stop the place: it is flagged for the Admin who reviews it. |
| `GET` | `/api/evacuation-centers/removed` | Admin | Centers that are removed right now, newest first, each with the day it will be deleted for good. |
| `DELETE` | `/api/evacuation-centers/{facility_id}` | Admin | Remove a center for everyone. Its data and status history are kept (30 days) so it can be restored. |
| `POST` | `/api/evacuation-centers/{facility_id}/restore` | Admin | Bring a removed center back on the map. |

### `POST /api/evacuation-centers`

**Who:** Public (X-Phone-Id optional)

Add an evacuation center. Field rules live in schemas.EvacCenterIn. The place starts as PENDING ("approval_status": "pending"): you see it, nobody else does, until an Admin approves it. Send the X-Phone-Id header (the same one the reports use), or you will not see it again after a reload. A possible duplicate (same name within 30 m) does not stop the place: it is flagged for the Admin who reviews it.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | optional | in header |
| `name` | string | required | in body |
| `center_type` | one of `permanent`, `temporary` | required | in body |
| `barangay` | string or null | optional | in body |
| `address` | string or null | optional | in body |
| `contact` | string or null | optional | in body |
| `max_capacity` | integer | required | in body; min 1.0; max 50000.0 |
| `latitude` | number | required | in body |
| `longitude` | number | required | in body |
| `note` | string or null | optional | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string or null | optional |  |
| `name` | string | required |  |
| `type` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `notes` | string or null | optional |  |
| `source` | string | optional | default `` |
| `center_type` | string or null | optional |  |
| `approval_status` | string | optional | default `approved` |
| `status` | StatusOut or null | optional |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `spaces_left` | integer or null | optional |  |
| `percent_full` | number or null | optional |  |
| `is_outdated` | boolean or null | optional |  |

### `GET /api/evacuation-centers/removed`

**Who:** Admin

Centers that are removed right now, newest first, each with the day it will be deleted for good.

**Request fields**

None.

**Response** `200`

A list of `RemovalOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `removed_at` | string (date and time, UTC) | required |  |
| `message` | string or null | optional |  |
| `removed_by` | string or null | optional |  |
| `delete_after` | string (date and time, UTC) or null | optional |  |
| `days_left` | integer or null | optional |  |

### `DELETE /api/evacuation-centers/{facility_id}`

**Who:** Admin

Remove a center for everyone. Its data and status history are kept (30 days) so it can be restored.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `removed_at` | string (date and time, UTC) | required |  |
| `message` | string or null | optional |  |
| `removed_by` | string or null | optional |  |
| `delete_after` | string (date and time, UTC) or null | optional |  |
| `days_left` | integer or null | optional |  |

### `POST /api/evacuation-centers/{facility_id}/restore`

**Who:** Admin

Bring a removed center back on the map.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string or null | optional |  |
| `name` | string | required |  |
| `type` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `notes` | string or null | optional |  |
| `source` | string | optional | default `` |
| `center_type` | string or null | optional |  |
| `approval_status` | string | optional | default `approved` |
| `status` | StatusOut or null | optional |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `spaces_left` | integer or null | optional |  |
| `percent_full` | number or null | optional |  |
| `is_outdated` | boolean or null | optional |  |

---

## Places review and status corrections (Admin)

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/admin/places` | Admin | Added places with their exact details. Pending ones (the default) are the queue to review, the longest-waiting first; each carries `possible_duplicate` when an existing center has the same name within 30 m. |
| `PATCH` | `/api/admin/places/{facility_id}` | Admin | Correct the details of an evacuation center that was added through the app: send only the fields to change (name, address, barangay, contact, note). A new name that matches another center within 30 m is refused (409). Centers from the map data files, hospitals and clinics cannot be edited (409). |
| `DELETE` | `/api/admin/places/{facility_id}` | Admin | Delete a removed center, or a rejected place, together with its status history, now (instead of waiting for the purge). |
| `POST` | `/api/admin/places/{facility_id}/approve` | Admin | Make a pending place public. Also undoes a rejection. Safe to call twice. |
| `POST` | `/api/admin/places/{facility_id}/reject` | Admin | Reject a pending place (the reason is optional). A place already on the map is removed instead (409). Safe to call twice. |
| `POST` | `/api/admin/facilities/{facility_id}/status-override` | Admin | Replace the latest status. Same fields as a user report plus an optional `reason`. It is added to the history as "Confirmed by official" with your name; the status it replaces stays in the history. |
| `POST` | `/api/admin/facilities/{facility_id}/capacity-correction` | Admin | Correct the maximum capacity of an evacuation center. Added to the history; users cannot change it afterwards. |
| `GET` | `/api/admin/facilities/{facility_id}/status-history` | Admin | Every row of the history, newest first, including overrides and capacity corrections, with staff names. |

### `GET /api/admin/places`

**Who:** Admin

Added places with their exact details. Pending ones (the default) are the queue to review, the longest-waiting first; each carries `possible_duplicate` when an existing center has the same name within 30 m.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | one of `pending`, `rejected` | optional | in query; Which added places to list |

**Response** `200`

A list of `PlaceAdminOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `center_type` | string | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `approval_status` | string | required |  |
| `submitted_at` | string (date and time, UTC) | required |  |
| `reviewed_by` | string or null | optional |  |
| `reviewed_at` | string (date and time, UTC) or null | optional |  |
| `reject_reason` | string or null | optional |  |
| `possible_duplicate` | DuplicateOut or null | optional |  |
| `is_removed` | boolean | optional | default `False` |
| `message` | string or null | optional |  |

### `PATCH /api/admin/places/{facility_id}`

**Who:** Admin

Correct the details of an evacuation center that was added through the app: send only the fields to change (name, address, barangay, contact, note). A new name that matches another center within 30 m is refused (409). Centers from the map data files, hospitals and clinics cannot be edited (409).

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |
| `name` | string or null | optional | in body |
| `address` | string or null | optional | in body |
| `barangay` | string or null | optional | in body |
| `contact` | string or null | optional | in body |
| `note` | string or null | optional | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `center_type` | string | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `approval_status` | string | required |  |
| `submitted_at` | string (date and time, UTC) | required |  |
| `reviewed_by` | string or null | optional |  |
| `reviewed_at` | string (date and time, UTC) or null | optional |  |
| `reject_reason` | string or null | optional |  |
| `possible_duplicate` | DuplicateOut or null | optional |  |
| `is_removed` | boolean | optional | default `False` |
| `message` | string or null | optional |  |

### `DELETE /api/admin/places/{facility_id}`

**Who:** Admin

Delete a removed center, or a rejected place, together with its status history, now (instead of waiting for the purge).

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |

**Response** `200`

`any`.


### `POST /api/admin/places/{facility_id}/approve`

**Who:** Admin

Make a pending place public. Also undoes a rejection. Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `center_type` | string | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `approval_status` | string | required |  |
| `submitted_at` | string (date and time, UTC) | required |  |
| `reviewed_by` | string or null | optional |  |
| `reviewed_at` | string (date and time, UTC) or null | optional |  |
| `reject_reason` | string or null | optional |  |
| `possible_duplicate` | DuplicateOut or null | optional |  |
| `is_removed` | boolean | optional | default `False` |
| `message` | string or null | optional |  |

### `POST /api/admin/places/{facility_id}/reject`

**Who:** Admin

Reject a pending place (the reason is optional). A place already on the map is removed instead (409). Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |
| `reason` | string or null | optional | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `center_type` | string | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `approval_status` | string | required |  |
| `submitted_at` | string (date and time, UTC) | required |  |
| `reviewed_by` | string or null | optional |  |
| `reviewed_at` | string (date and time, UTC) or null | optional |  |
| `reject_reason` | string or null | optional |  |
| `possible_duplicate` | DuplicateOut or null | optional |  |
| `is_removed` | boolean | optional | default `False` |
| `message` | string or null | optional |  |

### `POST /api/admin/facilities/{facility_id}/status-override`

**Who:** Admin

Replace the latest status. Same fields as a user report plus an optional `reason`. It is added to the history as "Confirmed by official" with your name; the status it replaces stays in the history.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |
| `status` | string | required | in body |
| `people_inside` | integer or null | optional | in body |
| `max_capacity` | integer or null | optional | in body |
| `resources` | array of string or null | optional | in body |
| `note` | string or null | optional | in body |
| `reason` | string or null | optional | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `is_outdated` | boolean | required |  |
| `source` | string | optional | default `user` |
| `source_label` | string | optional | default `Reported by a user` |
| `message` | string or null | optional |  |

### `POST /api/admin/facilities/{facility_id}/capacity-correction`

**Who:** Admin

Correct the maximum capacity of an evacuation center. Added to the history; users cannot change it afterwards.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |
| `max_capacity` | integer | required | in body; min 1.0; max 50000.0 |
| `reason` | string or null | optional | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string or null | optional |  |
| `name` | string | required |  |
| `type` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `notes` | string or null | optional |  |
| `source` | string | optional | default `` |
| `center_type` | string or null | optional |  |
| `approval_status` | string | optional | default `approved` |
| `status` | StatusOut or null | optional |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `spaces_left` | integer or null | optional |  |
| `percent_full` | number or null | optional |  |
| `is_outdated` | boolean or null | optional |  |

### `GET /api/admin/facilities/{facility_id}/status-history`

**Who:** Admin

Every row of the history, newest first, including overrides and capacity corrections, with staff names.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `facility_id` | integer | required | in path |
| `limit` | integer | optional | in query |

**Response** `200`

A list of `AdminStatusOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | string | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `source` | string | required |  |
| `source_label` | string | required |  |
| `changed_by` | string or null | optional |  |

---

## Chat

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `POST` | `/api/chat` | Public | Ask |

### `POST /api/chat`

**Who:** Public

Ask

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question` | string | required | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `answer` | string | required |  |
| `topic` | string or null | optional |  |

---

## Other

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/health` | Public | Health |
| `GET` | `/api/facilities` | Public (X-Phone-Id optional) | All facilities from every source (osm / manual / user), minus removed evacuation centers and places that are not approved. Each has its latest status (or null, with `source` and `source_label` saying who reported it) and, for evacuation centers, the capacity fields. The one extra: with an X-Phone-Id header, the places that phone added and that still wait for approval are in the list too, with "approval_status": "pending". |
| `POST` | `/api/facilities/{facility_id}/status` | Public (a signed-in Admin counts as an official) (X-Phone-Id optional) | Add a status update (kept as history). Returns the new latest status. |
| `GET` | `/api/facilities/{facility_id}/status/history` | Public (X-Phone-Id optional) | Newest first. Simple view for debugging and later use. (Admins see overrides and capacity corrections too, with names, in /api/admin/facilities/{id}/status-history.) |

### `GET /api/health`

**Who:** Public

Health

**Request fields**

None.

**Response** `200`

`any`.


### `GET /api/facilities`

**Who:** Public (X-Phone-Id optional)

All facilities from every source (osm / manual / user), minus removed evacuation centers and places that are not approved. Each has its latest status (or null, with `source` and `source_label` saying who reported it) and, for evacuation centers, the capacity fields. The one extra: with an X-Phone-Id header, the places that phone added and that still wait for approval are in the list too, with "approval_status": "pending".

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | optional | in header |

**Response** `200`

A list of `FacilityOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string or null | optional |  |
| `name` | string | required |  |
| `type` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `notes` | string or null | optional |  |
| `source` | string | optional | default `` |
| `center_type` | string or null | optional |  |
| `approval_status` | string | optional | default `approved` |
| `status` | StatusOut or null | optional |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `spaces_left` | integer or null | optional |  |
| `percent_full` | number or null | optional |  |
| `is_outdated` | boolean or null | optional |  |

### `POST /api/facilities/{facility_id}/status`

**Who:** Public (a signed-in Admin counts as an official) (X-Phone-Id optional)

Add a status update (kept as history). Returns the new latest status. Anyone can send it and it is saved as "Reported by a user". When a signed-in Admin sends it (Authorization: Bearer ...), it is saved as "Confirmed by official" with their name, and it can set the maximum capacity. A user's report cannot change a maximum capacity an official has set. A place that is still waiting for approval accepts updates only from the phone that added it (X-Phone-Id).

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | optional | in header |
| `facility_id` | integer | required | in path |
| `status` | string | required | in body |
| `people_inside` | integer or null | optional | in body |
| `max_capacity` | integer or null | optional | in body |
| `resources` | array of string or null | optional | in body |
| `note` | string or null | optional | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `is_outdated` | boolean | required |  |
| `source` | string | optional | default `user` |
| `source_label` | string | optional | default `Reported by a user` |
| `message` | string or null | optional |  |

### `GET /api/facilities/{facility_id}/status/history`

**Who:** Public (X-Phone-Id optional)

Newest first. Simple view for debugging and later use. (Admins see overrides and capacity corrections too, with names, in /api/admin/facilities/{id}/status-history.)

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `X-Phone-Id` | string (16 to 64 letters, digits, - or _) | optional | in header |
| `facility_id` | integer | required | in path |
| `limit` | integer | optional | in query |

**Response** `200`

A list of `StatusOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `is_outdated` | boolean | required |  |
| `source` | string | optional | default `user` |
| `source_label` | string | optional | default `Reported by a user` |
| `message` | string or null | optional |  |

---

## Weather, advisories, emergency numbers

| Method | Path | Who can call it | What it does |
| --- | --- | --- | --- |
| `GET` | `/api/weather` | Public | The forecast for Batangas City. `is_stale` is true (with a plain-language `notice`) when Open-Meteo could not be reached and this is the last good forecast; `fetched_at` says when it was received. 503 with a plain message when there has never been a good forecast. |
| `GET` | `/api/advisories` | Public | Pinned first, then newest first. `is_official` is true when the organization is on the official list. |
| `POST` | `/api/admin/advisories` | Admin | Create Advisory |
| `PATCH` | `/api/admin/advisories/{advisory_id}` | Admin | Update Advisory |
| `DELETE` | `/api/admin/advisories/{advisory_id}` | Admin | Delete Advisory |
| `POST` | `/api/admin/advisories/{advisory_id}/pin` | Admin | Safe to call twice. |
| `POST` | `/api/admin/advisories/{advisory_id}/unpin` | Admin | Safe to call twice. |
| `GET` | `/api/admin/advisory-sources` | Admin | The names that count as official. Starts with PAGASA, NDRRMC and Batangas City CDRRMO. |
| `POST` | `/api/admin/advisory-sources` | Admin | Add Source |
| `PATCH` | `/api/admin/advisory-sources/{source_id}` | Admin | Rename Source |
| `DELETE` | `/api/admin/advisory-sources/{source_id}` | Admin | Advisories from this source stay, but no longer show as official. |
| `GET` | `/api/emergency-numbers` | Public | In the order to show them. Only 911 until the Batangas City CDRRMO confirms the others. |
| `POST` | `/api/admin/emergency-numbers` | Admin | Add Number |
| `PUT` | `/api/admin/emergency-numbers/order` | Admin | Send every id once, in the order to show them. |
| `PATCH` | `/api/admin/emergency-numbers/{number_id}` | Admin | Update Number |
| `DELETE` | `/api/admin/emergency-numbers/{number_id}` | Admin | Remove Number |

### `GET /api/weather`

**Who:** Public

The forecast for Batangas City. `is_stale` is true (with a plain-language `notice`) when Open-Meteo could not be reached and this is the last good forecast; `fetched_at` says when it was received. 503 with a plain message when there has never been a good forecast.

**Request fields**

None.

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `location` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `current` | WeatherCurrentOut | required |  |
| `daily` | array of WeatherDayOut | required |  |
| `cyclone` | string or null | optional |  |
| `fetched_at` | string (date and time, UTC) | required |  |
| `is_stale` | boolean | required |  |
| `notice` | string or null | optional |  |
| `strip` | WeatherStripOut | required |  |

### `GET /api/advisories`

**Who:** Public

Pinned first, then newest first. `is_official` is true when the organization is on the official list.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `official` | boolean or null | optional | in query; true = only advisories from official sources (the Warnings tab) |
| `limit` | integer | optional | in query |

**Response** `200`

A list of `AdvisoryOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### `POST /api/admin/advisories`

**Who:** Admin

Create Advisory

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string | required | in body |
| `details` | string | required | in body |
| `organization` | string | required | in body |
| `source_url` | string | required | in body |
| `pinned` | boolean | optional | in body; default `False` |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### `PATCH /api/admin/advisories/{advisory_id}`

**Who:** Admin

Update Advisory

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `advisory_id` | integer | required | in path |
| `title` | string or null | optional | in body |
| `details` | string or null | optional | in body |
| `organization` | string or null | optional | in body |
| `source_url` | string or null | optional | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### `DELETE /api/admin/advisories/{advisory_id}`

**Who:** Admin

Delete Advisory

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `advisory_id` | integer | required | in path |

**Response** `204`

No body.

### `POST /api/admin/advisories/{advisory_id}/pin`

**Who:** Admin

Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `advisory_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### `POST /api/admin/advisories/{advisory_id}/unpin`

**Who:** Admin

Safe to call twice.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `advisory_id` | integer | required | in path |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### `GET /api/admin/advisory-sources`

**Who:** Admin

The names that count as official. Starts with PAGASA, NDRRMC and Batangas City CDRRMO.

**Request fields**

None.

**Response** `200`

A list of `AdvisorySourceOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |

### `POST /api/admin/advisory-sources`

**Who:** Admin

Add Source

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |

### `PATCH /api/admin/advisory-sources/{source_id}`

**Who:** Admin

Rename Source

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `source_id` | integer | required | in path |
| `name` | string | required | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |

### `DELETE /api/admin/advisory-sources/{source_id}`

**Who:** Admin

Advisories from this source stay, but no longer show as official.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `source_id` | integer | required | in path |

**Response** `204`

No body.

### `GET /api/emergency-numbers`

**Who:** Public

In the order to show them. Only 911 until the Batangas City CDRRMO confirms the others.

**Request fields**

None.

**Response** `200`

A list of `EmergencyNumberOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |
| `position` | integer | required |  |

### `POST /api/admin/emergency-numbers`

**Who:** Admin

Add Number

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `number` | string | required | in body |
| `name` | string | required | in body |
| `description` | string or null | optional | in body |

**Response** `201`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |
| `position` | integer | required |  |

### `PUT /api/admin/emergency-numbers/order`

**Who:** Admin

Send every id once, in the order to show them.

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `ids` | array of integer | required | in body |

**Response** `200`

A list of `EmergencyNumberOut`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |
| `position` | integer | required |  |

### `PATCH /api/admin/emergency-numbers/{number_id}`

**Who:** Admin

Update Number

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `number_id` | integer | required | in path |
| `number` | string or null | optional | in body |
| `name` | string or null | optional | in body |
| `description` | string or null | optional | in body |

**Response** `200`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |
| `position` | integer | required |  |

### `DELETE /api/admin/emergency-numbers/{number_id}`

**Who:** Admin

Remove Number

**Request fields**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `number_id` | integer | required | in path |

**Response** `204`

No body.

---

## Shapes used above


### AdminListOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `server_time` | string (date and time, UTC) | required |  |
| `refresh_seconds` | integer | required |  |
| `new_help_count` | integer | required |  |
| `has_new_help` | boolean | required |  |
| `latest_report_id` | integer or null | optional |  |
| `items` | array of AdminReportOut | required |  |

### AdminReportOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved`, `false` | required |  |
| `is_new_help` | boolean | required |  |
| `category` | string or null | optional |  |
| `categories` | array of string | optional | default `[]` |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contacts` | array of string | required |  |
| `notes` | array of string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `taken_by` | string or null | optional |  |
| `closed_by` | string or null | optional |  |
| `resolution_note` | string or null | optional |  |
| `false_reason` | string or null | optional |  |
| `verified` | boolean | required |  |
| `verified_by` | string or null | optional |  |
| `hazard_state` | one of `pending`, `unconfirmed`, `verified` or null | optional |  |
| `phones` | integer | required |  |
| `report_count` | integer | required |  |

### AdminStatusOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | string | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `source` | string | required |  |
| `source_label` | string | required |  |
| `changed_by` | string or null | optional |  |

### AdvisoryIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string | required |  |
| `details` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `pinned` | boolean | optional | default `False` |

### AdvisoryOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `title` | string | required |  |
| `details` | string | required |  |
| `summary` | string | required |  |
| `organization` | string | required |  |
| `source_url` | string | required |  |
| `is_official` | boolean | required |  |
| `pinned` | boolean | required |  |
| `published_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) or null | optional |  |

### AdvisorySourceIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required |  |

### AdvisorySourceOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |

### AdvisoryUpdateIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string or null | optional |  |
| `details` | string or null | optional |  |
| `organization` | string or null | optional |  |
| `source_url` | string or null | optional |  |

### AuditEntryOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `actor_id` | integer or null | optional |  |
| `actor_name` | string | required |  |
| `actor_role` | string or null | optional |  |
| `action` | string | required |  |
| `target` | string or null | optional |  |
| `detail` | any | optional |  |

### BlockedPhoneOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `blocked_at` | string (date and time, UTC) | required |  |
| `false_reports` | integer | required |  |
| `expires_at` | string (date and time, UTC) or null | optional |  |

### CapacityCorrectionIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `max_capacity` | integer | required | min 1.0; max 50000.0 |
| `reason` | string or null | optional |  |

### ChangePasswordIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `current_password` | string | required | max length 200 |
| `new_password` | string | required | max length 200 |

### ChatIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `question` | string | required |  |

### ChatOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `answer` | string | required |  |
| `topic` | string or null | optional |  |

### DuplicateOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `distance_m` | number | required |  |
| `approval_status` | string | required |  |
| `removed` | boolean | required |  |

### EmergencyNumberIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |

### EmergencyNumberOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `number` | string | required |  |
| `name` | string | required |  |
| `description` | string or null | optional |  |
| `position` | integer | required |  |

### EmergencyNumberUpdateIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `number` | string or null | optional |  |
| `name` | string or null | optional |  |
| `description` | string or null | optional |  |

### EmergencyOrderIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `ids` | array of integer | required |  |

### EvacCenterIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required |  |
| `center_type` | one of `permanent`, `temporary` | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required | min 1.0; max 50000.0 |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |

### FacilityOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string or null | optional |  |
| `name` | string | required |  |
| `type` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `notes` | string or null | optional |  |
| `source` | string | optional | default `` |
| `center_type` | string or null | optional |  |
| `approval_status` | string | optional | default `approved` |
| `status` | StatusOut or null | optional |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `spaces_left` | integer or null | optional |  |
| `percent_full` | number or null | optional |  |
| `is_outdated` | boolean or null | optional |  |

### MarkFalseIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `reason` | string | required |  |

### MeOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `idle_timeout_minutes` | integer | required |  |

### MessageOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `message` | string | required |  |

### MyReportOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved` | required |  |
| `label` | string | required |  |
| `category` | string or null | optional |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `updated_at` | string (date and time, UTC) | required |  |

### NearbyHazardOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `status` | one of `unconfirmed`, `verified` | required |  |
| `label` | string | required |  |
| `category` | string or null | optional |  |

### PlaceAdminOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `center_type` | string | required |  |
| `barangay` | string or null | optional |  |
| `address` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `max_capacity` | integer | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `note` | string or null | optional |  |
| `approval_status` | string | required |  |
| `submitted_at` | string (date and time, UTC) | required |  |
| `reviewed_by` | string or null | optional |  |
| `reviewed_at` | string (date and time, UTC) or null | optional |  |
| `reject_reason` | string or null | optional |  |
| `possible_duplicate` | DuplicateOut or null | optional |  |
| `is_removed` | boolean | optional | default `False` |
| `message` | string or null | optional |  |

### PlaceEditIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string or null | optional |  |
| `address` | string or null | optional |  |
| `barangay` | string or null | optional |  |
| `contact` | string or null | optional |  |
| `note` | string or null | optional |  |

### RejectIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `reason` | string or null | optional |  |

### RemovalOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `key` | string | required |  |
| `name` | string | required |  |
| `removed_at` | string (date and time, UTC) | required |  |
| `message` | string or null | optional |  |
| `removed_by` | string or null | optional |  |
| `delete_after` | string (date and time, UTC) or null | optional |  |
| `days_left` | integer or null | optional |  |

### ReportIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `kind` | one of `help`, `hazard` | required |  |
| `category` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `contact` | string or null | optional |  |
| `note` | string or null | optional |  |
| `people` | integer or null | optional |  |
| `can_move` | one of `yes`, `no`, `unsure` or null | optional |  |

### ReportSentOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `kind` | one of `help`, `hazard` | required |  |
| `status` | one of `new`, `being_handled`, `resolved` | required |  |
| `label` | string | required |  |
| `created_at` | string (date and time, UTC) | required |  |
| `message` | string | required |  |

### ResetPasswordIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `new_password` | string | required | max length 200 |

### ResolveIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `what_was_done` | string | required |  |

### SignInIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required | max length 100 |
| `password` | string | required | max length 200 |

### SignInOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `token` | string | required |  |
| `token_type` | string | optional | default `bearer` |
| `user` | MeOut | required |  |

### StatusIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string or null | optional |  |
| `note` | string or null | optional |  |

### StatusOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string | optional | default `[]` |
| `note` | string or null | optional |  |
| `updated_at` | string (date and time, UTC) | required |  |
| `is_outdated` | boolean | required |  |
| `source` | string | optional | default `user` |
| `source_label` | string | optional | default `Reported by a user` |
| `message` | string or null | optional |  |

### StatusOverrideIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | string | required |  |
| `people_inside` | integer or null | optional |  |
| `max_capacity` | integer or null | optional |  |
| `resources` | array of string or null | optional |  |
| `note` | string or null | optional |  |
| `reason` | string or null | optional |  |

### UserCreateIn

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `name` | string | required | max length 100 |
| `password` | string | required | max length 200 |
| `role` | one of `admin`, `responder`, `super_admin` or null | optional | Deprecated and ignored: every account is an Admin. Accepted for one release. |

### UserOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | integer | required |  |
| `name` | string | required |  |
| `role` | string | required |  |
| `status` | one of `active`, `locked_by_admin`, `locked_for_wrong_tries` | required |  |
| `locked_until` | string (date and time, UTC) or null | optional |  |
| `created_at` | string (date and time, UTC) | required |  |
| `created_by` | string or null | optional |  |
| `last_sign_in_at` | string (date and time, UTC) or null | optional |  |
| `message` | string or null | optional |  |

### WeatherCurrentOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `temperature_c` | number | required |  |
| `feels_like_c` | number or null | optional |  |
| `humidity_percent` | number or null | optional |  |
| `wind_kph` | number | required |  |
| `wind_gust_kph` | number or null | optional |  |
| `rain_mm` | number | required |  |
| `weather_code` | integer | required |  |
| `condition` | string | required |  |
| `is_day` | boolean or null | optional |  |

### WeatherDayOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `date` | string | required |  |
| `temp_max_c` | number | required |  |
| `temp_min_c` | number | required |  |
| `rain_mm` | number | required |  |
| `rain_chance_percent` | number or null | optional |  |
| `wind_max_kph` | number or null | optional |  |
| `weather_code` | integer | required |  |
| `condition` | string | required |  |

### WeatherOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `location` | string | required |  |
| `latitude` | number | required |  |
| `longitude` | number | required |  |
| `current` | WeatherCurrentOut | required |  |
| `daily` | array of WeatherDayOut | required |  |
| `cyclone` | string or null | optional |  |
| `fetched_at` | string (date and time, UTC) | required |  |
| `is_stale` | boolean | required |  |
| `notice` | string or null | optional |  |
| `strip` | WeatherStripOut | required |  |

### WeatherStripOut

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `headline` | string | required |  |
| `detail` | string | required |  |
