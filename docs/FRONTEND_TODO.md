# SILONG frontend to-do

Checklist for connecting the existing screens to the server and building the missing staff screens.
Facts come from `docs/API.md`, `docs/REDESIGN.md`, `README.md`, `CHANGELOG.md` (Updates 9 to 12) and the code in `frontend/src`, `backend/app`.
Where the docs and the code disagree, the code is what this file follows, and it says so.
"(check)" means: not confirmed, look before you build.

## 1. How to use this file

- The backend is done and tested (parts 1 to 5). `docs/API.md` and http://127.0.0.1:8000/docs describe every route.
- Work top to bottom: plumbing (3), existing screens (4), missing screens (5). Sizes and phases are in 6, open questions in 7.
- Do not change a field name or a route to fit a screen. If the server must change, tell the backend owner.

## 2. Setup for the frontend developer

- [ ] Run the backend (README, "How to run it"): `cd backend`, `pip install -r requirements.txt`, `uvicorn app.main:app --reload --port 8000`. On Windows use `py -m ...`.
  - check it: `GET /api/health` answers `{"status": "ok"}` (`api.health()` in `client.ts`)
- [ ] Create the first Super admin once: `py scripts/create_super_admin.py` (README, "Staff accounts and roles"). It uses `typhoon.db` in the folder you run it from.
- [ ] Load demo data into a separate file (README, "Operations"):
  - `py scripts/seed_demo.py --db demo.db --with-demo-staff`
  - start the backend with `DATABASE_URL=sqlite:///./demo.db` (or put it in `backend/.env`)
  - it makes the staff accounts "Demo Responder" and "Demo Super Admin" and prints their passwords once
  - it refuses `typhoon.db` unless you add `--force`; do not
- [ ] Set `VITE_API_URL` in `frontend/.env` if the backend is not at `http://127.0.0.1:8000/api` (the default in `src/api/client.ts`). It is not listed in `frontend/.env.example`.
- [ ] Set `VITE_MAPTILER_KEY` (README, "Map setup"). The key's allowed origin is the host name only, for example `localhost`, without `http://`.
- [ ] GPS needs a secure page. `http://localhost` works. `http://192.168.x.x` does not. For a real phone use USB and port forwarding so the phone opens `localhost` (`docs/REDESIGN.md`, "Testing on a phone").
- [ ] Optional: `VITE_SUPPORT_EMAIL`, `VITE_SUPPORT_PHONE` (read in `MenuPages.tsx`, not in `.env.example`). The backend has no support-contact setting (see 5.4).
- Browser calls from another origin are allowed (`backend/app/main.py`: CORS allows all origins and headers). Only `X-Total-Count` is exposed to the browser.

## 3. Shared plumbing (do this first)

### 3.1 Phone ID

- [ ] Make one random ID per browser, once, and keep it. Format: 16 to 64 letters, digits, `-` or `_` (API.md, "Phone ID"). A UUID (36 characters) fits.
- [ ] Send it as the header `X-Phone-Id`. The server stores only a hash. It is not proof of identity. Clearing browser data makes a new one.
- [ ] There is no phone ID code in `frontend/src` today.

Calls that take it (API.md):

| Call | Header |
| --- | --- |
| `POST /api/reports` | required (400 without) |
| `GET /api/reports/mine` | required (400 without) |
| `GET /api/hazards/nearby` | optional |
| `GET /api/facilities` | optional, but without it the phone never sees its own pending places |
| `POST /api/evacuation-centers` | optional, but without it the place is saved and this phone never sees it again |
| `POST /api/facilities/{facility_id}/status` | optional, but a pending place accepts updates only from the phone that added it |
| `GET /api/facilities/{facility_id}/status/history` | optional |

- [ ] Send it on all seven. No other route lists it (chat, weather, advisories, emergency numbers and every staff route do not).
- [ ] `MapPage.tsx` refreshes `getFacilities()` every 60 seconds (`REFRESH_MS`). Each refresh needs the header, or a pending place disappears at the next refresh.

### 3.2 Central request helper (`src/api/client.ts`)

Today `request()` only does `fetch(BASE_URL + path, init)`. It has no headers of its own.

- [ ] Add `X-Phone-Id` to the seven calls above.
- [ ] Add `Authorization: Bearer <token>` when staff are signed in, on every staff route.
- [ ] `POST /api/facilities/{facility_id}/status` with a token is saved as "Confirmed by official". A wrong or expired token there counts as a user, not an error (API.md).
- [ ] Keep `ApiError` and `messageFromBody()`. They already handle `detail` as a string and as a 422 list.
- [ ] Add `retryAfter` (seconds) to `ApiError` for 429. See 7: the browser may not be able to read the header.
- [ ] Remove the stale comment above `askSilo` ("ASSUMPTION ... routes.py ... not in this copy"). The route is `POST /api/chat` and the code already matches.
- [ ] Add the missing methods for sections 4 and 5. Today `client.ts` has: health, facilities, status, add, remove, removed list, restore, chat.

### 3.3 Errors (body is `{"detail": "<plain message>"}`; a 422 body is a list)

| Code | Meaning (API.md) | What the screen shows |
| --- | --- | --- |
| 0 | server not reached (`ApiError` status 0, already in `client.ts`) | existing "Can't reach the server" message |
| 400 | `X-Phone-Id` missing or badly formed | a plain error; this is an app bug, not the person's mistake |
| 401 | not signed in, or the sign-in ran out | staff: drop the token, go to sign in |
| 403 | wrong role, wrong current password, or this phone is blocked from reports | `detail` |
| 404 | does not exist, or this caller may not see it | `detail` |
| 409 | clashes with the current state (already taken, duplicate name, already added) | `detail` |
| 422 | a value is not accepted | `detail` (first message; `messageFromBody` does this) |
| 423 | account locked | `detail` on the sign-in form |
| 429 | too many requests | `detail`; disable the button for `Retry-After` seconds if it can be read |

- [ ] Show `detail` as written. Do not rewrite server messages. (`EvacCenterForm.friendlyError` strips "(id N)" and "(POST ...)" from the old duplicate message; see 4.2.)

### 3.4 Staff token

- [ ] Keep it in memory (API.md, flow 1: "Keep the token in memory"). A reload means sign in again. Other places are a decision, see 7.
- [ ] Idle sign-out is 30 minutes without any request; each request restarts it. `user.idle_timeout_minutes` in the sign-in answer says the number.
- [ ] Any `401` on a staff call: clear the token and go to the sign-in screen.
- [ ] Sign out: `POST /api/auth/sign-out` (sends the token), then drop it. Safe to call twice.

### 3.5 Times and ids

- [ ] Times are ISO strings marked UTC. Convert with `new Date(iso)` (`statusInfo.timeAgo` and `clockTime` already do). Checked in code for reports, status, advisories, accounts. Places and removal times: (check).
- [ ] Screens that want a `Date`: `WarningItem.issuedAt`, `UpdateItem.publishedAt`, `WeatherTab.lastUpdated`.
- [ ] Advisory `id` is a number. `WarningItem.id` and `UpdateItem.id` are strings: use `String(id)`.
- [ ] Facility, report, place and number ids are numbers in the API and in `types/index.ts` (`Facility.id`). No conversion there.

## 4. Existing screens to connect

### 4.1 Incident form: `components/IncidentPanel.tsx`

Today: validates, then `saveReport()` writes to localStorage (`REPORTS_KEY` in `myActivity.ts`). Nothing is sent. Footnote says "Saved on this phone for now".

- [ ] On submit call `POST /api/reports` with `X-Phone-Id`. Remove `saveReport()`.
- [ ] Replace the texts "Request saved on this phone" and "Report saved on this phone" and the hazard footnote with the server's `message` (answer has `id`, `kind`, `status`, `label`, `created_at`, `message`).

| Form | API | Rule |
| --- | --- | --- |
| `mode` | `kind` (`help` or `hazard`) | required |
| `kind` (chip or typed text) | `category` | required, 1 to 40 characters |
| `details` | `note` | optional, server max 140 |
| `contact` | `contact` | required for help, max 60; leave out for a hazard (the form does not ask) |
| `people` | `people` | help only, 1 to 999 (form: 1 to 99) |
| `canMove` | `can_move` | help only; `yes`, `no` or `unsure` (form: yes or no, required) |
| `point.lat`, `point.lng` | `latitude`, `longitude` | must be inside Batangas City (south 13.60, west 120.97, north 13.86, east 121.18 in `config.py`), else 422 |

- [ ] A hazard with `people` or `can_move` is refused (422). The form already keeps them in help mode only. Do not send them on a hazard.
- [ ] Any other field is refused (422): no name, no photo.
- [ ] Limits do **not** match. Form: details 200 (`MAX_DETAILS`), kind 60 (`MAX_KIND`). Server: note 140 (`REPORT_NOTE_MAX`), category 40 (`REPORT_CATEGORY_MAX`). Lower both in the form (or see 7).
- [ ] 403 means the phone is blocked after 3 false reports. 429 means wait (per-phone and per-IP limits in `config.py`: `REPORT_PHONE_COOLDOWN_SECONDS`, `REPORT_PHONE_MAX`, `REPORT_IP_MAX`).
- [ ] Keep the "Call 911" strip and the GPS texts as they are.

### 4.2 Add place: `components/EvacCenterForm.tsx`, `AddEvacCenter.tsx`, `evacCenterDraft.ts`; `api.addEvacuationCenter`; `MapPage.handleAdded`

Today: `POST /evacuation-centers` with no header. On success the page adds the pin, shows "Evacuation center added." and calls `rememberMyPlace()`.

- [ ] Call `POST /api/evacuation-centers` with `X-Phone-Id`.
- [ ] Field names already match the API: `name`, `center_type`, `barangay`, `address`, `contact`, `max_capacity`, `latitude`, `longitude`, `note`. Capacity 1 to 50000 matches.
- [ ] The answer is `201` with `approval_status: "pending"`. Add `approval_status` to `Facility` in `types/index.ts`.
- [ ] Change the toast "Evacuation center added." to say it waits for approval and only this phone sees it.
- [ ] A possible duplicate (same name within 30 m) is **not** a 409 any more. The answer has no duplicate flag; only staff see it. Remove the duplicate/"restore it instead" handling in `friendlyError()`.
- [ ] Errors that can happen now:
  - 409 "You already added this place. It is waiting for approval by a responder."
  - 429 when 5 places already wait (`PENDING_PLACES_PER_PHONE`)
  - 429 per IP or phone, with `Retry-After`
- [ ] Without the header the place is still saved but only staff will ever see it. Do not allow that case.

### 4.3 Status form: `components/StatusForm.tsx`; `api.submitStatus`; `MapPage.handleSaved`; `statusInfo.ts`

- [ ] Call `POST /api/facilities/{facility_id}/status` with `X-Phone-Id`. Body fields already match: `status`, `people_inside`, `max_capacity`, `resources`, `note`.
- [ ] Add `source` and `source_label` to `FacilityStatus`. The answer has them: "Reported by a user" or "Confirmed by official".
- [ ] Show `source_label` in `FacilityPanel.tsx` (next to "Last updated"). Nothing in `frontend/src` reads it today.
- [ ] **Label bug confirmed.** `StatusForm.tsx` has two inputs both labelled "Maximum capacity (optional)". The first one holds `people` (placeholder "e.g. 85", error text "People inside must be a whole number"). Rename its label to "People inside".
- [ ] `message` in the answer is already shown by `handleSaved` (8 seconds). Keep it. It is how the user learns the server changed what was sent (for example "full" because people reached capacity).
- [ ] After an official sets a capacity, a user's `max_capacity` is ignored. The form always sends the field; this is expected (REDESIGN).
- [ ] `resources` is only sent for evacuation centers (the form does that today).

### 4.4 Map pins and facility panel: `pages/MapPage.tsx`, `components/StatusPanel.css`, `MapPins.css`, `FacilityPanel.tsx`, `CapacityIndicator.tsx`

Pin looks from `docs/REDESIGN.md`, compared with the code:

| Look | Meaning | In code today |
| --- | --- | --- |
| hollow | no status yet | `data-status="unknown"` rule in `MapPins.css` |
| dashed and dim | update older than 6 hours | `data-outdated` rules in `StatusPanel.css` (from `status.is_outdated`) |
| small blue ring | added through the app | `data-source="user"` rule in `StatusPanel.css` |
| dashed blue | waiting for approval, only the sender sees it | **not built** |

- [ ] Read `approval_status` from `GET /api/facilities` and set a data attribute on the pin. Add the dashed blue rule.
- [ ] In `FacilityPanel.tsx` say a pending place is waiting for approval and only this phone sees it.
- [ ] A pending place only comes back from `GET /api/facilities` when the header is sent (3.1).
- [ ] `FacilityList.tsx` and the search use the same list: decide if pending places show there (check).
- [ ] Show "Confirmed by official" vs "Reported by a user" (4.3).

### 4.5 Weather tab and strip: `components/WeatherTab.tsx`, `WeatherStrip.tsx`, `AlertsSheet.tsx`, `pages/MapPage.tsx`

Today: `AlertsSheet.tsx` has `WEATHER_STATUS = "unavailable"` fixed and passes empty props. `WeatherTab` has a `children` slot for "weather cards", but no weather card component exists. `MapPage` renders `<WeatherStrip onOpen={...} />` with no headline or detail. `client.ts` has no weather call.

- [ ] Add `api.getWeather()`: `GET /api/weather` (no header, cached 10 minutes by the server).
- [ ] Answer fields: `location`, `latitude`, `longitude`, `current` (`temperature_c`, `feels_like_c`, `humidity_percent`, `wind_kph`, `wind_gust_kph`, `rain_mm`, `weather_code`, `condition`, `is_day`), `daily[]` (`date`, `temp_max_c`, `temp_min_c`, `rain_mm`, `rain_chance_percent`, `wind_max_kph`, `weather_code`, `condition`), `cyclone`, `fetched_at`, `is_stale`, `notice`, `strip` (`headline`, `detail`).
- [ ] Map to `WeatherTab`: `status` loading, ready or error; `errorMessage` from `detail`; `lastUpdated = new Date(fetched_at)`; `location`; `cyclone`.
- [ ] Build the weather cards for the `children` slot (current and daily list). Use `condition` text. No icon mapping from `weather_code` is defined anywhere (check).
- [ ] When `is_stale` is true, show `notice` and the `fetched_at` time. `WeatherTab` has no prop for it yet.
- [ ] 503 means no good forecast has ever been received. Show `detail` in the error state.
- [ ] `cyclone` is always null on the server. The tab already shows "Not available right now. Check PAGASA." Keep it.
- [ ] `WeatherStrip`: pass `strip.headline` and `strip.detail`. It needs the data before the sheet is opened, so fetch in `MapPage` (or share one fetch with the sheet).
- [ ] The Refresh button (`onRefresh`) calls `getWeather()` again.

### 4.6 Alerts sheet: `components/AlertsSheet.tsx`

- [ ] Delete the block marked "TEMPORARY, FOR A SCREENSHOT ONLY. DELETE BEFORE SUBMITTING" (`UPDATE_SAMPLE`).
- [ ] Replace the three fixed constants `WEATHER_STATUS`, `WARNINGS_STATUS`, `UPDATES_STATUS` and the empty `onRefresh` / `onRetry` props with real state and calls.
- [ ] Warnings tab: `GET /api/advisories?official=true`. Updates tab: `GET /api/advisories` (check that this is the split the design wants; the API only says `official=true` is "the Warnings tab").
- [ ] `limit` is an optional query field on `GET /api/advisories`.

### 4.7 Warnings and Updates tabs: `components/WarningsTab.tsx`, `UpdatesTab.tsx`

Advisory answer (`GET /api/advisories`): `id`, `title`, `details`, `summary`, `organization`, `source_url`, `is_official`, `pinned`, `published_at`, `updated_at`. Server order: pinned first, then newest. `summary` has the same text as `details` (`content_schemas.py`): `UpdatesTab` reads `summary`, `WarningsTab` reads `details`.

Mismatches listed in CHANGELOG Update 11, checked against the code:

| CHANGELOG says | Code | Do |
| --- | --- | --- |
| `UpdatesTab` sorts official first and ignores pinned | **true**: sorts by `isOfficial`, then `publishedAt` | [ ] Follow the server order, or sort pinned first (decision, 7) |
| always shows "AI-summarized" chip and an AI note | **true**: `<span className="ai-chip">` on every card, and the footer says summaries are generated by AI | [ ] Remove both for hand-written advisories (decision, 7) |
| needs a link on every card | **true**: `sourceUrl` is required in `UpdateItem` | [ ] No change: the server requires `source_url` |
| advisory `id` is a number, screens type it as string | **true**: `id: string` in both item types | [ ] `String(id)` |
| times are ISO UTC, screens expect `Date` | **true**: `issuedAt`, `publishedAt` are `Date` | [ ] `new Date(published_at)` |
| `AlertsSheet` uses fixed unavailable states and sample data | **true** (4.6) | [ ] see 4.6 |
| `WeatherStrip` takes `headline` and `detail`, the server sends `strip` | **true** (4.5) | [ ] see 4.5 |

More found in the code:

- [ ] `WarningsTab` field map: `title`, `details`, `organization`, `issuedAt` from `published_at`, `bulletinUrl` from `source_url`.
- [ ] `UpdatesTab` field map: `organization`, `publishedAt` from `published_at`, `summary`, `sourceUrl` from `source_url`, `isOfficial` from `is_official`.
- [ ] `WarningsTab` shows the "Official" badge on every card without reading `is_official`. Fine if only `?official=true` data goes in. (check)
- [ ] `WarningsTab` empty state says "no official weather warnings issued ... Source: PAGASA". Advisories are posted by hand and nothing is fetched automatically (README), so this may say more than the server knows. (check wording)
- [ ] `WarningsTab` needs a `lastChecked` date. The server has none. Use the time of the fetch. (check)
- [ ] `pinned` and `updated_at` are not shown anywhere. Whether to show them is not in the docs. (check)

### 4.8 Emergency hotlines: `components/EmergencyHotlines.tsx`, `hotlineData.ts`

Today: `NATIONAL_HOTLINES` is hardcoded with 911 "National Emergency" and 143 "Philippine Red Cross". The database has 911 only. 143 is not confirmed (REDESIGN, CHANGELOG Update 11).

- [ ] Add `api.getEmergencyNumbers()`: `GET /api/emergency-numbers`. Items: `id`, `number`, `name`, `description`, `position`. Already in display order.
- [ ] Replace `NATIONAL_HOTLINES` with this list. `description` is not shown today; show it or not (check).
- [ ] The 143 line goes away unless a Super admin adds it (7).
- [ ] If the call fails, 911 must still be reachable. Other screens already have a static "Call 911" (`IncidentPanel`). What `EmergencyHotlines` shows on failure is not decided. (check)
- [ ] Local hotlines come from the facilities already loaded (`buildLocalHotlines`, hospitals and clinics with a phone). No change.

### 4.9 Chat: `components/AskSiloPanel.tsx`; `api.askSilo`

- [ ] Shape already matches: `POST /api/chat` with `{question}` gives `{answer, topic}` (`SiloAnswer`). `topic` null means no guide entry matched.
- [ ] Question limit: `MAX_LENGTH = 200` equals `CHAT_MAX_QUESTION_LENGTH` (200). No change.
- [ ] **Ending line shows twice.** The answer text ends with "AI-generated. Follow official advisories first." and the footer (`AskSiloPanel.tsx`, online state) shows the same line. Remove one (decision, 7).
- [ ] 429: 15 questions per 10 minutes per IP. The retry button is enabled for 429 (`canRetry: true`). Use `Retry-After` if it can be read (7).
- [ ] The 404, 405 and 501 "Silo is not available yet" branch is no longer needed; harmless.
- [ ] **"Report a wrong answer" is not wired and there is no endpoint for it.** The button is already `disabled` in the options sheet. Keep it disabled or hide it. Do not call anything.
- [ ] Answers today are a fixed placeholder (no AI). Do not write UI that assumes follow-ups, history or place status.

### 4.10 My reports and my places: `components/myActivity.ts`, `MenuPages.tsx`, `HamburgerMenu.tsx`

Today both lists are read from localStorage by sync loaders (`loadMyReports`, `loadMyPlaces`) when the menu opens. Reports show "Saved on this phone". Places show "On the map".

My reports:

- [ ] Call `GET /api/reports/mine` with `X-Phone-Id`. Items: `id`, `kind`, `status` (`new`, `being_handled`, `resolved`), `label`, `category`, `latitude`, `longitude`, `note`, `created_at`, `updated_at`.
- [ ] Map to the list: `kind` to the "Needs help"/"Hazard" tag, `category` to the title, `label` instead of "Saved on this phone", `created_at` to "Sent ... ago".
- [ ] The loaders become async: add loading and error states. `HamburgerMenu` uses them in `useState(loadMyReports)`.
- [ ] Stop writing `REPORTS_KEY` (4.1). Remove the "kept on this phone" note for reports. Reports are deleted by the server after `REPORTS_KEEP_DAYS` (30).
- [ ] How a report marked false shows in this list is not in the docs. (check)

My places:

- [ ] There is no "my places" endpoint. Use `GET /api/facilities` with `X-Phone-Id`: this phone's pending places come back with `approval_status: "pending"`.
- [ ] Keep `PLACES_KEY` (ids saved by `rememberMyPlace`) to know which facilities are the phone's own. Replace the fixed "On the map" with "Waiting for approval" or "On the map" from `approval_status`.
- [ ] A rejected place is not in `GET /api/facilities` and there is no call that says it was rejected. The list cannot tell "rejected" from "gone". (check, see 7)

### 4.11 Hide on this phone: `components/hiddenCenters.ts`, `FacilityPanel.tsx`, `MapPage.handleHide`

- [ ] Nothing to connect. It never calls the server. It is kept in localStorage (`silong:hidden-centers`) and clearing browser data undoes it.
- [ ] Evacuation centers only. Hospitals and clinics cannot be hidden (`toHiddenCenter`).
- [ ] Do not add a server call. Hiding for everyone is a staff action (4.12, 5.2).

### 4.12 Removed centers: `components/RemovedCenters.tsx`

- [ ] **It is not mounted anywhere** (only defined; `getRemovedCenters` and `restoreEvacuationCenter` are used only inside it).
- [ ] Its three routes are staff only now (401 or 403 without a sign-in): `GET /api/evacuation-centers/removed`, `DELETE /api/evacuation-centers/{facility_id}`, `POST /api/evacuation-centers/{facility_id}/restore`. `client.ts` sends no `Authorization` header on them.
- [ ] Do not mount it on the public map. Reuse it inside the responder places screen (5.2).
- [ ] `RemovedCenter` in `types/index.ts` lacks `removed_by`, `delete_after`, `days_left` (the server sends them).

### 4.13 Admin sign in link: `components/HamburgerMenu.tsx`, `pages/AdminSignInPage.tsx`

- [ ] The menu row "Admin sign in" goes to `/admin`. The page is a placeholder that says sign-in is not available. Built in 5.1.

## 5. Missing screens to build

### 5.1 Staff sign in and change password (all staff)

Route `/admin` exists in `App.tsx`. Replace the placeholder `AdminSignInPage`.

- [ ] Sign in: `POST /api/auth/sign-in` with `name` (max 100, not case sensitive) and `password` (max 200). Answer: `token`, `token_type`, `user` (`id`, `name`, `role`, `idle_timeout_minutes`).
- [ ] 401 wrong name or password (same message for both). 423 account locked (5 wrong tries in a row lock it for 15 minutes; a Super admin can also lock it). 429 sign-ins per IP (20 per 10 minutes).
- [ ] `GET /api/me` says who is signed in (`id`, `name`, `role`, `idle_timeout_minutes`).
- [ ] Send responders to the responder screens, Super admins to the Super admin screens. Role checks are done by the server (403); hiding screens is only convenience.
- [ ] Change password: `POST /api/auth/change-password` with `current_password`, `new_password`. A wrong current password is 403 and counted (5 per person and 20 per IP per 10 minutes, then 429). New password: at least 8 characters (`MIN_PASSWORD_LENGTH`) and different from the current one. Your other sign-ins end; this one stays.
- [ ] Sign out button: `POST /api/auth/sign-out`.

### 5.2 Responder screens (phone first; also work on a computer)

Reports list:

- [ ] `GET /api/responder/reports` (query `include_closed`, `kind`). Poll every `refresh_seconds` from the answer (10), not a fixed number.
- [ ] Red "Needs help" alert while `has_new_help` is true. `new_help_count` and `latest_report_id` are in the answer.
- [ ] Item fields: `id`, `kind`, `status` (`new`, `being_handled`, `resolved`, `false`), `is_new_help`, `category`, `categories`, `people`, `can_move`, `latitude`, `longitude`, `contacts`, `notes`, `created_at`, `updated_at`, `taken_by`, `closed_by`, `resolution_note`, `false_reason`, `verified`, `verified_by`, `hazard_state` (`pending`, `unconfirmed`, `verified`), `phones`, `report_count`.
- [ ] A hazard is one line for all reports about the same place (within 100 m). Show `report_count`, `phones`, every `categories` value, all `contacts` and `notes`.
- [ ] Take: `POST /api/responder/reports/{report_id}/take`, no body. 409 means someone else has it. Safe to call twice.
- [ ] Call: a `tel:` link from `contacts`. No endpoint.
- [ ] Navigate: a link with `latitude` and `longitude`. No endpoint. Which maps app is not decided. (check)
- [ ] Resolve: `POST /api/responder/reports/{report_id}/resolve` with `what_was_done` (3 to 500 characters). Ask the responder what was done first.
- [ ] Mark false: `POST /api/responder/reports/{report_id}/mark-false` with `reason` (3 to 500). Ask for the reason first. 3 false reports from one phone block that phone.
- [ ] Verify a hazard: `POST /api/responder/reports/{report_id}/verify`, no body, hazards only, safe to call twice. The public then sees "Verified".
- [ ] Rules from REDESIGN: exact location and contact are visible to staff only; the site cannot text or page anyone; the page is not a replacement for 911.

Places to review:

- [ ] `GET /api/responder/places` (default: pending, longest waiting first; `status=rejected` lists rejected). Item fields: `id`, `key`, `name`, `center_type`, `barangay`, `address`, `contact`, `max_capacity`, `latitude`, `longitude`, `note`, `approval_status`, `submitted_at`, `reviewed_by`, `reviewed_at`, `reject_reason`, `possible_duplicate`, `is_removed`, `message`.
- [ ] Show `possible_duplicate` (`name`, `distance_m`, `approval_status`, `removed`) so the reviewer sees the other place.
- [ ] Approve: `POST /api/responder/places/{facility_id}/approve`. Also undoes a rejection. Safe to call twice.
- [ ] Reject: `POST /api/responder/places/{facility_id}/reject` with an optional `reason`. A place already on the map gets 409 (remove it instead).
- [ ] Edit details: `PATCH /api/responder/places/{facility_id}` with only the changed fields of `name`, `address`, `barangay`, `contact`, `note`. 409 when a new name matches another center within 30 m, or the place is a hospital, a clinic or from the data files.

Status override and capacity:

- [ ] Override latest status: `POST /api/responder/facilities/{facility_id}/status-override` (`status`, `people_inside`, `max_capacity`, `resources`, `note`, optional `reason`). Saved as "Confirmed by official" with the name; the old status stays in the history.
- [ ] Correct capacity: `POST /api/responder/facilities/{facility_id}/capacity-correction` (`max_capacity` 1 to 50000, optional `reason`). Users cannot change it afterwards.
- [ ] History: `GET /api/responder/facilities/{facility_id}/status-history` (optional `limit`). Fields include `kind`, `source`, `source_label`, `changed_by`.
- [ ] A normal status update with a token (`POST /api/facilities/{facility_id}/status`) is also "Confirmed by official" and is not held back by the per-place cooldown (REDESIGN).

Removed places:

- [ ] List: `GET /api/evacuation-centers/removed` (`days_left`, `delete_after`, `removed_by`). Remove: `DELETE /api/evacuation-centers/{facility_id}`. Restore: `POST /api/evacuation-centers/{facility_id}/restore`.
- [ ] Removing hides the center for everyone and keeps it 30 days. A pending place cannot be removed (409): reject it.

### 5.3 Super admin screens (computer only)

Also everything in 5.2.

Advisories (`AdvisoryIn`: `title` max 120, `details` max 1000, `organization` max 80, `source_url` http or https max 500, `pinned`):

- [ ] Create `POST /api/admin/advisories`. Edit `PATCH /api/admin/advisories/{advisory_id}` (`title`, `details`, `organization`, `source_url`; not `pinned`). Delete `DELETE /api/admin/advisories/{advisory_id}`.
- [ ] Pin `POST /api/admin/advisories/{advisory_id}/pin`. Unpin `POST /api/admin/advisories/{advisory_id}/unpin`. Both safe to call twice.
- [ ] Official sources: `GET /api/admin/advisory-sources`, `POST /api/admin/advisory-sources` (`name`), `PATCH /api/admin/advisory-sources/{source_id}`, `DELETE /api/admin/advisory-sources/{source_id}`. An advisory is official when its `organization` matches a listed name (case and extra spaces ignored). Removing a source keeps its advisories but they stop showing as official. Starts with PAGASA, NDRRMC, Batangas City CDRRMO.

Emergency numbers (`number` max 30, `name` max 80, `description` max 140):

- [ ] Add `POST /api/admin/emergency-numbers`. Edit `PATCH /api/admin/emergency-numbers/{number_id}`. Remove `DELETE /api/admin/emergency-numbers/{number_id}`.
- [ ] Order: `PUT /api/admin/emergency-numbers/order` with `ids`: every id once, in the order to show.

Accounts:

- [ ] List `GET /api/admin/users` (`status`: `active`, `locked_by_admin`, `locked_for_wrong_tries`; `locked_until`, `created_by`, `last_sign_in_at`).
- [ ] Create `POST /api/admin/users` (`name`, `password`, `role` `responder` or `super_admin`).
- [ ] Lock `POST /api/admin/users/{user_id}/lock`. Unlock `POST /api/admin/users/{user_id}/unlock` (also clears a wrong-tries lock).
- [ ] Reset password `POST /api/admin/users/{user_id}/reset-password` (`new_password`). The person is signed out everywhere. The Super admin must tell them the password: it is never shown again. Not for your own account.
- [ ] Remove `DELETE /api/admin/users/{user_id}`. Audit entries stay. You cannot lock or remove your own account (README).

Audit log:

- [ ] `GET /api/admin/audit-log`, newest first. Query: `limit`, `offset`, `before_id`, `action`, `actor` (exact name), `person` (part of a name), `from`, `to` (`YYYY-MM-DD`, UTC; a bad date is 422).
- [ ] Read the total from the `X-Total-Count` response header for paging. Item fields: `id`, `created_at`, `actor_id`, `actor_name`, `actor_role`, `action`, `target`, `detail`.

Blocked phones:

- [ ] `GET /api/admin/blocked-phones` (`id`, `blocked_at`, `false_reports`, `expires_at`; never the phone ID).
- [ ] `POST /api/admin/blocked-phones/{block_id}/unblock`. The phone's false-report count starts again.

Permanent delete:

- [ ] `DELETE /api/admin/places/{facility_id}`. Only a removed center or a rejected place (409 otherwise). Deletes its status history too. Ask the Super admin to confirm.

### 5.4 What the backend does NOT have (do not look for it)

- Chatbot guide and its editor (no guide table, no route).
- "Report a wrong answer" (no route).
- A real AI (`POST /api/chat` gives a fixed answer; no model, no key).
- Photo upload (reports have no photo field; an extra field is a 422).
- Offline mode and install to the home screen (not in this version).
- A support-contact setting. `MenuPages.tsx` says the Super admin will set it; no route does that.
- Automatic warnings: advisories are typed in by a Super admin. Cyclone data is always null.
- Two-step sign in (planned after Nov 20).
- Sending texts or pages to responders. The responder screens poll.
- A list of rejected places for the sender's phone.

## 6. Suggested work order

Sizes: S = under half a day, M = about a day, L = several days. These are guesses, not from the docs.

### Phase 1: shared plumbing and the user side

- [ ] Phone ID + `client.ts` changes (3.1 to 3.5): S
- [ ] Incident form to `POST /api/reports` (4.1): M
- [ ] Add place, pending result (4.2): S
- [ ] Status form: source label and label fix (4.3): S
- [ ] Pending pin look and panel text (4.4): S
- [ ] My reports and my places (4.10): M

Done when (demo data, phone ID set):
- [ ] A hazard sent from the form shows in "My reports" with a status label (New, Being handled or Resolved).
- [ ] A help request without a phone number is refused with the server's message.
- [ ] A place added on the map shows dashed blue, survives the 60-second refresh and a reload, and another browser profile does not see it.
- [ ] A status update shows "Reported by a user". The "People inside" field is labelled correctly.
- [ ] The seeded pending places do not show on the public map. They belong to the seed's fake phones, so test pending with a place you add yourself. (check)

### Phase 2: weather, alerts, hotlines, chat

- [ ] Weather call, cards, strip (4.5): M
- [ ] Alerts sheet cleanup, Warnings and Updates tabs (4.6, 4.7): M
- [ ] Hotlines from the server (4.8): S
- [ ] Chat fixes (4.9): S

Done when:
- [ ] The strip shows the server's `headline` and `detail`. With the network cut after one good load, the weather shows the last forecast with `notice`.
- [ ] The Updates tab shows the seeded advisories. The pinned one is first (or as decided in 7). No "AI-summarized" chip.
- [ ] The Warnings tab shows only the advisory from an official source.
- [ ] The hotlines panel shows 911 only.
- [ ] A chat answer shows the ending line once. "Report a wrong answer" does nothing.

### Phase 3: staff sign in and responder screens

- [ ] Sign in, change password, sign out, 401 handling (5.1): M
- [ ] Reports list with polling and alert (5.2): L
- [ ] Take, resolve, mark false, verify (5.2): M
- [ ] Places to approve, reject, edit (5.2): M
- [ ] Status override, capacity, history (5.2): S
- [ ] Removed places (5.2, 4.12): S

Done when (sign in as "Demo Responder"):
- [ ] The seeded new help request shows the red alert. After "Take" the alert goes away within `refresh_seconds`.
- [ ] A second responder taking the same report gets the 409 message.
- [ ] Resolve and mark false both refuse an empty text.
- [ ] The hazard seeded with 3 phones shows `unconfirmed`; verifying it makes it `verified` for the public (`GET /api/hazards/nearby`).
- [ ] The pending seeded place with a possible duplicate shows the other place and its distance. Approve puts it on the public map.
- [ ] A status override shows "Confirmed by official" on the map.
- [ ] Leaving the page idle past the timeout returns to sign in on the next action.
- [ ] A responder calling any Super admin route (for example `GET /api/admin/users`) gets 403.

### Phase 4: Super admin screens

- [ ] Advisories and sources (5.3): M
- [ ] Emergency numbers with order (5.3): M
- [ ] Accounts (5.3): M
- [ ] Audit log with filters and paging (5.3): M
- [ ] Blocked phones, permanent delete (5.3): S

Done when (sign in as "Demo Super Admin", on a computer):
- [ ] A new advisory appears in the Updates tab; pinning moves it first; deleting removes it.
- [ ] A new emergency number appears in the hotlines panel in the order set.
- [ ] A new responder account can sign in; locking it signs them out; reset password lets them in with the new one.
- [ ] The audit log shows these actions with the name, and the filters and total change the list.
- [ ] A removed place can be deleted for good; deleting an approved place is refused.

## 7. Known gaps and decisions

- [ ] Where to keep the staff token: memory (API.md example) or the browser. Not decided.
- [ ] Phone ID storage: it must survive a reload. The existing code already keeps hidden centers, drafts and "my places" in localStorage. Not decided where this one goes.
- [ ] 143 Philippine Red Cross: not confirmed by the Batangas City CDRRMO. It is in `hotlineData.ts` but not in the database. Keep, remove or add through the Super admin screen.
- [ ] The "AI-summarized" chip and "Summaries are generated by AI" note are wrong for advisories typed by a person.
- [ ] Updates order: pinned first (server) or official first (current code).
- [ ] The chat ending line: show it in the answer or in the footer, not both.
- [ ] `Retry-After`: `main.py` exposes only `X-Total-Count`. A browser on another origin probably cannot read `Retry-After`, so `ApiError.retryAfter` may stay empty. Several 429 messages already say how many minutes to wait. (check)
- [ ] Rejected places: the sender's phone gets no signal (4.10).
- [ ] "Super admin: computer only" (REDESIGN) is not enforced by the server. Any role check on screen size is a frontend choice.
- [ ] Whether pending places appear in the list and search (4.4).
- [ ] Warnings empty text may overclaim (4.7). Show `pinned` or `updated_at` or not.
- [ ] `hazard_state: pending` has no label in the docs. (check)
- [ ] Time zone marking for places and removal times (3.5). (check)
- [ ] Navigate button: which maps app (5.2).
- [ ] `weather_code` to icon: not defined (4.5).
- [ ] What `EmergencyHotlines` shows when `GET /api/emergency-numbers` fails (4.8).
- [ ] Report limits in the form (4.1): lower to 40 and 140, or ask the backend owner to raise the server limits.
