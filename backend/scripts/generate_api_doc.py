"""
Builds docs/API.md, the API reference for the frontend, from the app's own OpenAPI schema
(app.openapi()), so it cannot drift from the code. The short introduction at the top is written by
hand and kept in INTRO below. Run it from the backend folder after changing any route or field:

    py scripts/generate_api_doc.py            # writes ../docs/API.md
    py scripts/generate_api_doc.py --check    # exits 1 if docs/API.md is out of date (writes nothing)
    py scripts/generate_api_doc.py --out file.md   # write somewhere else

It never touches your real database: it loads the app on a throw-away temporary one.
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
DOC_FILE = BACKEND.parent / "docs" / "API.md"

INTRO = """# SILONG API reference

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

**Two websites (CORS).** The user site (`http://localhost:5173`) and the admin console (`http://localhost:5174`) call this
backend from the browser. Only the origins in `CORS_ORIGINS` (`backend/.env`; default: those two sites on `localhost` and
`127.0.0.1`) get CORS headers; a browser from any other website cannot read an answer. Allowed request headers are
`Authorization`, `X-Phone-Id` and `Content-Type`; `X-Total-Count` can be read. The token is only read from the
`Authorization` header, never from a URL, a query or a cookie. `*` (any website) works only when it is written in
`CORS_ORIGINS` on purpose.

**Roles.** There is one role, Admin. Nothing is locked by role: every Admin can use every Admin endpoint.

| Role | Who | Can do |
| --- | --- | --- |
| Public | Anyone, no sign-in | Read the map, weather, advisories and numbers; send a status update, a report or a new place (some need `X-Phone-Id`) |
| Admin | Signed-in Admin (`role` is always `\"admin\"`) | Everything public, plus everything under `/api/admin`: reports, places to approve, status overrides, accounts, the audit log, blocked phones, advisories, official sources and emergency numbers. Removing, restoring and listing removed centers (`/api/evacuation-centers`) are Admin endpoints too |

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

1. Sign in (flow 1). `GET /api/admin/reports` lists open reports; poll it about every `refresh_seconds`. `status=new|handling|resolved|all` narrows it (`resolved` includes reports marked false).
2. `POST /api/admin/reports/{id}/take` (no body). If another Admin is handling it you take it over (it is reassigned to you); a `409` only means it is already closed. `POST /api/admin/reports/{id}/release` gives any open report back to New.
3. `POST /api/admin/reports/{id}/resolve` with `{"what_was_done": "Team sent, family moved to the gym"}`.
4. Use `mark-false` (`{"reason": "..."}`) instead of `resolve` for a false report.

**4. A user adds a place and an Admin approves it**

1. With `X-Phone-Id`, `POST /api/evacuation-centers` with `{"name", "center_type": "temporary", "max_capacity", "latitude", "longitude", ...}`. Answer `201`, with `"approval_status": "pending"`.
2. `GET /api/facilities` with the same header shows that phone its own pending place; everybody else does not see it yet.
3. An Admin signs in, `GET /api/admin/places` (the queue; `possible_duplicate` is set when a same-name center is within 30 m), then `POST /api/admin/places/{id}/approve` (or `.../reject` with an optional `reason`).
4. An Admin can fix details later with `PATCH /api/admin/places/{id}`.
"""

AREAS = {  # tag -> heading, in this order; a tag not listed here is added at the end under its own name
    "accounts": "Sign-in and accounts",
    "phone blocks": "Phone blocks",
    "reports": "Help requests and hazard reports",
    "evacuation centers": "Evacuation centers (add, remove, restore)",
    "places (admin)": "Places review and status corrections (Admin)",
    "content": "Weather, advisories and emergency numbers",
    "chat": "Chat",
    "admin console": "Admin console helpers (badge counts, my recent actions)",
    "contact settings": "Contact settings",
}


def load_app():
    """The app on a temporary database, so no real data file is created or touched."""
    tmp = tempfile.mkdtemp(prefix="silong-apidoc-")
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(tmp) / 'doc.db'}"
    from app.main import app
    return app


def walk_routes(routes):
    """Every route that has a path, also inside included routers (works across FastAPI versions)."""
    for r in routes:
        if hasattr(r, "dependant") and hasattr(r, "path"):
            yield r
        else:
            inner = getattr(getattr(r, "original_router", None), "routes", None) or getattr(r, "routes", None)
            if inner:
                yield from walk_routes(inner)


def route_access(route):
    """(who can call it, extra header note) from the route's own dependencies."""
    from app import auth
    from app.report_routes import optional_phone, required_phone
    calls = set()

    def visit(dep):
        calls.add(dep.call)
        for sub in dep.dependencies:
            visit(sub)

    visit(route.dependant)
    if auth.require_admin in calls:
        who = "Admin"
    elif auth.current_user in calls:
        who = "Any signed-in Admin"
    elif auth.optional_staff in calls:
        who = "Public (a signed-in Admin counts as an official)"
    elif auth.bearer_token in calls:
        who = "Public (sends the token it wants to end)"
    else:
        who = "Public"
    note = ""
    if required_phone in calls:
        note = "X-Phone-Id required"
    elif optional_phone in calls:
        note = "X-Phone-Id optional"
    return who, note


def _resolve(schema, spec):
    ref = schema.get("$ref")
    if ref:
        return spec["components"]["schemas"][ref.split("/")[-1]]
    return schema


def type_of(schema, spec):
    """A short readable type, e.g. string, integer, array of FacilityOut, object or null."""
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [type_of(s, spec) for s in schema[key]]
            return " or ".join(dict.fromkeys(parts))
    if "enum" in schema:
        return "one of " + ", ".join(f'`{v}`' for v in schema["enum"])
    t = schema.get("type")
    if t == "array":
        return "array of " + type_of(schema.get("items", {}), spec)
    if t == "object" and "additionalProperties" in schema and schema["additionalProperties"] is not True:
        return "object of " + type_of(schema["additionalProperties"], spec)
    fmt = schema.get("format")
    if t == "string" and fmt == "date-time":
        return "string (date and time, UTC)"
    return (t or "any") + (f" ({fmt})" if fmt else "")


def fields_of(schema, spec):
    """[(name, type, required, note)] for an object schema; [] when it has no named fields."""
    schema = _resolve(schema, spec)
    if "allOf" in schema and len(schema["allOf"]) == 1:
        schema = _resolve(schema["allOf"][0], spec)
    rows = []
    required = set(schema.get("required", []))
    for name, prop in schema.get("properties", {}).items():
        notes = []
        if prop.get("description"):
            notes.append(prop["description"].strip().replace("\n", " "))
        for k, label in (("minimum", "min"), ("maximum", "max"), ("minLength", "min length"), ("maxLength", "max length")):
            if k in prop:
                notes.append(f"{label} {prop[k]}")
        if "default" in prop and prop["default"] is not None:
            notes.append(f"default `{prop['default']}`")
        rows.append((name, type_of(prop, spec), name in required, "; ".join(notes)))
    return rows


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(out)


def field_table(rows):
    return table([(f"`{n}`", t, "required" if r else "optional", note) for n, t, r, note in rows],
                 ("Field", "Type", "Required", "Notes"))


def one_line(text):
    first = (text or "").strip().split("\n\n")[0]
    return " ".join(first.split())


def build() -> str:
    app = load_app()
    spec = app.openapi()
    access = {(m.upper(), r.path): route_access(r) for r in walk_routes(app.routes) for m in (r.methods or []) if m.upper() != "HEAD"}

    ops = []  # (area tag, path, method, operation)
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                ops.append(((op.get("tags") or ["other"])[0], path, method.upper(), op))

    order = list(AREAS)
    tags = sorted({t for t, *_ in ops}, key=lambda t: (order.index(t) if t in order else len(order), t))  # same order on every run
    out = [INTRO, f"This reference lists **{len(ops)} endpoints** in {len(tags)} areas.\n"]
    used_shapes = set()

    def collect(schema):  # remember every named shape an endpoint mentions
        if isinstance(schema, dict):
            if "$ref" in schema:
                name = schema["$ref"].split("/")[-1]
                if name not in used_shapes:
                    used_shapes.add(name)
                    collect(spec["components"]["schemas"][name])
            for v in schema.values():
                collect(v)
        elif isinstance(schema, list):
            for v in schema:
                collect(v)

    for tag in tags:
        heading = AREAS.get(tag, tag.capitalize())
        group = [o for o in ops if o[0] == tag]
        out.append(f"\n---\n\n## {heading}\n")
        out.append(table(
            [(f"`{m}`", f"`{p}`", access.get((m, p), ("?", ""))[0] + (f" ({access[(m, p)][1]})" if access.get((m, p), ("", ""))[1] else ""),
              one_line(op.get("summary") if op.get("description") is None else op.get("description")))
             for _, p, m, op in group],
            ("Method", "Path", "Who can call it", "What it does")))
        for _, path, method, op in group:
            who, note = access.get((method, path), ("?", ""))
            out.append(f"\n### `{method} {path}`\n")
            out.append(f"**Who:** {who}" + (f" ({note})" if note else "") + "\n")
            desc = (op.get("description") or op.get("summary") or "").strip()
            if desc:
                out.append(" ".join(desc.split()) + "\n")
            # The Authorization and X-Phone-Id headers are described in "Who" and the introduction.
            params = [p for p in op.get("parameters", []) if p["name"].lower() not in ("authorization", "x-phone-id")]
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            rows = [(p["name"], type_of(p.get("schema", {}), spec), bool(p.get("required")),
                     f"in {p['in']}" + (f"; {one_line(p['description'])}" if p.get("description") else "")) for p in params]
            if note:
                rows.insert(0, ("X-Phone-Id", "string (16 to 64 letters, digits, - or _)", "required" in note, "in header"))
            if body:
                collect(body)
                rows += [(n, t, r, ("in body" + (f"; {nt}" if nt else ""))) for n, t, r, nt in fields_of(body, spec)]
            out.append("**Request fields**\n")
            out.append(field_table(rows) if rows else "None.")
            responses = op.get("responses", {})
            ok = next((c for c in responses if c.startswith("2")), None)
            out.append(f"\n**Response** `{ok}`\n")
            resp = responses.get(ok, {})
            schema = resp.get("content", {}).get("application/json", {}).get("schema")
            if schema is None:
                out.append("No body.")
            else:
                collect(schema)
                shown = _resolve(schema, spec) if "$ref" in schema else schema
                if shown.get("type") == "array":
                    out.append(f"A list of `{type_of(shown.get('items', {}), spec)}`.\n")
                    fr = fields_of(shown.get("items", {}), spec)
                else:
                    fr = fields_of(schema, spec)
                    if not fr:
                        out.append(f"`{type_of(schema, spec)}`.")
                out.append(field_table(fr) if fr else "")
            for hname, h in resp.get("headers", {}).items():
                out.append(f"\nResponse header `{hname}`: {h.get('description', '')}")

    if used_shapes:
        out.append("\n---\n\n## Shapes used above\n")
        for name in sorted(used_shapes):
            fr = fields_of(spec["components"]["schemas"][name], spec)
            if fr:
                out.append(f"\n### {name}\n")
                out.append(field_table(fr))
    return "\n".join(out).rstrip() + "\n"


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    check = "--check" in args
    out_file = Path(args[args.index("--out") + 1]) if "--out" in args else DOC_FILE
    text = build()
    if check:
        if not DOC_FILE.exists() or DOC_FILE.read_text(encoding="utf-8") != text:
            print("docs/API.md is out of date. Run: py scripts/generate_api_doc.py")
            return 1
        print("docs/API.md is up to date.")
        return 0
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {out_file} ({text.count(chr(10))} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
