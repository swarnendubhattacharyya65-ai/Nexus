"""Download IIIT-Delhi's building outlines from OpenStreetMap (run once, needs internet).

Run from the repo root in the codespace:   python scripts/fetch_campus.py

Writes data/campus/osm_raw.json (the raw answer) and data/campus/buildings.geojson
(one feature per building, plus the campus boundary if OpenStreetMap has one),
then prints every building found so the I-BLEND buildings can be matched to them.

Map data (c) OpenStreetMap contributors, Open Database License (ODbL).
"""
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

CENTER = (28.54444, 77.27250)   # IIIT-Delhi, Okhla Phase III (Wikipedia)
RADIUS = 450                    # metres; the campus is about 10 hectares
SERVERS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
OUT = Path("data/campus")

QUERY = f"""
[out:json][timeout:90];
(
  nwr["amenity"~"university|college"]["name"~"Indraprastha|IIIT",i](around:1500,{CENTER[0]},{CENTER[1]});
)->.campus;
.campus out geom;
way["building"](around:{RADIUS},{CENTER[0]},{CENTER[1]});
out geom;
"""


def fetch():
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    for url in SERVERS:
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "NEXUS-student-project"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # try the next server
            print(f"{url} failed: {e}")
    raise SystemExit("Could not reach any Overpass server. Try again in a minute.")


def ring(geometry):
    return [[round(p["lon"], 7), round(p["lat"], 7)] for p in geometry]


def area_m2(coords):
    """Approximate area of a small lon/lat polygon in square metres."""
    lat0 = math.radians(sum(c[1] for c in coords) / len(coords))
    xs = [math.radians(c[0]) * 6371000 * math.cos(lat0) for c in coords]
    ys = [math.radians(c[1]) * 6371000 for c in coords]
    return abs(sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(xs) - 1))) / 2


def main():
    raw = fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "osm_raw.json").write_text(json.dumps(raw))

    features = []
    for el in raw["elements"]:
        tags = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            coords = ring(el["geometry"])
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            kind = "building" if "building" in tags else "campus"
            features.append({
                "type": "Feature",
                "id": f"way/{el['id']}",
                "properties": {"osm_id": f"way/{el['id']}", "kind": kind,
                               "name": tags.get("name", ""), "building": tags.get("building", ""),
                               "levels": tags.get("building:levels", ""),
                               "height": tags.get("height", ""),
                               "area_m2": round(area_m2(coords))},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            })
        elif el["type"] == "relation" and "members" in el:   # campus boundary as a relation
            for m in el["members"]:
                if m.get("role") == "outer" and "geometry" in m:
                    coords = ring(m["geometry"])
                    features.append({
                        "type": "Feature", "id": f"relation/{el['id']}",
                        "properties": {"osm_id": f"relation/{el['id']}", "kind": "campus",
                                       "name": tags.get("name", "")},
                        "geometry": {"type": "LineString", "coordinates": coords},
                    })

    (OUT / "buildings.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": features,
         "attribution": "(c) OpenStreetMap contributors, ODbL"}, indent=1))

    buildings = [f for f in features if f["properties"]["kind"] == "building"]
    campus = [f for f in features if f["properties"]["kind"] == "campus"]
    print(f"Campus outline: {'found: ' + campus[0]['properties']['name'] if campus else 'not found'}")
    print(f"Buildings within {RADIUS} m: {len(buildings)}\n")
    print(f"{'osm_id':16}{'area m2':>9}  {'levels':>6}  {'type':12} name")
    for f in sorted(buildings, key=lambda f: -f["properties"]["area_m2"])[:40]:
        p = f["properties"]
        print(f"{p['osm_id']:16}{p['area_m2']:>9,}  {p['levels']:>6}  {p['building'][:12]:12} {p['name']}")
    print("\nSaved data/campus/buildings.geojson")


if __name__ == "__main__":
    main()
