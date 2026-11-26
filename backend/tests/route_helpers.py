"""
Shared by the test files that look at the whole route table (not a test file itself: run_all.py only
runs test_*.py).

`all_routes(app)` finds every API route WITHOUT a hand-kept list of modules:
  - every app/*_routes.py module that has a `router`, and
  - the routes written straight on the app in main.py.
`test_the_route_table_is_complete` (test_accounts.py) checks it against the app's own OpenAPI list,
so a route that this helper cannot see fails a test instead of slipping past the sweeps.
"""
import importlib
import pkgutil
import re

import app as app_package
from app import auth


def uses(dependant, target) -> bool:
    """True if `target` (for example auth.require_admin) is among the dependencies of a route, at any depth."""
    return dependant.call is target or any(uses(d, target) for d in dependant.dependencies)


def all_routes(app):
    """[(METHOD, path, route)], one entry per method, HEAD left out, in a stable order."""
    seen, found = set(), []
    routes = []
    for info in pkgutil.iter_modules(app_package.__path__):
        if info.name.endswith("_routes"):
            module = importlib.import_module(f"app.{info.name}")
            routes.extend(getattr(getattr(module, "router", None), "routes", []))
    routes.extend(r for r in app.routes if getattr(r, "dependant", None) is not None)  # written on the app itself
    for r in routes:
        if getattr(r, "dependant", None) is None:
            continue
        for method in sorted(r.methods - {"HEAD"}):
            if (method, r.path) not in seen:
                seen.add((method, r.path))
                found.append((method, r.path, r))
    return sorted(found, key=lambda t: (t[1], t[0]))


def openapi_operations(app):
    """{(METHOD, path)} as the app itself lists them (what /docs shows)."""
    return {(m.upper(), p) for p, ops in app.openapi()["paths"].items() for m in ops if m.upper() != "HEAD"}


def kind_of(route) -> str:
    """'admin' (needs require_admin), 'signed-in' (current_user only), 'optional-staff' or 'public'."""
    d = route.dependant
    if uses(d, auth.require_admin):
        return "admin"
    if uses(d, auth.current_user):
        return "signed-in"
    if uses(d, auth.optional_staff):
        return "optional-staff"
    return "public"


def fill(path: str, value: str = "1") -> str:
    """A path with its {parameters} filled in."""
    return re.sub(r"\{[^}]+\}", value, path)
