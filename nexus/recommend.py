"""NEXUS recommendations: explicit rules that turn findings into next steps.

Every recommendation is an investigation or a check, never a diagnosed cause.
Each one carries the rule that produced it and the numbers behind it.

Print the recommendations:   python -m nexus.recommend
"""
import pandas as pd

from nexus.data import OUT

# Rule thresholds. Change them here; the app shows them next to each rule.
EVENT_MIN_HOURS = 3        # R1: unusual high use lasting at least 3 hours...
EVENT_MIN_EXTRA = 0.50     # ...and at least 50% above expected
EVENT_TOP = 5              # R1: list the 5 largest by extra kWh
OUT_OF_HOURS = (8, 20)     # R1: hours outside 08:00-20:00, or non-working days
EXTREME = 3.0              # R1: 300% or more above expected -> also suspect the meter
LOW_MIN_HOURS = 24         # R2: lower-than-usual readings for at least 24 hours...
LOW_MIN_DROP = 0.50        # ...and at least 50% below expected
LOW_TOP = 3
QUIET_RATIO = 0.60         # R3: near-empty hours use at least 60% of busy-hour energy
PLAN_CHANGE = 0.15         # R4: forecast at least 15% above/below the same weeks last year
PLAN_MIN_DAYS = 10         # R4: need 10 complete days in last year's matching weeks
FORECAST_MAX_ERROR = 0.15  # R5: forecasts that miss by more than 15% of a day

RULES = [
    ("R1", "Investigate", "Unusual high use",
     f"An event at least {EVENT_MIN_EXTRA:.0%} above expected for at least {EVENT_MIN_HOURS} "
     f"hours; the {EVENT_TOP} largest by extra kWh."),
    ("R2", "Check data", "Long low reading",
     f"At least {LOW_MIN_HOURS} hours at least {LOW_MIN_DROP:.0%} below expected."),
    ("R3", "Investigate", "High use when near-empty",
     f"Near-empty hours use at least {QUIET_RATIO:.0%} of the energy of busy hours."),
    ("R4", "Plan", "Forecast differs from last year",
     f"The next 14 days are forecast at least {PLAN_CHANGE:.0%} above or below the same "
     "14 days a year earlier."),
    ("R5", "Caution", "Less reliable forecast",
     f"On 2017 the forecast missed by more than {FORECAST_MAX_ERROR:.0%} of a typical day, "
     "or did worse than the simple rule."),
]


def _out_of_hours_share(start, end, working):
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    workday = [bool(working.get(d, False)) for d in hours.normalize()]
    off = ((hours.hour < OUT_OF_HOURS[0]) | (hours.hour >= OUT_OF_HOURS[1])
           | ~pd.Index(workday, dtype=bool))
    return float(off.to_numpy().mean())


def from_events(events):
    """R1 and R2, from Resource Intelligence events."""
    cal = pd.read_parquet(OUT / "calendar.parquet")
    working = dict(zip(cal["date"], cal["working_day"]))
    recs = []

    high = events[(events["direction"] == "high") & (events["hours"] >= EVENT_MIN_HOURS)
                  & (events["extra_pct"] >= EVENT_MIN_EXTRA)]
    for e in high.nlargest(EVENT_TOP, "extra_kwh").itertuples():
        when = f"{e.start:%a %d %b %Y, %H:%M} to {e.end:%a %H:%M}"
        if _out_of_hours_share(e.start, e.end, working) >= 0.5:
            todo = (f"Check what was running in {e.building} out of hours ({when}): "
                    "HVAC and lighting schedules, and equipment left on.")
        else:
            todo = (f"Ask facilities whether an event, extra equipment or a meter fault "
                    f"explains {e.building} on {when}.")
        if e.extra_pct >= EXTREME:
            todo += (f" At +{e.extra_pct:.0%} this is far outside normal, so a meter or data "
                     "fault is as plausible as real use: check the meter too.")
        recs.append({
            "rule": "R1", "building": e.building, "size": e.extra_kwh,
            "finding": f"{e.actual_kwh:,.0f} kWh measured vs {e.expected_kwh:,.0f} expected "
                       f"(+{e.extra_pct:.0%}, {e.hours} hours).",
            "next_step": todo,
            "evidence": f"Baseline: median of at least {e.samples:.0f} comparable hours. "
                        "See Resource Intelligence.",
        })

    low = events[(events["direction"] == "low") & (events["hours"] >= LOW_MIN_HOURS)
                 & (events["extra_pct"] <= -LOW_MIN_DROP)]
    for e in low.nlargest(LOW_TOP, "hours").itertuples():
        recs.append({
            "rule": "R2", "building": e.building, "size": -e.extra_kwh,
            "finding": f"{e.hours} hours from {e.start:%d %b %Y} at {e.extra_pct:.0%} vs expected.",
            "next_step": f"Confirm whether {e.building} was closed then; if not, check the "
                         "meter and data feed before trusting readings from that period.",
            "evidence": "See Resource Intelligence, lower-than-usual events.",
        })
    return recs


def from_occupancy(summary):
    """R3, from Institutional Intelligence."""
    recs = []
    ok = summary[(summary["energy_note"] == "") & (summary["quiet_vs_busy"] >= QUIET_RATIO)]
    for r in ok.sort_values("quiet_vs_busy", ascending=False).itertuples():
        recs.append({
            "rule": "R3", "building": r.building, "size": r.quiet_kwh * r.quiet_energy_hours,
            "finding": f"Near-empty hours use {r.quiet_kwh:.1f} kWh/h, {r.quiet_vs_busy:.0%} of "
                       f"the {r.busy_kwh:.1f} kWh/h used when busy.",
            "next_step": f"Review what keeps running in {r.building} when it is near-empty: "
                         "HVAC and lighting schedules, and always-on equipment.",
            "evidence": f"{r.quiet_energy_hours:,} near-empty and {r.busy_energy_hours:,} busy "
                        "semester hours compared. See Institutional Intelligence.",
        })
    return recs


def from_forecasts(evaluation, daily, types, forecast):
    """R4 and R5, from Predictive Intelligence (latest forecast date per building)."""
    recs = []
    for r in evaluation[evaluation["note"] == ""].itertuples():
        if r.error_pct > FORECAST_MAX_ERROR or r.skill < 0:
            why = (f"misses by {r.error_pct:.1%} of a typical day" if r.error_pct > FORECAST_MAX_ERROR
                   else f"was {abs(r.skill):.0%} less accurate than the simple rule on 2017")
            recs.append({
                "rule": "R5", "building": r.building, "size": r.error_pct,
                "finding": f"The forecast {why}.",
                "next_step": f"Treat {r.building}'s forecast as a rough guide. Adding weather "
                             "data is the likely next improvement.",
                "evidence": "See Predictive Intelligence, How accurate is this?",
            })

        s = daily[daily["building"] == r.building].set_index("date")["kwh"].sort_index()
        origin = s.index.max() - pd.Timedelta(days=13)
        f = forecast(s, types, origin)
        f["forecast"] = f[r.method]
        year_ago = s.reindex(f["date"] - pd.Timedelta(days=364)).dropna()  # same weekdays
        if len(year_ago) < PLAN_MIN_DAYS or f["forecast"].isna().any():
            continue
        change = f["forecast"].mean() / year_ago.mean() - 1
        if abs(change) < PLAN_CHANGE:
            continue
        span = f"{f['date'].min():%d %b} to {f['date'].max():%d %b %Y}"
        todo = (f"Check planned events and HVAC schedules for {span}."
                if change > 0 else
                f"If parts of {r.building} will be closed during {span}, confirm "
                "non-essential loads are switched off.")
        actual = f["actual"].dropna()
        outcome = (f" What actually happened: {actual.mean() / year_ago.mean() - 1:+.0%}."
                   if len(actual) >= PLAN_MIN_DAYS else "")
        recs.append({
            "rule": "R4", "building": r.building, "size": abs(change),
            "finding": f"Forecast for {span}: {change:+.0%} vs the same weeks a year earlier "
                       f"({f['forecast'].mean():,.0f} vs {year_ago.mean():,.0f} kWh/day).",
            "next_step": todo,
            "evidence": f"Forecast made on {origin:%d %b %Y}, the latest date with 14 days of "
                        f"data after it.{outcome} See Predictive Intelligence.",
        })
    return recs


def build(events, summary, evaluation, daily, types, forecast):
    """All recommendations, grouped by rule and largest first within each rule."""
    recs = from_events(events) + from_occupancy(summary) + \
        from_forecasts(evaluation, daily, types, forecast)
    if not recs:
        return pd.DataFrame(columns=["rule", "kind", "title", "building", "finding",
                                     "next_step", "evidence"])
    out = pd.DataFrame(recs)
    rules = pd.DataFrame(RULES, columns=["rule", "kind", "title", "condition"])
    out = out.merge(rules[["rule", "kind", "title"]], on="rule")
    return out.sort_values(["rule", "size"], ascending=[True, False], ignore_index=True)


def main():
    from nexus.institutional import building_summary, load_occupancy
    from nexus.predictive import backtest, daily_energy, day_types, evaluate, forecast
    from nexus.resource import add_baseline, find_events, load_energy

    events = find_events(add_baseline(load_energy()))
    summary = building_summary(load_occupancy())
    daily, types = daily_energy(), day_types()
    recs = build(events, summary, evaluate(backtest(daily, types)), daily, types, forecast)
    print(f"RECOMMENDATIONS  {len(recs)} from {recs['rule'].nunique() if len(recs) else 0} rules\n")
    for r in recs.itertuples():
        print(f"[{r.rule} {r.kind}] {r.building}: {r.title}")
        print(f"   finding:   {r.finding}")
        print(f"   next step: {r.next_step}")
        print(f"   evidence:  {r.evidence}\n")


if __name__ == "__main__":
    main()
