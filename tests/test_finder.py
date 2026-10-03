"""Offline tests for college search and place lookup (run: python tests/test_finder.py).

The real repositories and OpenStreetMap are not called; each is replaced by a fake that
returns the shape the real service returns.
"""
import io
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from nexus import finder, place
from nexus.place import Unreachable


def hourly_csv(weeks=6):
    t = pd.date_range("2023-01-02", periods=24 * 7 * weeks, freq="h")
    rng = np.random.default_rng(1)
    base = 40 + 20 * np.sin(np.arange(len(t)) * 2 * np.pi / 24)
    df = pd.DataFrame({"datetime": t.strftime("%Y-%m-%d %H:%M"),
                       "Main Block (kWh)": base + rng.normal(0, 2, len(t)),
                       "Hostel (kWh)": base / 2 + rng.normal(0, 1, len(t))})
    return df.to_csv(index=False).encode()


def rec(title="PES University hourly electricity consumption", lic="cc-by-4.0", name="meters.csv"):
    return {"source": "Zenodo", "title": title, "text": "Hourly electricity consumption of buildings.",
            "url": "https://zenodo.org/records/1", "licence": lic, "files": [(name, 1000, "http://x/f")]}


def boom(q):
    raise Unreachable("down")


# registry
r = finder.search("IIIT-Delhi, New Delhi")
assert r["status"] == "found" and r["registry"] == "iiitd", r
assert finder.search("iiitd")["registry"] == "iiitd"
assert finder.search("Fox", {"A": (lambda q: [], None)})["status"] == "unavailable"
assert finder.search("BDG2 Fox")["registry"] == "sample"

# nothing reachable -> unreachable, not unavailable
r = finder.search("PES University", {"A": (boom, None), "B": (boom, None)})
assert r["status"] == "unreachable" and len(r["failed"]) == 2, r

# reachable, nothing named PES -> unavailable
r = finder.search("PES University", {"A": (lambda q: [rec("Stanford campus energy")], None)})
assert r["status"] == "unavailable" and r["checked"] == ["A"], r

# found and analysed (wide format, units in headers)
r = finder.search("PES University", {"A": (lambda q: [rec()], None)}, download=lambda u: hourly_csv())
assert r["status"] == "found", r
ds = r["dataset"]
assert sorted(ds.energy["building"].unique()) == ["Hostel", "Main Block"]
assert "PES" not in r["source"] or "Not PES data" in r["source"]
assert ds.has_calendar is False

# closed licence is listed, not downloaded
called = []
r = finder.search("PES University", {"A": (lambda q: [rec(lic="cc-by-nc-4.0")], None)},
                  download=lambda u: called.append(u) or b"")
assert r["status"] == "unavailable" and not called and r["candidates"][0]["why"].startswith("its licence"), r

# a file with no unit in its headers is refused, with the reason
bad = pd.DataFrame({"time": pd.date_range("2023-01-01", periods=2000, freq="h").astype(str),
                    "usage": np.arange(2000.0)}).to_csv(index=False).encode()
r = finder.search("PES University", {"A": (lambda q: [rec()], None)}, download=lambda u: bad)
assert r["status"] == "unavailable" and "clear unit" in r["tried"][0], r

# too short is refused by the importer
r = finder.search("PES University", {"A": (lambda q: [rec()], None)}, download=lambda u: hourly_csv(2))
assert r["status"] == "unavailable" and "days" in r["tried"][0], r

# place: only educational results count
rows = [{"type": "city", "boundingbox": ["1", "2", "3", "4"], "lat": "1", "lon": "1", "display_name": "x"},
        {"type": "university", "name": "PES University", "display_name": "PES University, Bengaluru",
         "boundingbox": ["12.9", "12.91", "77.5", "77.51"], "lat": "12.905", "lon": "77.505",
         "osm_type": "way", "osm_id": 5}]
p = place.geocode("PES", http=lambda *a, **k: rows)
assert p["name"] == "PES University" and p["bbox"][0] < 12.9
assert place.geocode("Paris", http=lambda *a, **k: rows[:1]) is None
big = dict(rows[1], boundingbox=["10", "14", "70", "80"])
pb = place.geocode("x", http=lambda *a, **k: [big])
assert pb["bbox"][2] - pb["bbox"][0] < 0.02          # a huge box is cut down

# buildings from an Overpass answer; matching is by name and never ambiguous
def way(i, name, x):
    ring = [{"lon": x, "lat": 12.9}, {"lon": x + .0004, "lat": 12.9}, {"lon": x + .0004, "lat": 12.9004},
            {"lon": x, "lat": 12.9004}, {"lon": x, "lat": 12.9}]
    return {"type": "way", "id": i, "geometry": ring, "tags": {"building": "yes", "name": name, "building:levels": "4"}}
feats = place.features([way(1, "Main Block", 77.5), way(2, "Boys Hostel", 77.51), way(3, "Boys Hostel", 77.52),
                        {"type": "way", "id": 9, "geometry": [{"lon": 1, "lat": 1}]}])
assert len(feats) == 3 and feats[0]["properties"]["height"] == 14.0
out, found = place.match_buildings(feats, ["Main Block", "Boys Hostel", "Library"])
assert found == {"Main Block": "Main Block"}, found      # Hostel is on two outlines: not guessed
print("all finder tests passed")
