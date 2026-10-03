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

# what's at stake: savings only as the person's scenario; shifting never claims a saving
df = pd.DataFrame([dict(r, kind="Save energy", title="t") for r in recs])
r6 = df[(df["rule"] == "R6")].iloc[0].to_dict()
line = stake_line(r6, 0.2, 8.0, None, 1_000_000)
assert "If a fix cut that by 20%" in line and "₹" in line, line
r8 = df[df["rule"] == "R8"].iloc[0].to_dict()
line = stake_line(r8, 0.2, 8.0, None, 1_000_000)
assert "does not save energy" in line and "₹" not in line, line
assert stake_line(dict(r6, worth_kind="", at_stake_kwh=float("nan")), 0.2, None, None, None) == ""

# the downloadable checklist has a checkbox per step
md = checklist(df.assign(kind="Save energy"), 0.2, 1_000_000, "Test campus")
assert md.count("- [ ]") == sum(len(r["actions"]) for r in recs)
assert "not diagnoses" in md

# campus total is scaled per building to a full year
assert abs(R.campus_year_kwh(e) - e[e["hour"] > e["hour"].max() - pd.Timedelta(days=365)]["kwh"].sum()) < 1e4

print("all recommendation tests passed")
