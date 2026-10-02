"""NEXUS weekly snapshot: one week compared with the week before it.

A week is the 7 days ending on a chosen date. Every comparison is hour for
hour: an hour counts only if it was recorded in both weeks (a meter gap never
looks like a drop in use), and the share of comparable hours is reported.

Print a snapshot:   python -m nexus.kpis 2017-11-03
"""
import sys

import pandas as pd

from nexus.data import ENERGY_WARNINGS, OUT

WEEK = pd.Timedelta(days=7)
HOURS_PER_WEEK = 168
MIN_COVERAGE = 0.5   # fewer comparable hours than this -> "insufficient data", no number
SPARK_DAYS = 28      # sparklines show the 4 weeks ending on the chosen date


def window(week_end):
    """[start, end) of the 7 days ending on `week_end` (inclusive)."""
    end = pd.Timestamp(week_end).normalize() + pd.Timedelta(days=1)
    return end - WEEK, end


def default_week_end():
    """The latest date with both energy and Wi-Fi data."""
    e = pd.read_parquet(OUT / "energy_hourly.parquet", columns=["hour", "kwh"]).dropna()
    o = pd.read_parquet(OUT / "occupancy_hourly.parquet", columns=["hour", "occ_mean"]).dropna()
    return min(e["hour"].max(), o["hour"].max()).normalize()


def _matched(df, value, week_end):
    """Rows of this week next to the same building-hour a week earlier, both recorded."""
    start, end = window(week_end)
    this = df[(df["hour"] >= start) & (df["hour"] < end)]
    prev = df[(df["hour"] >= start - WEEK) & (df["hour"] < start)]
    prev = prev.assign(hour=prev["hour"] + WEEK)[["hour", "building", value]]
    both = this[["hour", "building", value]].merge(
        prev, on=["hour", "building"], suffixes=("", "_prev"))
    return both.dropna(subset=[value, f"{value}_prev"])


def compare(df, value, week_end):
    """Total this week vs last week over comparable building-hours, overall and per building."""
    buildings = df["building"].nunique()
    both = _matched(df, value, week_end)
    coverage = len(both) / (buildings * HOURS_PER_WEEK) if buildings else 0.0
    per = both.groupby("building").agg(this=(value, "sum"), prev=(f"{value}_prev", "sum"),
                                       hours=(value, "size"))
    per["change"] = per["this"] / per["prev"] - 1
    per = per[per["hours"] >= MIN_COVERAGE * HOURS_PER_WEEK]
    this, prev = both[value].sum(), both[f"{value}_prev"].sum()
    ok = coverage >= MIN_COVERAGE and prev > 0
    return {
        "this": this if ok else None,
        "prev": prev if ok else None,
        "change": this / prev - 1 if ok else None,
        "coverage": coverage,
        "per_building": per.reset_index(),
    }


def daily(df, value, week_end, how="mean"):
    """One value per day for the sparkline: the 4 weeks ending on `week_end`."""
    end = window(week_end)[1]
    d = df[(df["hour"] >= end - pd.Timedelta(days=SPARK_DAYS)) & (df["hour"] < end)]
    s = d.groupby(d["hour"].dt.normalize())[value].agg(how)
    return s.reindex(pd.date_range(end - pd.Timedelta(days=SPARK_DAYS), periods=SPARK_DAYS))


def snapshot(df, events, occ, week_end):
    """Everything the Overview cards and headline need, from the app's own tables.

    df:     hourly energy with baseline flags (nexus.resource.add_baseline)
    events: unusual events (nexus.resource.find_events)
    occ:    hourly occupancy (nexus.institutional.load_occupancy or the processed table)
    """
    start, end = window(week_end)
    energy = df[~df["building"].isin(ENERGY_WARNINGS)][["hour", "building", "kwh"]]
    full = pd.read_parquet(OUT / "energy_hourly.parquet")
    full = full[~full["building"].isin(ENERGY_WARNINGS)]
    # Only hours while each meter was in service count as gaps (some started later).
    span = full.dropna(subset=["kwh"]).groupby("building")["hour"].agg(["min", "max"])
    full = full.join(span, on="building")
    full = full[(full["hour"] >= full["min"]) & (full["hour"] <= full["max"])]

    def missing_share(lo, hi):
        w = full[(full["hour"] >= lo) & (full["hour"] < hi)]
        return w["kwh"].isna().mean() if len(w) else None

    high = events[events["direction"] == "high"]
    flagged = df[df["flag"] == "high"].assign(n=1)
    gaps = full.assign(missing=full["kwh"].isna().astype(float))
    return {
        "week_end": pd.Timestamp(week_end).normalize(),
        "start": start,
        "energy": compare(energy, "kwh", week_end),
        "energy_daily": daily(energy, "kwh", week_end),
        "wifi": compare(occ[["hour", "building", "occ_mean"]], "occ_mean", week_end),
        "wifi_daily": daily(occ, "occ_mean", week_end),
        "events": int(((high["start"] >= start) & (high["start"] < end)).sum()),
        "events_prev": int(((high["start"] >= start - WEEK) & (high["start"] < start)).sum()),
        "events_daily": daily(flagged, "n", week_end, how="sum").fillna(0),
        "missing": missing_share(start, end),
        "missing_prev": missing_share(start - WEEK, start),
        "missing_daily": daily(gaps, "missing", week_end),
    }


def _compared(change, what):
    """'5% higher', '3% lower' or 'about the same', for a change given as a fraction."""
    if abs(change) < 0.005:
        return f"{what} about the same"
    return f"{what} {abs(change):.0%} {'higher' if change > 0 else 'lower'}"


def headline(snap):
    """The week in plain words, built only from the snapshot.

    Returns {"when": ..., "main": one sentence, "details": [short sentences]}.
    """
    e, w = snap["energy"], snap["wifi"]
    out = {"when": f"Week ending {snap['week_end']:%a %-d %b %Y}", "details": []}
    if e["change"] is None:
        out["main"] = "Not enough recorded hours to compare with the week before."
        return out
    out["main"] = (f"{_compared(e['change'], 'Campus electricity was')} than the week before."
                   .replace("about the same than", "about the same as"))
    per = e["per_building"]
    if not per.empty:
        b = per.loc[per["change"].abs().idxmax()]
        out["details"].append(f"Biggest change: {b['building']}, "
                              f"{_compared(b['change'], '').strip()}.")
    if w["change"] is not None:
        out["details"].append(f"{_compared(w['change'], 'Wi-Fi activity was')}.")
    out["details"].append(f"Compared hour for hour, using the {e['coverage']:.0%} of building-hours "
                          "recorded in both weeks.")
    return out


def main(week_end=None):
    from nexus.resource import add_baseline, find_events, load_energy

    df = add_baseline(load_energy())
    occ = pd.read_parquet(OUT / "occupancy_hourly.parquet")
    week_end = pd.Timestamp(week_end) if week_end else default_week_end()
    s = snapshot(df, find_events(df), occ, week_end)
    print(f"WEEK {s['start']:%Y-%m-%d} to {s['week_end']:%Y-%m-%d}, vs the 7 days before")
    for key, unit in [("energy", "kWh"), ("wifi", "people-hours")]:
        c = s[key]
        if c["change"] is None:
            print(f"  {key:7} insufficient data ({c['coverage']:.0%} of hours comparable)")
        else:
            print(f"  {key:7} {c['this']:>12,.0f} vs {c['prev']:>12,.0f} {unit:13} "
                  f"{c['change']:+.1%}  ({c['coverage']:.0%} of hours comparable)")
    print(f"  events  {s['events']} vs {s['events_prev']} higher-than-usual events starting")
    print(f"  missing {s['missing']:.1%} vs {s['missing_prev']:.1%} of building-hours with no reading")
    print()
    h = headline(s)
    print(f"  {h['when']}: {h['main']}")
    for line in h["details"]:
        print("   ", line)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
