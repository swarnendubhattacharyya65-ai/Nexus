"""Find a college on the map and its building outlines, from OpenStreetMap.

geocode(name)   -> the place (centre, box, official name) or None; only educational places count
campus(place)   -> building outlines as map features (a few hundred at most)

Both use free OpenStreetMap services (Nominatim and Overpass), so every call has a short
timeout and a clear failure: `Unreachable` means "could not ask", never "nothing there".
Map data (c) OpenStreetMap contributors, Open Database License (ODbL).
"""
import math
import re

import requests

UA = {"User-Agent": "NEXUS-campus-intelligence/2.0 (student hackathon project)"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
EDUCATION = {"university", "college", "school", "research_institute"}
MAX_SPAN = 0.012        # degrees (about 1.3 km): larger boxes are cut down around the centre
PAD = 0.0015
MAX_BUILDINGS = 500
LEVEL_M, DEFAULT_M = 3.5, 12.0


class Unreachable(Exception):
    """A service did not answer (blocked, offline or timed out)."""


def _json(method, url, **kw):
    try:
        r = requests.request(method, url, headers=UA, timeout=kw.pop("timeout", 12), **kw)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        raise Unreachable(f"{url.split('/')[2]}: {type(e).__name__}") from e


def geocode(name, http=_json):
    """The best educational match for `name`, or None. Raises Unreachable if Nominatim is down."""
    rows = http("GET", NOMINATIM, params={"q": name, "format": "jsonv2", "limit": 8,
                                           "addressdetails": 0})
    for r in rows:
        if r.get("type") in EDUCATION:
            return _place(r)
    return None


def _place(r):
    s, n, w, e = (float(x) for x in r["boundingbox"])     # south, north, west, east
    lat, lon = float(r["lat"]), float(r["lon"])
    if n - s > MAX_SPAN or e - w > MAX_SPAN:               # a very large area: look around the centre
        s, n, w, e = lat - MAX_SPAN / 2, lat + MAX_SPAN / 2, lon - MAX_SPAN / 2, lon + MAX_SPAN / 2
    return {"name": r.get("name") or r["display_name"].split(",")[0],
            "display": r["display_name"], "lat": lat, "lon": lon,
            "bbox": [s - PAD, w - PAD, n + PAD, e + PAD], "osm": f"{r.get('osm_type')}/{r.get('osm_id')}"}


def _height(tags):
    for key, scale in (("height", 1.0), ("building:levels", LEVEL_M)):
        try:
            return round(float(re.split(r"[ ;]", str(tags.get(key, "")))[0]) * scale, 1)
        except ValueError:
            pass
    return DEFAULT_M


def _area(ring):
    lat0 = math.radians(sum(c[1] for c in ring) / len(ring))
    xs = [math.radians(c[0]) * 6371000 * math.cos(lat0) for c in ring]
    ys = [math.radians(c[1]) * 6371000 for c in ring]
    return abs(sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(ring) - 1))) / 2


def features(elements):
    """Overpass `out geom` ways -> map features (largest first, capped). Pure function."""
    out = []
    for el in elements:
        if el.get("type") != "way" or "geometry" not in el or len(el["geometry"]) < 4:
            continue
        ring = [[round(p["lon"], 7), round(p["lat"], 7)] for p in el["geometry"]]
        if ring[0] != ring[-1]:
            continue
        tags = el.get("tags", {})
        out.append((_area(ring), {
            "type": "Feature", "id": el["id"],
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"osm_id": el["id"], "osm_name": tags.get("name", ""), "nexus": None,
                           "height": _height(tags),
                           "center": [sum(c[0] for c in ring[:-1]) / (len(ring) - 1),
                                      sum(c[1] for c in ring[:-1]) / (len(ring) - 1)]}}))
    out.sort(key=lambda t: -t[0])
    return [f for _, f in out[:MAX_BUILDINGS]]


def campus(place, http=_json):
    """Building outlines inside the place's box. Raises Unreachable if no Overpass server answers."""
    s, w, n, e = place["bbox"]
    query = f'[out:json][timeout:25];way["building"]({s},{w},{n},{e});out geom;'
    last = None
    for url in OVERPASS:
        try:
            return features(http("POST", url, data={"data": query}, timeout=30).get("elements", []))
        except Unreachable as err:
            last = err
    raise last


# ---------------------------------------------------------------- matching

STOP = {"block", "building", "the", "of", "and", "centre", "center", "hall"}


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if t not in STOP}


def match_buildings(feats, names):
    """Put each meter building on an outline whose OpenStreetMap name equals or contains it.

    Only unambiguous matches count (one outline for a name, one name for an outline); anything
    else is left unplaced rather than guessed. Returns (features, {name: osm_name}).
    """
    placed, claimed = {}, {}
    for n in names:
        tn = _tokens(n)
        if not tn:
            continue
        hits = [f for f in feats if f["properties"]["osm_name"]
                and (tn <= _tokens(f["properties"]["osm_name"])
                     or _tokens(f["properties"]["osm_name"]) <= tn)]
        if len(hits) == 1:
            claimed.setdefault(hits[0]["id"], []).append(n)
            placed[n] = hits[0]
    out, found = [], {}
    for f in feats:
        who = claimed.get(f["id"], [])
        p = dict(f["properties"])
        if len(who) == 1:
            p["nexus"] = who[0]
            found[who[0]] = p["osm_name"]
        out.append({**f, "properties": p})
    return out, found
