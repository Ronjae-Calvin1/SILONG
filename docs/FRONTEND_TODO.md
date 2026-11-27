# SILONG frontend to-do

> **One role: Admin.** There is only the Admin role: `/api/responder/*` is now `/api/admin/*`, every Admin can use every admin endpoint, and `role` is always `"admin"`. The admin console follows the admin console design (the design notes that came with the staff console mockup). The exact endpoints, fields, error codes and refresh rules for every admin screen are in [`ADMIN_FRONTEND_HANDOFF.md`](ADMIN_FRONTEND_HANDOFF.md); section 5 below is the short checklist.

Checklist for connecting the existing screens to the server and building the admin console (a separate frontend).
Facts come from `docs/API.md`, `docs/REDESIGN.md`, `README.md`, `CHANGELOG.md` (Updates 9 to 12) and the code in `frontend/src`, `backend/app`.
Where the docs and the code disagree, the code is what this file follows, and it says so.
"(check)" means: not confirmed, look before you build.

## 1. How to use this file

- The backend is done and tested (parts 1 to 5). `docs/API.md` and http://127.0.0.1:8000/docs describe every route.
- Work top to bottom: plumbing (3), existing screens (4), missing screens (5). Sizes and phases are in 6, open questions in 7.
- The admin console is a second frontend with its own link, built from section 5 and [`ADMIN_FRONTEND_HANDOFF.md`](ADMIN_FRONTEND_HANDOFF.md). The user site (sections 3 and 4) must not link to it or mention it.
- Do not change a field name or a route to fit a screen. If the server must change, tell the backend owner.

## 2. Setup for the frontend developer

- [ ] Run the backend (README, "How to run it"): `cd backend`, `pip install -r requirements.txt`, `uvicorn app.main:app --reload --port 8000`. On Windows use `py -m ...`.
  - check it: `GET /api/health` answers `{"status": "ok"}` (`api.health()` in `client.ts`)
- [ ] Create the first Admin once: `py scripts/create_admin.py` (README, "Admin accounts"). It uses `typhoon.db` in the folder you run it from.
- [ ] Load demo data into a separate file (README, "Operations"):
  - `py scripts/seed_demo.py --db demo.db --with-demo-staff`
  - start the backend with `DATABASE_URL=sqlite:///./demo.db` (or put it in `backend/.env`)
  - it makes the Admin accounts "Demo Admin" and "Demo Admin 2" and prints their passwords once
  - it refuses `typhoon.db` unless you add `--force`; do not
- [ ] Set `VITE_API_URL` in `frontend/.env` if the backend is not at `http://127.0.0.1:8000/api` (the default in `src/api/client.ts`). It is not listed in `frontend/.env.example`. The admin console uses the same variable the same way (default `http://127.0.0.1:8000/api`).
- [ ] Two frontends, one backend: user site `http://localhost:5173` (this `frontend` folder), admin console `http://localhost:5174` (its own frontend, started with its own port, for example `--port 5174`; its code is not in this repository), backend `http://127.0.0.1:8000`. Any two free ports work, but every origin must be listed in `CORS_ORIGINS` (see below and README, "Admin console and the two origins").
- [ ] Set `VITE_MAPTILER_KEY` (README, "Map setup"). The key's allowed origin is the host name only, for example `localhost`, without `http://`.
- [ ] GPS needs a secure page. `http://localhost` works. `http://192.168.x.x` does not. For a real phone use USB and port forwarding so the phone opens `localhost` (`docs/REDESIGN.md`, "Testing on a phone").
- [ ] Optional: `VITE_SUPPORT_EMAIL`, `VITE_SUPPORT_PHONE` (read in `MenuPages.tsx`, not in `.env.example`). The backend now has the support contact: `GET /api/support-contact` (public) and `GET`/`PATCH /api/admin/contact-settings` (Admin). Use the server values on the Contact support page instead of these two variables (see 4.15).
- CORS (`backend/app/main.py`, `config.py`): the backend answers a browser only for the origins in `CORS_ORIGINS` in `backend/.env`. Not set means `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:5174`, `http://127.0.0.1:5174`. Any other address (a phone on Wi-Fi, a real domain) must be added there, then restart the backend. Allowed request headers are `Authorization`, `X-Phone-Id` and `Content-Type`; allowed methods `GET HEAD POST PUT PATCH DELETE OPTIONS`. Only `X-Total-Count` is exposed to the browser, so `Retry-After` cannot be read (7). Credentials stay off: the token is a header, not a cookie.

## 3. Shared plumbing (do this first)

### 3.1 Phone ID

- [x] Make one random ID per browser, once, and keep it. Format: 16 to 64 letters, digits, `-` or `_` (API.md, "Phone ID"). A UUID (36 characters) fits.
- [x] Send it as the header `X-Phone-Id`. The server stores only a hash. It is not proof of identity. Clearing browser data makes a new one.
- [x] The phone ID code is `frontend/src/api/phoneId.ts` (`getPhoneId()`, kept in localStorage under `silong:phone-id`; a stored value that does not fit the format is replaced).

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

- [ ] Send it on all seven (done for five: `getFacilities`, `submitStatus`, `addEvacuationCenter`, `sendReport`, `getMyReports`; `GET /api/hazards/nearby` and the status history are added with their screens, pass `phone: true`). No other route lists it (chat, weather, advisories, emergency numbers and every Admin route do not).
- [x] `MapPage.tsx` refreshes `getFacilities()` every 60 seconds (`REFRESH_MS`). Each refresh needs the header, or a pending place disappears at the next refresh.

### 3.2 Central request helper (`src/api/client.ts`)

Every call goes through `request()` in `src/api/client.ts`: JSON in and out, `X-Phone-Id` when a call passes `phone: true`, errors as `ApiError` (`status`, `detail`), status 0 when the server cannot be reached.

- [ ] Add `X-Phone-Id` to the seven calls above (five of seven today, see 3.1).
- [ ] Add `Authorization: Bearer <token>` when an Admin is signed in, on every Admin route. Only the admin console does this; the user site never has a token.
- [ ] `POST /api/facilities/{facility_id}/status` with an Admin token is saved as "Confirmed by official". A wrong or expired token there counts as a user, not an error (API.md). The user site sends no token, so its updates are always "Reported by a user".
- [x] Keep `ApiError` and `messageFromBody()`. They already handle `detail` as a string and as a 422 list.
- [x] Add `retryAfter` (seconds) to `ApiError` for 429. See 7: the browser may not be able to read the header.
- [x] Remove the stale comment above `askSilo` ("ASSUMPTION ... routes.py ... not in this copy"). The route is `POST /api/chat` and the code already matches.
- [ ] Add the missing methods for sections 4 and 5. Today `client.ts` has: health, facilities, status, add, sendReport, getMyReports, chat (the three Admin-only methods for removed centers were deleted in Part F2).

### 3.3 Errors (body is `{"detail": "<plain message>"}`; a 422 body is a list)

| Code | Meaning (API.md) | What the screen shows |
| --- | --- | --- |
| 0 | server not reached (`ApiError` status 0, already in `client.ts`) | existing "Can't reach the server" message |
| 400 | `X-Phone-Id` missing or badly formed | a plain error; this is an app bug, not the person's mistake |
| 401 | not signed in, or the sign-in ran out (on the sign-in call itself: wrong name or password) | admin console: drop the token, show "You were signed out" and the sign-in screen |
| 403 | an account that is locked or gone, a wrong current password, or this phone is blocked from reports | `detail` |
| 404 | does not exist, or this caller may not see it | `detail` |
| 409 | clashes with the current state (already taken, duplicate name, already added) | `detail` |
| 422 | a value is not accepted | `detail` (first message; `messageFromBody` does this) |
| 423 | account locked | `detail` on the sign-in form |
| 429 | too many requests | `detail`; disable the button for `Retry-After` seconds if it can be read |

- [x] Show `detail` as written. Do not rewrite server messages. (`EvacCenterForm.friendlyError` strips "(id N)" and "(POST ...)" from the old duplicate message; see 4.2.)

### 3.4 Admin token (admin console only)

- [ ] Keep it in memory (API.md, flow 1: "Keep the token in memory"). A reload means sign in again. Other places are a decision, see 7. Whatever is chosen: the token is never reachable from the user site (the two sites are two origins) and is never put in a URL, a query string or the `#` part of a link.
- [ ] Idle sign-out is 30 minutes without any request; each request restarts it. `user.idle_timeout_minutes` in the sign-in answer says the number.
- [ ] Any `401` on an Admin call: clear the token and go to the sign-in screen with the "You were signed out" message. A `403` on an Admin call (account locked or removed while the sign-in was alive) is handled the same way.
- [ ] Sign out: `POST /api/auth/sign-out` (sends the token), then drop it. Safe to call twice.

### 3.5 Times and ids

- [x] Times are ISO strings marked UTC. Convert with `parseApiTime(iso)` from `src/api/convert.ts` (it adds the UTC mark when one is missing; `statusInfo.timeAgo` and `clockTime` still use `new Date(iso)`, which is the same for marked times). Checked in code for reports, status, advisories, accounts. Places and removal times: (check).
- [ ] Screens that want a `Date`: `WarningItem.issuedAt`, `UpdateItem.publishedAt`, `WeatherTab.lastUpdated`.
- [ ] Advisory `id` is a number. `WarningItem.id` and `UpdateItem.id` are strings: use `idToString(id)` from `src/api/convert.ts` (not used yet; the screens are connected in 4.6 and 4.7).
- [x] Facility, report, place and number ids are numbers in the API and in `types/index.ts` (`Facility.id`). No conversion there.

## 4. Existing screens to connect

### 4.1 Incident form: `components/IncidentPanel.tsx`

Today: validates, then `saveReport()` writes to localStorage (`REPORTS_KEY` in `myActivity.ts`). Nothing is sent. Footnote says "Saved on this phone for now".

- [x] On submit call `POST /api/reports` with `X-Phone-Id`. Remove `saveReport()`.
- [x] Replace the texts "Request saved on this phone" and "Report saved on this phone" and the hazard footnote with the server's `message` (answer has `id`, `kind`, `status`, `label`, `created_at`, `message`).

| Form | API | Rule |
| --- | --- | --- |
| `mode` | `kind` (`help` or `hazard`) | required |
| `kind` (chip or typed text) | `category` | required, 1 to 40 characters |
| `details` | `note` | optional, server max 140 |
| `contact` | `contact` | required for help, max 60; leave out for a hazard (the form does not ask) |
| `people` | `people` | help only, 1 to 999 (form: 1 to 99) |
| `canMove` | `can_move` | help only; `yes`, `no` or `unsure` (form: yes or no, required) |
| `point.lat`, `point.lng` | `latitude`, `longitude` | must be inside Batangas City (south 13.60, west 120.97, north 13.86, east 121.18 in `config.py`), else 422 |

- [x] A hazard with `people` or `can_move` is refused (422). The form already keeps them in help mode only. Do not send them on a hazard.
- [x] Any other field is refused (422): no name, no photo.
- [x] Limits do **not** match. Form: details 200 (`MAX_DETAILS`), kind 60 (`MAX_KIND`). Server: note 140 (`REPORT_NOTE_MAX`), category 40 (`REPORT_CATEGORY_MAX`). Lower both in the form (or see 7).
- [x] 403 means the phone is blocked after 3 false reports. 429 means wait (per-phone and per-IP limits in `config.py`: `REPORT_PHONE_COOLDOWN_SECONDS`, `REPORT_PHONE_MAX`, `REPORT_IP_MAX`).
- [x] Keep the "Call 911" strip and the GPS texts as they are.

### 4.2 Add place: `components/EvacCenterForm.tsx`, `AddEvacCenter.tsx`, `evacCenterDraft.ts`; `api.addEvacuationCenter`; `MapPage.handleAdded`

Today: `POST /evacuation-centers` with no header. On success the page adds the pin, shows "Evacuation center added." and calls `rememberMyPlace()`.

- [x] Call `POST /api/evacuation-centers` with `X-Phone-Id`.
- [x] Field names already match the API: `name`, `center_type`, `barangay`, `address`, `contact`, `max_capacity`, `latitude`, `longitude`, `note`. Capacity 1 to 50000 matches.
- [x] The answer is `201` with `approval_status: "pending"`. Add `approval_status` to `Facility` in `types/index.ts`.
- [x] Change the toast "Evacuation center added." to say it waits for approval and only this phone sees it.
- [x] A possible duplicate (same name within 30 m) is **not** a 409 any more. The answer has no duplicate flag; only Admins see it. Remove the duplicate/"restore it instead" handling in `friendlyError()`.
- [x] Errors that can happen now:
  - 409 "You already added this place. It is waiting for approval by an Admin."
  - 429 when 5 places already wait (`PENDING_PLACES_PER_PHONE`)
  - 429 per IP or phone, with `Retry-After`
- [x] Without the header the place is still saved but only Admins will ever see it. Do not allow that case.

### 4.3 Status form: `components/StatusForm.tsx`; `api.submitStatus`; `MapPage.handleSaved`; `statusInfo.ts`

- [x] Call `POST /api/facilities/{facility_id}/status` with `X-Phone-Id`. Body fields already match: `status`, `people_inside`, `max_capacity`, `resources`, `note`.
- [x] Add `source` and `source_label` to `FacilityStatus`. The answer has them: "Reported by a user" or "Confirmed by official".
- [x] Show `source_label` in `FacilityPanel.tsx` (next to "Last updated"). Nothing in `frontend/src` reads it today.
- [x] **Label bug confirmed.** `StatusForm.tsx` has two inputs both labelled "Maximum capacity (optional)". The first one holds `people` (placeholder "e.g. 85", error text "People inside must be a whole number"). Rename its label to "People inside".
- [x] `message` in the answer is already shown by `handleSaved` (8 seconds). Keep it. It is how the user learns the server changed what was sent (for example "full" because people reached capacity).
- [x] After an official sets a capacity, a user's `max_capacity` is ignored. The form always sends the field; this is expected (REDESIGN).
- [x] `resources` is only sent for evacuation centers (the form does that today).

### 4.4 Map pins and facility panel: `pages/MapPage.tsx`, `components/StatusPanel.css`, `MapPins.css`, `FacilityPanel.tsx`, `CapacityIndicator.tsx`

Pin looks from `docs/REDESIGN.md`, compared with the code:

| Look | Meaning | In code today |
| --- | --- | --- |
| hollow | no status yet | `data-status="unknown"` rule in `MapPins.css` |
| dashed and dim | update older than 6 hours | `data-outdated` rules in `StatusPanel.css` (from `status.is_outdated`) |
| small blue ring | added through the app | `data-source="user"` rule in `StatusPanel.css` |
| dashed blue | waiting for approval, only the sender sees it | **not built** |

- [x] Read `approval_status` from `GET /api/facilities` and set a data attribute on the pin. Add the dashed blue rule.
- [x] In `FacilityPanel.tsx` say a pending place is waiting for approval and only this phone sees it.
- [x] A pending place only comes back from `GET /api/facilities` when the header is sent (3.1).
- [ ] `FacilityList.tsx` and the search use the same list: decide if pending places show there (check).
- [x] Show "Confirmed by official" vs "Reported by a user" (4.3).

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

- [ ] Add `api.getEmergencyNumbers()`: `GET /api/emergency-numbers` (optional query `category`: `medical`, `accident`, `flood`, `violence`, `missing_person`; numbers without a category are left out when it is used). Items: `id`, `number`, `name`, `description`, `position`, `category` (null = a general number such as 911). Already in display order.
- [ ] Replace `NATIONAL_HOTLINES` with this list. `description` is not shown today; show it or not (check).
- [ ] The 143 line goes away unless an Admin adds it (7).
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
- [ ] Do not add a server call. Hiding for everyone is an Admin action (4.12, 5.2).

### 4.12 Removed centers: `components/RemovedCenters.tsx`

- [ ] **It is not mounted anywhere** (only defined; `getRemovedCenters` and `restoreEvacuationCenter` are used only inside it).
- [ ] Its three routes are Admin only now (401 or 403 without a sign-in): `GET /api/evacuation-centers/removed`, `DELETE /api/evacuation-centers/{facility_id}`, `POST /api/evacuation-centers/{facility_id}/restore`. `client.ts` sends no `Authorization` header on them.
- [x] Do not mount it on the public map or anywhere in the user site. Move it (or rebuild it) in the admin console's Places screen (5.2).
- [x] `RemovedCenters.tsx`, the `RemovedCenter` type and the client methods `removeEvacuationCenter`, `getRemovedCenters` and `restoreEvacuationCenter` were deleted from the user site (Part F2). The admin console builds its own.

### 4.13 Admin sign in link: remove it from the user site: `components/HamburgerMenu.tsx`, `pages/AdminSignInPage.tsx`, `App.tsx`

The admin console has its own link (its own frontend and port). The user site does not point to it in any way and does not mention it.

- [x] `HamburgerMenu.tsx`: delete the "Admin sign in" row (the footer with `navigate("/admin")`). The menu keeps Map, My reports, My suggested places, Hidden on this phone, About SILONG, FAQs and Contact support.
- [x] `App.tsx`: delete the `/admin` route and the `AdminSignInPage` import. The real sign-in is built in the admin console (5.1).
- [x] Delete `pages/AdminSignInPage.tsx` and its CSS from the user site.
- [x] No admin link, button or text anywhere else on the user screens, the landing page, the FAQs or Contact support.
- [x] The full list of places that still say Responder, Super admin or Admin sign in is in [`ADMIN_FRONTEND_HANDOFF.md`](ADMIN_FRONTEND_HANDOFF.md), "Leftovers in the user site".

### 4.14 Nearby hazards on the map (not built): `pages/MapPage.tsx`, `components/MapPins.css`, `types/index.ts`

Today no screen shows hazards from other people. Only the sender's own reports exist (4.10).

- [ ] Add `api.getNearbyHazards(latitude, longitude)`: `GET /api/hazards/nearby?latitude=..&longitude=..` (query names are `latitude` and `longitude`; the short `lat` and `lng` in the `docs/API.md` intro are wrong). Send `X-Phone-Id` (optional).
- [ ] Items: `id`, `latitude`, `longitude` (approximate: the middle of a 250 m square, not the real spot), `status` (`unconfirmed` or `verified`), `label` ("Unconfirmed" or "Verified"), `category`. Nothing else is public.
- [ ] Range is 1 km (`NEAR_ME_KM`) from the position you send. The position is not stored. Use the person's location, or the map centre if location is off (check).
- [ ] Draw each hazard as an approximate area or marker (not an exact pin), with its `label` and `category`. Make "Unconfirmed" look different from "Verified". The look is not in the designs file (check).
- [ ] Refresh when the person moves or the map refreshes. Reads are rate limited (429).
- [ ] A hazard is hidden until 3 different phones report it, and leaves the map when an Admin resolves or marks it false.
- [ ] A help request never appears here. The sender sees only their own status (4.10). Whether the sender also sees their own pin on the map is not in the code (check).

### 4.15 Contact support: `components/MenuPages.tsx`

- [ ] Add `api.getSupportContact()`: `GET /api/support-contact` (public, no header). Answer: `support_email`, `support_number`; `null` means not set (show nothing, not a placeholder; the page's "not set yet" text may stay for null).
- [ ] Replace `VITE_SUPPORT_EMAIL` and `VITE_SUPPORT_PHONE` with the server values.
- [x] The footer line now says "Contact details are set by an Admin."
- [ ] The control-room number is never in a public answer. Do not look for it here.

## 5. Missing screens to build

All of section 5 is the **admin console**: its own frontend at its own link (`http://localhost:5174`), with its own pages, menu and routes. It shares nothing with the user site. [`ADMIN_FRONTEND_HANDOFF.md`](ADMIN_FRONTEND_HANDOFF.md) has the exact endpoints, fields, error codes and refresh rules for every screen; this section is the checklist.

### 5.1 Admin sign in and change password (all Admins)

One sign-in screen: name, password, show or hide password. No sign-up. No "Back to the public map" link and no link to the user site. A user who opens the admin link sees only this screen.

- [ ] Sign in: `POST /api/auth/sign-in` with `name` (max 100, not case sensitive) and `password` (max 200). Answer: `token`, `token_type`, `user` (`id`, `name`, `role`, `idle_timeout_minutes`).
- [ ] 401 wrong name or password (same message for both). 423 account locked (5 wrong tries in a row lock it for 15 minutes; an Admin can also lock it, and then only an Admin can unlock it). 429 sign-ins per IP (20 per 10 minutes).
- [ ] `GET /api/me` says who is signed in (`id`, `name`, `role`, `idle_timeout_minutes`). `role` is always `"admin"`: do not branch on it.
- [ ] Every Admin gets every screen. No locked tabs, no "Super admin only" labels, one ADMIN badge. The server checks the token on every admin route (401 without a good sign-in, 403 for a locked or removed account); hiding screens is not security.
- [ ] Change password: `POST /api/auth/change-password` with `current_password`, `new_password`. A wrong current password is 403 and counted (5 per person and 20 per IP per 10 minutes, then 429). New password: at least 8 characters (`MIN_PASSWORD_LENGTH`) and different from the current one (422). Your other sign-ins end; this one stays.
- [ ] Sign out button: `POST /api/auth/sign-out`.
- [ ] "You were signed out": after 30 minutes without any request (each request moves the timer), the next admin call is a 401. Drop the token, show "You were signed out" and the sign-in screen.

### 5.2 Admin console (computer: full; phone: simple)

One role, so one console. Computer: top bar with the logo, the ADMIN badge, five tabs (Live map, Places, Content, Chatbot, Accounts), the person's name and Sign out. Phone: header with the logo, the ADMIN badge and the person's name, and a bottom bar with four tabs (Reports, Map, Places, Me). Content, Chatbot and Accounts are computer only in the design.

Reports (Live map on a computer; Reports and Map on a phone):

- [ ] `GET /api/admin/reports`. Query: `status` (`new`, `handling`, `resolved`, `all`; anything else is 422; `resolved` also lists reports marked false, `all` is open and closed together, not given means open reports only), `include_closed` (adds nothing when `status` is given), `kind` (`help` or `hazard`), `mine` (only reports you took), `latitude` with `longitude` (both or neither, else 422; adds `distance_m`), `since` (ISO time; only items that changed since, closed ones included so you can drop them).
- [ ] Filters in the design: computer All, New, Being handled, Resolved; phone New, Mine, Handling, Resolved. Map to `status=all`, `new`, `handling`, `resolved`, and `mine=true`.
- [ ] Answer: `server_time`, `refresh_seconds` (10), `new_help_count`, `has_new_help`, `latest_report_id`, `since`, `items`. Poll every `refresh_seconds` from the answer, not a fixed number. Send the last `server_time` as `since` for the next poll and merge.
- [ ] Order is the server's: new help requests first, then other open reports (longest waiting first), then closed (newest first).
- [ ] Badges: `GET /api/admin/summary` (`new_reports`, `being_handled`, `mine`, `pending_places`, `removed_centers`, `server_time`). Poll it with the list. There is no count of resolved reports and no "All" count: count the list.
- [ ] Red "Needs help" alert (computer and phone, with an Open button) while `has_new_help` is true. `new_help_count` and `latest_report_id` are in the answer. There is no push, text or page: the screens poll.
- [ ] Item fields: `id`, `kind`, `status` (`new`, `being_handled`, `resolved`, `false`), `is_new_help`, `category`, `categories`, `people`, `can_move`, `latitude`, `longitude`, `contacts`, `notes`, `created_at`, `updated_at`, `taken_by`, `is_mine`, `distance_m`, `closed_by`, `resolution_note`, `false_reason`, `verified`, `verified_by`, `hazard_state` (`pending`, `unconfirmed`, `verified`), `phones`, `report_count`.
- [ ] A hazard is one line for all reports about the same place (within 100 m). Show `report_count`, `phones`, every `categories` value, all `contacts` and `notes`.
- [ ] Take it: `POST /api/admin/reports/{report_id}/take`, no body. If another Admin has it you take it over (reassigned to you); 409 only means it is closed. Safe to call twice. **Ask first:** when `taken_by` is another Admin, show "<name> is handling this. Take over?" before calling take. The server does not ask.
- [ ] Release: `POST /api/admin/reports/{report_id}/release`, any Admin, any open report, safe to call twice.
- [ ] Call: a `tel:` link from `contacts`. No endpoint. Navigate: a link with `latitude` and `longitude`. No endpoint. Which maps app is not decided.
- [ ] Resolve: `POST /api/admin/reports/{report_id}/resolve` with `what_was_done` (3 to 500 characters). Phone sheet options: Helped on site, Moved to a center, Sent to a hospital, Could not find them, Other, plus an optional note. The server has only the one text: build `what_was_done` from the option and the note.
- [ ] Mark false: `POST /api/admin/reports/{report_id}/mark-false` with `reason` (3 to 500). The dialog needs a reason. 3 false reports from one phone block that phone.
- [ ] Verify a hazard: `POST /api/admin/reports/{report_id}/verify`, no body, hazards only (422 otherwise), safe to call twice. The public then sees "Verified".
- [ ] Rules: exact location and contact are visible to Admins only; the site cannot text or page anyone; the page is not a replacement for 911.

Places:

- [ ] `GET /api/admin/places` (default: pending, longest waiting first; `status=rejected` lists rejected). Item fields: `id`, `key`, `name`, `center_type`, `barangay`, `address`, `contact`, `max_capacity`, `latitude`, `longitude`, `note`, `approval_status`, `submitted_at`, `reviewed_by`, `reviewed_at`, `reject_reason`, `possible_duplicate`, `is_removed`, `message`. There is no device or phone field.
- [ ] Show `possible_duplicate` (`name`, `distance_m`, `approval_status`, `removed`) so the reviewer sees the other place.
- [ ] Approve: `POST /api/admin/places/{facility_id}/approve`. Also undoes a rejection. Safe to call twice.
- [ ] Reject: `POST /api/admin/places/{facility_id}/reject` with an optional `reason` (max 140). A place already on the map gets 409 (remove it instead).
- [ ] Edit details: `PATCH /api/admin/places/{facility_id}` with only the changed fields of `name`, `address`, `barangay`, `contact`, `note`. Type, capacity and location cannot be edited here. 409 when a new name matches another center within 30 m, or the center is from the data files; 422 for a hospital or a clinic.

Status override and capacity:

- [ ] Override latest status: `POST /api/admin/facilities/{facility_id}/status-override` (`status`, `people_inside`, `max_capacity`, `resources`, `note`, optional `reason`). Saved as "Confirmed by official" with the name; the old status stays in the history. Works on places that are on the map.
- [ ] Correct capacity: `POST /api/admin/facilities/{facility_id}/capacity-correction` (`max_capacity` 1 to 50000, optional `reason`). Needs a status to sit on (422 when the center has none: override the status and send the capacity with it). Users cannot change it afterwards.
- [ ] History: `GET /api/admin/facilities/{facility_id}/status-history` (optional `limit`). Fields include `kind` (`report`, `override`, `capacity`), `source`, `source_label`, `changed_by`.
- [ ] A normal status update with a token (`POST /api/facilities/{facility_id}/status`) is also "Confirmed by official" and is not held back by the per-place cooldown (REDESIGN).

Removed places:

- [ ] List: `GET /api/evacuation-centers/removed` (`days_left`, `delete_after`, `removed_by`). Remove: `DELETE /api/evacuation-centers/{facility_id}`. Restore: `POST /api/evacuation-centers/{facility_id}/restore`.
- [ ] Removing hides the center for everyone and keeps it 30 days. A pending place cannot be removed (409): reject it.
- [ ] Delete for good: `DELETE /api/admin/places/{facility_id}`. Only a removed center or a rejected place (409 otherwise). Deletes its status history too. The dialog asks the person to type the name; the server does not check it.

Content (computer):

- [ ] Advisories (`AdvisoryIn`: `title` max 120, `details` max 1000, `organization` max 80, `source_url` http or https max 500 and required, `pinned`): create `POST /api/admin/advisories`, edit `PATCH /api/admin/advisories/{advisory_id}` (`title`, `details`, `organization`, `source_url`; not `pinned`), delete `DELETE /api/admin/advisories/{advisory_id}` (204), pin `POST .../pin`, unpin `POST .../unpin` (both safe to call twice). There is no expiry field.
- [ ] Official sources: `GET /api/admin/advisory-sources`, `POST /api/admin/advisory-sources` (`name`), `PATCH /api/admin/advisory-sources/{source_id}`, `DELETE /api/admin/advisory-sources/{source_id}` (204). An advisory is official when its `organization` matches a listed name (case and extra spaces ignored). Removing a source keeps its advisories but they stop showing as official. Starts with PAGASA, NDRRMC, Batangas City CDRRMO.
- [ ] Emergency numbers (`number` max 30, digits and `+ - ( ) * #`, at least 3 digits; `name` max 80; `description` max 140; `category` optional): add `POST /api/admin/emergency-numbers`, edit `PATCH /api/admin/emergency-numbers/{number_id}`, remove `DELETE /api/admin/emergency-numbers/{number_id}` (204), order `PUT /api/admin/emergency-numbers/order` with `ids`: every id once, in the order to show.
- [ ] Contact settings: `GET /api/admin/contact-settings` and `PATCH /api/admin/contact-settings` (`control_room_number`, `support_email`, `support_number`; send only what changes; `null` or empty clears). The control-room number feeds the phone "Call the control room" button; the support pair feeds the user site's Contact support page.

Chatbot (computer): not built on the server. See 5.3.

Accounts (computer):

- [ ] List `GET /api/admin/users` (`status`: `active`, `locked_by_admin`, `locked_for_wrong_tries`; `locked_until`, `created_by`, `last_sign_in_at`). `role` is always `admin`: show no role column or one ADMIN label.
- [ ] Create `POST /api/admin/users` (`name`, `password`). Leave `role` out: it is accepted and ignored for one release, then refused.
- [ ] Lock `POST /api/admin/users/{user_id}/lock`. Unlock `POST /api/admin/users/{user_id}/unlock` (also clears a wrong-tries lock).
- [ ] Reset password `POST /api/admin/users/{user_id}/reset-password` (`new_password`). The person is signed out everywhere. The Admin must tell them the password: it is never shown again. Not for your own account (409).
- [ ] Remove `DELETE /api/admin/users/{user_id}`. Audit entries stay. You cannot lock or remove your own account, and the last active Admin cannot be locked or removed (409).

Audit log and blocked phones (computer):

- [ ] `GET /api/admin/audit-log`, newest first. Query: `limit`, `offset`, `before_id`, `action`, `actor` (exact name), `person` (part of a name), `from`, `to` (`YYYY-MM-DD`, UTC; a bad date is 422). Read the total from the `X-Total-Count` response header for paging. Item fields: `id`, `created_at`, `actor_id`, `actor_name`, `actor_role`, `action`, `target`, `detail`.
- [ ] `GET /api/admin/blocked-phones` (`id`, `blocked_at`, `false_reports`, `expires_at`; never the phone ID). `POST /api/admin/blocked-phones/{block_id}/unblock`. The phone's false-report count starts again.

Me (phone; the same data is useful on a computer):

- [ ] Name from `GET /api/me`. Change password (5.1). "Signs out by itself after 30 minutes without use" (`idle_timeout_minutes`).
- [ ] My recent actions: `GET /api/admin/me/activity` (`limit` 1 to 100, default 20): `handled_today`, `today_starts_at`, `server_time`, `items` (`id`, `created_at`, `action`, `target`, `detail`). Your own actions only; sign-ins are left out.
- [ ] Call the control room: `control_room_number` from `GET /api/admin/contact-settings`; `null` means not set.

### 5.3 What the backend does NOT have (do not look for it)

- Chatbot guide and its editor (no guide table, no route).
- "Report a wrong answer" (no route).
- A real AI (`POST /api/chat` gives a fixed answer; no model, no key).
- Photo upload (reports have no photo field; an extra field is a 422).
- Offline mode and install to the home screen (not in this version).
- Automatic warnings: advisories are typed in by an Admin. Cyclone data is always null.
- Two-step sign in (planned after Nov 20).
- Sending texts or pages to Admins. The admin screens poll.
- A list of rejected places for the sender's phone.
- Screens in the admin console design that have no endpoint, and endpoints with no designed screen: see `ADMIN_FRONTEND_HANDOFF.md`, "Gaps and contradictions".

## 6. Suggested work order

Sizes: S = under half a day, M = about a day, L = several days. These are guesses, not from the docs.

### Phase 1: shared plumbing and the user side

- [ ] Phone ID + `client.ts` changes (3.1 to 3.5): S
- [x] Incident form to `POST /api/reports` (4.1): M
- [x] Add place, pending result (4.2): S
- [x] Status form: source label and label fix (4.3): S
- [x] Pending pin look and panel text (4.4): S
- [ ] My reports and my places (4.10): M
- [ ] Nearby hazards on the map (4.14): M

Done when (demo data, phone ID set):
- [ ] A hazard sent from the form shows in "My reports" with a status label (New, Being handled or Resolved).
- [ ] A help request without a phone number is refused with the server's message.
- [ ] A place added on the map shows dashed blue, survives the 60-second refresh and a reload, and another browser profile does not see it.
- [ ] A status update shows "Reported by a user". The "People inside" field is labelled correctly.
- [ ] The seeded pending places do not show on the public map. They belong to the seed's fake phones, so test pending with a place you add yourself. (check)
- [ ] A hazard reported by 3 different phones (demo data has one) shows on the map as "Unconfirmed" within 1 km, and as "Verified" after an Admin verifies it.

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

### Phase 3: admin sign in and the report and place screens (admin console)

- [ ] Sign in, change password, sign out, 401 handling (5.1): M
- [ ] Reports list with polling and alert (5.2): L
- [ ] Take (with the take-over question), resolve, mark false, verify (5.2): M
- [ ] Places to approve, reject, edit (5.2): M
- [ ] Status override, capacity, history (5.2): S
- [ ] Removed places (5.2, 4.12): S

Done when (sign in as "Demo Admin"):
- [ ] The seeded new help request shows the red alert. After "Take" the alert goes away within `refresh_seconds`.
- [ ] With "Demo Admin 2" signed in elsewhere: taking a report "Demo Admin" is handling first asks "<name> is handling this. Take over?"; confirming takes it over (no 409). A closed report gives the 409 message.
- [ ] Resolve and mark false both refuse an empty text.
- [ ] The hazard seeded with 3 phones shows `unconfirmed`; verifying it makes it `verified` for the public (`GET /api/hazards/nearby`).
- [ ] The pending seeded place with a possible duplicate shows the other place and its distance. Approve puts it on the public map.
- [ ] A status override shows "Confirmed by official" on the map.
- [ ] Leaving the page idle past the timeout returns to sign in ("You were signed out") on the next action.
- [ ] Opening the admin link on the user's port or with no token gives only the sign-in screen; any admin call without a token is 401.

### Phase 4: admin content and account screens (computer)

- [ ] Advisories and sources (5.2): M
- [ ] Emergency numbers with order, contact settings (5.2): M
- [ ] Accounts (5.2): M
- [ ] Audit log with filters and paging (5.2): M
- [ ] Blocked phones, delete for good (5.2): S

Done when (sign in as "Demo Admin", on a computer):
- [ ] A new advisory appears in the Updates tab of the user site; pinning moves it first; deleting removes it.
- [ ] A new emergency number appears in the hotlines panel in the order set.
- [ ] A new Admin account can sign in; locking it signs them out; reset password lets them in with the new one.
- [ ] The audit log shows these actions with the name, and the filters and total change the list.
- [ ] A removed place can be deleted for good; deleting an approved place is refused.

## 7. Known gaps and decisions

- [ ] Where to keep the Admin token: memory (API.md example) or the browser. Not decided. Fixed rules whichever is chosen: never reachable from the user site (separate origin) and never in a URL.
- [x] Phone ID storage: localStorage, key `silong:phone-id` (decided in Part F1).
- [ ] 143 Philippine Red Cross: not confirmed by the Batangas City CDRRMO. It is in `hotlineData.ts` but not in the database. Keep, remove or add through the admin console.
- [ ] The "AI-summarized" chip and "Summaries are generated by AI" note are wrong for advisories typed by a person.
- [ ] Updates order: pinned first (server) or official first (current code).
- [ ] The chat ending line: show it in the answer or in the footer, not both.
- [ ] `Retry-After`: `main.py` exposes only `X-Total-Count`. A browser on another origin probably cannot read `Retry-After`, so `ApiError.retryAfter` may stay empty. Several 429 messages already say how many minutes to wait. (check)
- [ ] Rejected places: the sender's phone gets no signal (4.10).
- [ ] In the admin console design, Content, Chatbot and Accounts are shown on a computer only; the phone has Reports, Map, Places and Me. The server does not enforce screen size, and every Admin can call every admin route. Any limit by screen size is a frontend choice.
- [ ] Where Audit log, Blocked phones and Change password sit on the desktop console: not in the design (see `ADMIN_FRONTEND_HANDOFF.md`).
- [ ] Whether pending places appear in the list and search (4.4).
- [ ] Warnings empty text may overclaim (4.7). Show `pinned` or `updated_at` or not.
- [ ] `hazard_state: pending` has no label in the docs. (check)
- [ ] Time zone marking for places and removal times (3.5). (check)
- [ ] Navigate button: which maps app (5.2).
- [ ] `weather_code` to icon: not defined (4.5).
- [ ] What `EmergencyHotlines` shows when `GET /api/emergency-numbers` fails (4.8).
- [x] Report limits in the form (4.1): lowered to 40 (category) and 140 (note), the server limits (Part F2).
