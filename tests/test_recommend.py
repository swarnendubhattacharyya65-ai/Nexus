"""Offline tests for the solution-oriented recommendations (R6-R9, playbooks, the tab's wording).

Run:  python tests/test_recommend.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from nexus import playbook as pb, recommend as R   # noqa: E402
from views.recommend import checklist, stake_line   # noqa: E402


def campus(days=400, seed=1):
    """Synthetic hourly kWh for 3 buildings with known shapes."""
    rng = np.random.default_rng(seed)
    hours = pd.date_range("2016-01-01", periods=days * 24, freq="h")
    working = hours.dayofweek < 5
    hod = hours.hour
    month_boost = np.where(hours.month.isin([5, 6, 7]), 2.0, 1.0)          # hot months
    office_day = ((hod >= 9) & (hod < 18)).astype(float)
    rows = []
    for name, base, day, weekend_on, season in [
        ("Main Office", 50, 40, 0.9, False),   # big always-on, runs on weekends -> R6, R7
        ("Hostel A", 20, 10, 1.0, True),       # residence: R7 must not apply; seasonal -> R9
        ("Library", 2, 60, 0.0, False),        # small base, shut on days off -> neither R6 nor R7
    ]:
        on = np.where(working, 1.0, weekend_on)
        kwh = base + day * office_day * on
        if season:
            kwh = kwh * month_boost
        kwh = kwh + rng.normal(0, 0.5, len(hours))
        rows.append(pd.DataFrame({"hour": hours, "building": name, "kwh": kwh, "working_day": working}))
    df = pd.concat(rows, ignore_index=True)
    # one sharp campus peak
    df.loc[(df["hour"] == hours[-500]) & (df["building"] == "Library"), "kwh"] += 400
    return df


e = campus()
recs = R.from_energy(e)
by = {(r["rule"], r["building"]) for r in recs}
assert ("R6", "Main Office") in by, by
assert ("R6", "Library") not in by, by                       # small always-on share
assert ("R7", "Main Office") in by, by
assert not any(r == "R7" and b == "Hostel A" for r, b in by), "residences are meant to run on days off"
assert ("R7", "Library") not in by, by
assert ("R9", "Hostel A") in by, by
assert ("R8", R.CAMPUS) in by, by

# every recommendation carries a usable plan
for r in recs:
    assert r["causes"] and r["actions"] and r["verify"], r["rule"]
    assert all(stage in pb.STAGES for stage, _, _ in r["actions"])
    assert r["next_step"] == r["actions"][0][1]

# unreliable meters are left out; too little data is skipped, not guessed
assert not any(r["building"] == "Main Office" for r in R.from_energy(e, {"Main Office": "bad meter"}))
assert R.from_energy(e[e["hour"] < e["hour"].min() + pd.Timedelta(days=20)]) == []
assert R.from_energy(pd.DataFrame()) == []

# building types guessed from names
assert pb.building_type("Boys dorm") == "residence" and pb.building_type("Hostel 3") == "residence"
assert pb.building_type("Lecture Hall") == "academic" and pb.building_type("Mess A") == "dining"
assert pb.building_type("Facilities") == "plant"

# what's at stake: only measured amounts plus "every 10%" arithmetic; shifting never claims a saving
df = pd.DataFrame([dict(r, kind="Save energy", title="t") for r in recs])
r6 = df[(df["rule"] == "R6")].iloc[0].to_dict()
line = stake_line(r6, 8.0, None, 1_000_000)
assert "Every 10% cut here saves" in line and "₹" in line and "20%" not in line, line
assert f"{r6['at_stake_kwh'] * 0.1:,.0f} kWh" in line, line
r8 = df[df["rule"] == "R8"].iloc[0].to_dict()
line = stake_line(r8, 8.0, None, 1_000_000)
assert "does not save energy" in line and "₹" not in line and "Every" not in line, line
assert stake_line(dict(r6, worth_kind="", at_stake_kwh=float("nan")), None, None, None) == ""

# the downloadable checklist has a checkbox per step and says which months it covers
md = checklist(df.assign(kind="Save energy"), 1_000_000, "Test campus", "the 12 months to 3 Feb 2017")
assert md.count("- [ ] ") == sum(len(r["actions"]) for r in recs)
assert "not diagnoses" in md and "3 Feb 2017" in md

# results follow the selected date: a window ending earlier gives different numbers
early = R.from_energy(e, as_of=pd.Timestamp("2016-06-30"))
late = R.from_energy(e)
assert {r["finding"] for r in early} != {r["finding"] for r in late}
assert all("Jun 2016" in r["evidence"] for r in early if r["rule"] == "R6"), [r["evidence"] for r in early]
assert not any(r["rule"] == "R9" for r in early), "only 6 months before June 2016: no seasonal rule"
start, end = R.window(pd.Timestamp("2016-06-30"))
assert end == pd.Timestamp("2016-07-01") and (end - start).days == 365

# events: only those that started in the 12 months before the date
ev = pd.DataFrame({"building": ["Main Office"] * 2, "direction": ["high"] * 2, "hours": [5, 5],
                   "extra_pct": [1.0, 1.0], "extra_kwh": [100.0, 200.0], "actual_kwh": [200.0, 400.0],
                   "expected_kwh": [100.0, 200.0], "samples": [10, 10],
                   "start": pd.to_datetime(["2016-03-05 22:00", "2017-01-07 22:00"]),
                   "end": pd.to_datetime(["2016-03-06 03:00", "2017-01-08 03:00"])})
cal = pd.DataFrame({"date": pd.date_range("2016-01-01", "2017-02-28"), "working_day": True})
assert [r["size"] for r in R.from_events(ev, cal, pd.Timestamp("2016-06-30"))] == [100.0]
assert len(R.from_events(ev, cal)) == 2

# campus total is scaled per building to a full year
assert abs(R.campus_year_kwh(e) - e[e["hour"] > e["hour"].max() - pd.Timedelta(days=365)]["kwh"].sum()) < 1e4

print("all recommendation tests passed")
