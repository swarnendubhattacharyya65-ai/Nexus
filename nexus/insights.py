"""The Overview's panels: deterministic summaries of one week, from the app's own tables.

Every function takes plain tables and a week-ending date and returns a small table or
list; nothing here is estimated beyond what the methods in resource.py, predictive.py
and institutional.py already do.
"""
import pandas as pd

from nexus.institutional import BUSY, BUSY_LEVEL, QUIET
from nexus.kpis import HOURS_PER_WEEK, compare, window
from nexus.predictive import HORIZON, forecast

TREND_DAYS = 30


def in_service(df, week_end):
    """Analysed buildings whose meter was in service during the week (first to last reading).

    Baseline tables hold only recorded hours, so a meter that was offline all week has no
    rows; this list lets weekly tables show it with 0 hours instead of dropping it.
    """
    start, end = window(week_end)
    analysed = df[df["flag"] != "unreliable meter"]
    span = analysed.groupby("building")["hour"].agg(["min", "max"])
    return sorted(span[(span["min"] < end) & (span["max"] >= start)].index)
GAP_SHARE = 0.3      # a building missing this share of the week's hours is a meter item


def daily_trend(df, week_end, days=TREND_DAYS, min_share=0.9):
    """Campus kWh per day for the 30 days to the chosen date, with each day's flagged hours.

    A day counts only if at least 90% of its building-hours were recorded, so a meter gap
    never looks like a drop in use. `high_hours` is how many hours were flagged higher
    than usual that day (see resource.py).
    """
    end = window(week_end)[1]
    analysed = df[df["flag"] != "unreliable meter"]
    buildings = analysed["building"].nunique()
    d = analysed[(analysed["hour"] >= end - pd.Timedelta(days=days)) & (analysed["hour"] < end)]
    g = d.groupby(d["hour"].dt.normalize()).agg(
        kwh=("kwh", "sum"), hours=("kwh", "count"),
        high_hours=("flag", lambda f: int((f == "high").sum())))
    g = g[g["hours"] >= min_share * 24 * buildings]
    return g.reset_index(names="date")


def campus_forecast(daily, types, evaluation, week_end):
    """The 14 days after the chosen week: each building's chosen method, summed.

    Uses only days before the forecast date. Buildings without a usable method, or
    with a day it cannot forecast, are left out of the sum and listed.
    """
    origin = pd.Timestamp(week_end).normalize() + pd.Timedelta(days=1)
    parts, skipped = [], []
    for r in evaluation[evaluation["note"] == ""].itertuples():
        s = daily[daily["building"] == r.building].set_index("date")["kwh"].sort_index()
        if s.empty or s.index.min() >= origin:
            skipped.append(r.building)
            continue
        f = forecast(s, types, origin)
        f["forecast"] = f[r.method]
        if f["forecast"].isna().any():
            skipped.append(r.building)
            continue
        parts.append(f.assign(building=r.building)[["date", "building", "forecast", "actual"]])
    if not parts:
        return pd.DataFrame(columns=["date", "forecast", "actual"]), skipped, None
    allf = pd.concat(parts)
    total = allf.groupby("date").agg(forecast=("forecast", "sum"),
                                     actual=("actual", lambda a: a.sum() if a.notna().all() else float("nan")))
    total = total.reset_index()
    used = sorted(allf["building"].unique())
    before = daily[daily["building"].isin(used) & (daily["date"] < origin)
                   & (daily["date"] >= origin - pd.Timedelta(days=HORIZON))]
    full_days = before.groupby("date")["building"].nunique() == len(used)
    recent = before[before["date"].isin(full_days[full_days].index)].groupby("date")["kwh"].sum()
    change = (total["forecast"].mean() / recent.mean() - 1) if len(recent) >= HORIZON // 2 else None
    return total, skipped, change


def building_hours(occ, week_end):
    """How the week's building-hours split by Wi-Fi activity, relative to each building's peak."""
    if occ is None or occ.empty:
        return None
    start, end = window(week_end)
    occ = occ.dropna(subset=["occ_mean"])
    level = occ.groupby("building")["occ_mean"].quantile(BUSY_LEVEL)
    w = occ[(occ["hour"] >= start) & (occ["hour"] < end)]
    buildings = occ["building"].nunique()
    share = w["occ_mean"] / w["building"].map(level)
    counts = {
        "Busy": int((share >= BUSY).sum()),
        "In use": int(((share >= QUIET) & (share < BUSY)).sum()),
        "Near-empty": int((share < QUIET).sum()),
    }
    counts["No data"] = max(buildings * HOURS_PER_WEEK - sum(counts.values()), 0)
    return pd.DataFrame({"state": list(counts), "hours": list(counts.values())})


def energy_hours(df, week_end):
    """How the week's building-hours split by energy flag (for colleges without Wi-Fi data)."""
    start, end = window(week_end)
    analysed = df[df["flag"] != "unreliable meter"]
    w = analysed[(analysed["hour"] >= start) & (analysed["hour"] < end)]
    counts = {"Normal": int((w["flag"] == "normal").sum()),
              "Higher than usual": int((w["flag"] == "high").sum()),
              "Lower than usual": int((w["flag"] == "low").sum())}
    counts["No data"] = max(analysed["building"].nunique() * HOURS_PER_WEEK - sum(counts.values()), 0)
    return pd.DataFrame({"state": list(counts), "hours": list(counts.values())})


def feed(events, df, recs, week_end, forecast_change=None, limit=6):
    """Key insights for the week, most specific first. Each: kind, title, text, when."""
    start, end = window(week_end)
    items = []
    week = events[(events["start"] >= start) & (events["start"] < end)]
    for e in week[week["direction"] == "high"].head(3).itertuples():
        items.append({"kind": "high", "title": e.building,
                      "text": f"{e.extra_pct:+.0%} above expected: {e.actual_kwh:,.0f} kWh vs "
                              f"{e.expected_kwh:,.0f} over {e.hours} hour{'s' if e.hours != 1 else ''}.",
                      "when": f"{e.start:%a %-d %b, %H:%M}"})
    analysed = df[df["flag"] != "unreliable meter"]
    w = analysed[(analysed["hour"] >= start) & (analysed["hour"] < end)]
    recorded = w.groupby("building")["kwh"].count().reindex(in_service(df, week_end), fill_value=0)
    for b, n in recorded[recorded < (1 - GAP_SHARE) * HOURS_PER_WEEK].items():
        items.append({"kind": "data", "title": b,
                      "text": f"Meter recorded only {n} of {HOURS_PER_WEEK} hours this week; "
                              "check the meter and data feed.",
                      "when": "This week"})
    if forecast_change is not None and abs(forecast_change) >= 0.05:
        items.append({"kind": "plan", "title": "Next 2 weeks",
                      "text": f"Forecast {forecast_change:+.0%} vs the last 14 days, campus total.",
                      "when": f"From {end:%a %-d %b}"})
    for r in recs[recs["rule"].isin(["R3", "R5"])].head(limit).itertuples():
        items.append({"kind": "pattern" if r.rule == "R3" else "caution", "title": r.building,
                      "text": r.finding, "when": "Across the data"})
    return items[:limit]


def building_week(df, week_end):
    """One row per building for the chosen week: kWh, change, flagged and missing hours."""
    start, end = window(week_end)
    analysed = df[df["flag"] != "unreliable meter"]
    w = analysed[(analysed["hour"] >= start) & (analysed["hour"] < end)]
    change = compare(analysed[["hour", "building", "kwh"]], "kwh", week_end)["per_building"]
    t = w.groupby("building").agg(kwh=("kwh", "sum"), recorded=("kwh", "count"),
                                  high=("flag", lambda f: int((f == "high").sum())),
                                  low=("flag", lambda f: int((f == "low").sum())))
    t = t.reindex(in_service(df, week_end)).fillna({"kwh": 0, "recorded": 0, "high": 0, "low": 0})
    t[["recorded", "high", "low"]] = t[["recorded", "high", "low"]].astype(int)
    t["kwh"] = t["kwh"].where(t["recorded"] > 0)
    t = t.join(change.set_index("building")[["change"]])
    return pd.DataFrame({
        "Building": t.index, "kWh this week": t["kwh"].round().to_numpy(),
        "vs week before %": (t["change"] * 100).round(1).to_numpy(),
        "Hours higher than usual": t["high"].to_numpy(), "Hours lower than usual": t["low"].to_numpy(),
        "Hours without data": (HOURS_PER_WEEK - t["recorded"]).to_numpy()})
