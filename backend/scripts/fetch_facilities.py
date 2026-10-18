"""
Fetch hospitals, clinics and evacuation/assembly points for Batangas City
from OpenStreetMap (Overpass API, free, no key) and save them to
backend/data/facilities.json, which the backend loads on startup.

Run from the backend folder (needs internet, no extra installs):
    py scripts/fetch_facilities.py

Then restart the backend. Open data/facilities.json to review the results
and delete any rows that are wrong before committing.

Data (c) OpenStreetMap contributors, ODbL. OSM coverage in the Philippines is
uneven, so check the output; evacuation centers especially are poorly tagged.
"""
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
AREA_NAME = "Batangas City"
# Fallback box (south, west, north, east) if the named area is not found.
FALLBACK_BBOX = (13.66, 120.97, 13.86, 121.14)
OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "facilities.json"
DATA_DIR = OUT_FILE.parent
# Names to always drop (one per line, # for comments). Survives re-running.
EXCLUDE_FILE = DATA_DIR / "exclude.txt"
# Facilities you add by hand (e.g. evacuation centers). Merged on every run.
MANUAL_FILE = DATA_DIR / "manual_facilities.json"

# Individual doctors' offices are mapped as "clinics" under the doctor's name
# (e.g. "Jelyn Mandigma, M.D."). They are noisy and stack on one building, so
# clinics whose names look like that are skipped. Hospitals are never filtered.
# Health centers and maternity/lying-in clinics are often tagged "hospital" in
# OpenStreetMap. They are moved to the clinic category (unless the name says
# "hospital").
SMALL_FACILITY_RE = re.compile(r"health\s*cent(er|re)|maternity|lying[\s-]?in", re.I)
# Same-name entries closer than this are treated as one place (duplicate points).
DUPLICATE_METERS = 100

PERSONAL_RE = re.compile(r"(?<!\w)(m\.?d\.?|d\.?m\.?d\.?|dr\.?|dra\.?|doc|dds)(?!\w)", re.I)

TAGS = (
    'nwr["amenity"~"^(hospital|clinic)$"]{f};'
    'nwr["healthcare"~"^(hospital|clinic)$"]{f};'
    'nwr["emergency"="assembly_point"]{f};'
)


def build_query(use_bbox: bool) -> str:
    if use_bbox:
        s, w, n, e = FALLBACK_BBOX
        body = TAGS.format(f=f"({s},{w},{n},{e})")
        return f"[out:json][timeout:60];({body});out center tags;"
    body = TAGS.format(f="(area.a)")
    return (
        f'[out:json][timeout:60];'
        f'area["name"="{AREA_NAME}"]["boundary"="administrative"]->.a;'
        f"({body});out center tags;"
    )


def fetch(query: str) -> list:
    data = urllib.parse.urlencode({"data": query}).encode()
    last_error = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(
                url, data=data, headers={"User-Agent": "bayanialerto-student-project/0.1"}
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp).get("elements", [])
        except Exception as e:  # try the next mirror
            last_error = e
            print(f"  {url} failed: {e}")
    raise SystemExit(f"All Overpass endpoints failed. Last error: {last_error}")


def classify(tags: dict):
    if tags.get("amenity") == "hospital" or tags.get("healthcare") == "hospital":
        return "hospital"
    if tags.get("amenity") == "clinic" or tags.get("healthcare") == "clinic":
        return "clinic"
    if tags.get("emergency") == "assembly_point":
        return "evacuation_center"
    return None


def normalize(elements: list) -> list:
    results, seen = [], set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        kind = classify(tags)
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not (name and kind and lat is not None and lon is not None):
            continue  # skip unnamed or incomplete entries
        key = (name.lower(), round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        address = ", ".join(
            p for p in (
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:suburb") or tags.get("addr:barangay"),
                tags.get("addr:city") or "Batangas City",
            ) if p
        )
        results.append({
            "name": name,
            "type": kind,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "address": address,
            "contact": tags.get("phone") or tags.get("contact:phone"),
            "notes": f"Source: OpenStreetMap {el.get('type')}/{el.get('id')}",
        })
    order = {"hospital": 0, "clinic": 1, "evacuation_center": 2}
    return sorted(results, key=lambda r: (order[r["type"]], r["name"]))


def fix_types(facilities: list):
    """Move health centers / maternity clinics tagged 'hospital' to 'clinic'."""
    moved = []
    for f in facilities:
        name = f["name"].lower()
        if f["type"] == "hospital" and "hospital" not in name and SMALL_FACILITY_RE.search(name):
            f["type"] = "clinic"
            moved.append(f["name"])
    return facilities, moved


def _meters(a: dict, b: dict) -> float:
    dy = (a["latitude"] - b["latitude"]) * 110540
    dx = (a["longitude"] - b["longitude"]) * 111320 * math.cos(math.radians(a["latitude"]))
    return math.hypot(dx, dy)


def remove_duplicates(facilities: list):
    """Drop entries with the same name and type within DUPLICATE_METERS of one already kept."""
    kept, dropped = [], []
    for f in facilities:
        if any(
            k["type"] == f["type"] and k["name"].lower() == f["name"].lower()
            and _meters(k, f) <= DUPLICATE_METERS
            for k in kept
        ):
            dropped.append(f["name"])
        else:
            kept.append(f)
    return kept, dropped


def load_exclude() -> set:
    if not EXCLUDE_FILE.exists():
        return set()
    lines = EXCLUDE_FILE.read_text(encoding="utf-8").splitlines()
    return {l.strip().lower() for l in lines if l.strip() and not l.strip().startswith("#")}


def load_manual() -> list:
    if not MANUAL_FILE.exists():
        return []
    items, required = [], ("name", "type", "latitude", "longitude")
    for row in json.loads(MANUAL_FILE.read_text(encoding="utf-8")):
        if not all(k in row for k in required):
            print(f"  Skipping manual entry missing one of {required}: {row}")
            continue
        items.append({
            "name": row["name"], "type": row["type"],
            "latitude": row["latitude"], "longitude": row["longitude"],
            "address": row.get("address"), "contact": row.get("contact"),
            "notes": row.get("notes", "Added manually"),
        })
    return items


def apply_filters(facilities: list, exclude: set):
    """Return (kept, skipped_names). Drops excluded names and personal clinics."""
    kept, skipped = [], []
    for f in facilities:
        if f["name"].lower() in exclude:
            skipped.append(f["name"] + "  [exclude.txt]")
        elif f["type"] == "clinic" and PERSONAL_RE.search(f["name"]):
            skipped.append(f["name"] + "  [looks like a doctor's office]")
        else:
            kept.append(f)
    return kept, skipped


def main():
    print(f"Querying OpenStreetMap for {AREA_NAME}...")
    facilities = normalize(fetch(build_query(use_bbox=False)))
    if not facilities:
        print("Named area returned nothing; retrying with a bounding box...")
        facilities = normalize(fetch(build_query(use_bbox=True)))
    if not facilities:
        raise SystemExit("No facilities found. Nothing was written.")
    facilities, moved = fix_types(facilities)
    if moved:
        print(f"Moved {len(moved)} 'hospital' entries to clinics (health centers / maternity):")
        for name in moved:
            print(f"  - {name}")
    facilities, skipped = apply_filters(facilities, load_exclude())
    if skipped:
        print(f"Skipped {len(skipped)} entries:")
        for name in skipped:
            print(f"  - {name}")
    facilities, dupes = remove_duplicates(facilities)
    if dupes:
        print(f"Removed {len(dupes)} duplicate points: {', '.join(dupes)}")
    manual = load_manual()
    if manual:
        print(f"Added {len(manual)} manual entries from {MANUAL_FILE.name}")
    order = {"hospital": 0, "clinic": 1, "evacuation_center": 2}
    facilities = sorted(facilities + manual, key=lambda r: (order.get(r["type"], 9), r["name"]))
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(facilities, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = {}
    for f in facilities:
        counts[f["type"]] = counts.get(f["type"], 0) + 1
    print(f"Saved {len(facilities)} facilities to {OUT_FILE}: {counts}")


if __name__ == "__main__":
    sys.exit(main())
