"""NEXUS recommendations: explicit rules that turn findings into solutions.

Each recommendation has
  - a finding, with the numbers behind it (from the data)
  - what is at stake: the energy the fix would act on, per year where possible (from the data)
  - common causes to rule out, a staged action plan with owners, and how to check it worked
    (from nexus/playbook.py: general practice, never a diagnosis)

Savings are never claimed: the app multiplies "what is at stake" by a reduction the person sets.

Print the recommendations:   python -m nexus.recommend
"""
import pandas as pd

from nexus import playbook as pb
from nexus.data import OUT

# Rule thresholds. Change them here; the app shows them next to each rule.
EVENT_MIN_HOURS = 3        # R1: unusual high use lasting at least 3 hours...
EVENT_MIN_EXTRA = 0.50     # ...and at least 50% above expected
EVENT_TOP = 5              # R1: list the 5 largest by extra kWh
OUT_OF_HOURS = (8, 20)     # R1/R7: hours outside 08:00-20:00, or non-working days
EXTREME = 3.0              # R1: 300% or more above expected -> also suspect the meter
REPEAT_MIN = 3             # R1: mention the building's pattern when it has 3+ such events
REPEAT_SAME_DAY = 0.40     # ...and point at weekly schedules when 40%+ started on the same weekday
LOW_MIN_HOURS = 24         # R2: lower-than-usual readings for at least 24 hours...
LOW_MIN_DROP = 0.50        # ...and at least 50% below expected
LOW_TOP = 3
QUIET_RATIO = 0.60         # R3: near-empty hours use at least 60% of busy-hour energy
PLAN_CHANGE = 0.15         # R4: forecast at least 15% above/below the same weeks last year
PLAN_MIN_DAYS = 10         # R4: need 10 complete days in last year's matching weeks
FORECAST_MAX_ERROR = 0.15  # R5: forecasts that miss by more than 15% of a day
YEAR_DAYS = 365            # R6-R9 use the last 365 days of data
MIN_DAYS = 60              # R6-R8 need at least 60 days of readings in that window
BASE_QUANTILE = 0.10       # R6: the always-on level = the 10th percentile of hourly kWh
BASE_SHARE = 0.50          # R6: always-on energy is at least 50% of the building's total
OFF_RATIO = 0.60           # R7: a day off uses at least 60% of a working day's energy
OFF_MIN_DAYS = 20          # R7: needs 20 days off in the window
PEAK_OVER = 0.15           # R8: campus peak hour at least 15% above its 95th-percentile hour
PEAK_TOP = 0.01            # R8: the top 1% of hours describe when peaks happen
SEASON_SHARE = 0.15        # R9: the 3 highest months add at least 15% to the year's energy
SEASON_MIN_MONTHS = 9      # R9: needs 9 different months

RULES = [
    ("R1", "Investigate", "Unusual high use",
     f"An event at least {EVENT_MIN_EXTRA:.0%} above expected for at least {EVENT_MIN_HOURS} "
     f"hours; the {EVENT_TOP} largest by extra kWh."),
    ("R2", "Fix data", "Long low reading",
     f"At least {LOW_MIN_HOURS} hours at least {LOW_MIN_DROP:.0%} below expected."),
    ("R3", "Save energy", "High use when near-empty",
     f"Near-empty hours use at least {QUIET_RATIO:.0%} of the energy of busy hours."),
    ("R4", "Plan", "Forecast differs from last year",
     f"The forecast for the 14 days after the selected week is at least {PLAN_CHANGE:.0%} above "
     "or below the same 14 days a year earlier."),
    ("R5", "Plan", "Less reliable forecast",
     f"In the test year the forecast missed by more than {FORECAST_MAX_ERROR:.0%} of a typical "
     "day, or did worse than the simple rule (about the method, so the same for every date)."),
    ("R6", "Save energy", "Large always-on load",
     f"In the 12 months to the selected week, the building's overnight minimum (its {BASE_QUANTILE:.0%} lowest "
     f"hours) running all day adds up to at least {BASE_SHARE:.0%} of its energy."),
    ("R7", "Save energy", "Running on days off",
     f"A non-working day uses at least {OFF_RATIO:.0%} of a working day's energy (12 months to the selected week; "
     "not applied to residences or dining halls, which are meant to run every day)."),
    ("R8", "Cut peak", "Campus peak demand",
     f"The campus's highest hour is at least {PEAK_OVER:.0%} above its 95th-percentile hour "
     f"(12 months to the selected week, buildings with reliable meters)."),
    ("R9", "Save energy", "Big seasonal swing",
     f"The 3 highest months add at least {SEASON_SHARE:.0%} to the year's energy compared with "
     "running all year at the 3 lowest months' level."),
]
KINDS = ["Save energy", "Cut peak", "Investigate", "Fix data", "Plan"]
CAMPUS = "Whole campus"
COLUMNS = ["rule", "kind", "title", "building", "btype", "finding", "next_step", "evidence", "size",
           "at_stake_kwh", "at_stake_what", "worth_kind", "causes", "actions", "verify"]


def _rec(rule, building, finding, evidence, size, playbook, at_stake=None, what="", worth="save"):
    causes, actions, verify = playbook
    btype = "campus" if building == CAMPUS else pb.building_type(building)
    return {"rule": rule, "building": building, "btype": btype, "finding": finding,
            "next_step": actions[0][1], "evidence": evidence, "size": size,
            "at_stake_kwh": float("nan") if at_stake is None else float(at_stake),
            "at_stake_what": what, "worth_kind": worth if at_stake is not None else "",
            "causes": causes, "actions": actions, "verify": verify}


def _out_of_hours_share(start, end, working):
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    workday = [bool(working.get(d, False)) for d in hours.normalize()]
    off = ((hours.hour < OUT_OF_HOURS[0]) | (hours.hour >= OUT_OF_HOURS[1])
           | ~pd.Index(workday, dtype=bool))
    return float(off.to_numpy().mean())


def from_events(events, calendar=None, as_of=None):
    """R1 and R2, from Resource Intelligence events (only those starting in the window when `as_of` is set)."""
    cal = pd.read_parquet(OUT / "calendar.parquet") if calendar is None else calendar
    working = dict(zip(cal["date"], cal["working_day"]))
    recs = []
    if as_of is not None and len(events):
        start, end = window(as_of)
        events = events[(events["start"] >= start) & (events["start"] < end)]

    high = events[(events["direction"] == "high") & (events["hours"] >= EVENT_MIN_HOURS)
                  & (events["extra_pct"] >= EVENT_MIN_EXTRA)]
    for e in high.nlargest(EVENT_TOP, "extra_kwh").itertuples():
        when = f"{e.start:%a %d %b %Y, %H:%M} to {e.end:%a %H:%M}"
        out_of_hours = _out_of_hours_share(e.start, e.end, working) >= 0.5
        extreme = e.extra_pct >= EXTREME
        same = high[high["building"] == e.building]
        repeat = ""
        if len(same) >= REPEAT_MIN:
            day = same["start"].dt.day_name().mode().iloc[0]
            n_day = int((same["start"].dt.day_name() == day).sum())
            repeat = f" It is one of {len(same)} such events in {e.building} in these 12 months"
            repeat += (f"; {n_day} of them started on a {day}, so check weekly schedules first."
                       if n_day / len(same) >= REPEAT_SAME_DAY else ".")
        recs.append(_rec(
            "R1", e.building,
            f"{e.actual_kwh:,.0f} kWh measured vs {e.expected_kwh:,.0f} expected (+{e.extra_pct:.0%}, "
            f"{e.hours} hours, {when}{', mostly out of hours' if out_of_hours else ''}).{repeat}",
            f"Baseline: median of at least {e.samples:.0f} comparable hours. See Resource Intelligence.",
            e.extra_kwh,
            pb.unusual_high(e.building, when, f"{e.start:%A}", out_of_hours, extreme,
                            e.expected_kwh / e.hours),
            e.extra_kwh, "extra in this one event", "once"))

    low = events[(events["direction"] == "low") & (events["hours"] >= LOW_MIN_HOURS)
                 & (events["extra_pct"] <= -LOW_MIN_DROP)]
    for e in low.nlargest(LOW_TOP, "hours").itertuples():
        recs.append(_rec(
            "R2", e.building,
            f"{e.hours} hours from {e.start:%d %b %Y} at {e.extra_pct:.0%} vs expected. Until this is "
            "explained, NEXUS's numbers for that period can't be trusted.",
            "See Resource Intelligence, lower-than-usual events.", -e.extra_kwh, pb.long_low(e.building)))
    return recs


def from_occupancy(summary, years=None):
    """R3, from Institutional Intelligence. `years` = how many years the occupancy data covers."""
    recs = []
    if summary is None or summary.empty:
        return recs
    ok = summary[(summary["energy_note"] == "") & (summary["quiet_vs_busy"] >= QUIET_RATIO)]
    for r in ok.sort_values("quiet_vs_busy", ascending=False).itertuples():
        total = r.quiet_kwh * r.quiet_energy_hours
        per_year = total / years if years and years >= 0.5 else total
        what = ("a year used while near-empty (semester weeks)" if years and years >= 0.5
                else "used while near-empty, across the semester weeks in these 12 months")
        recs.append(_rec(
            "R3", r.building,
            f"Near-empty hours use {r.quiet_kwh:.1f} kWh/h, {r.quiet_vs_busy:.0%} of the {r.busy_kwh:.1f} "
            "kWh/h used when busy: the building costs almost as much to run empty as full.",
            f"{r.quiet_energy_hours:,} near-empty and {r.busy_energy_hours:,} busy semester hours compared. "
            "See Institutional Intelligence.",
            total, pb.near_empty(r.building, pb.building_type(r.building), r.quiet_vs_busy, QUIET_RATIO),
            per_year, what))
    return recs


def from_forecasts(evaluation, daily, types, forecast, as_of=None):
    """R4 and R5, from Predictive Intelligence. R4 forecasts the 14 days after `as_of` (default: the
    latest 14 days with data); R5 is about the forecasting method, so it is the same for every date."""
    recs = []
    for r in evaluation[evaluation["note"] == ""].itertuples():
        if r.error_pct > FORECAST_MAX_ERROR or r.skill < 0:
            why = (f"misses by {r.error_pct:.1%} of a typical day" if r.error_pct > FORECAST_MAX_ERROR
                   else f"was {abs(r.skill):.0%} less accurate than the simple rule on "
                        f"{r.test_period}")
            recs.append(_rec("R5", r.building, f"The forecast {why}.",
                             "See Predictive Intelligence, How accurate is this?", r.error_pct,
                             pb.unreliable_forecast(r.building)))

        s = daily[daily["building"] == r.building].set_index("date")["kwh"].sort_index()
        origin = (s.index.max() - pd.Timedelta(days=13) if as_of is None
                  else pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1))
        if len(s[s.index < origin]) < 28:
            continue
        f = forecast(s, types, origin)
        f["forecast"] = f[r.method]
        year_ago = s.reindex(f["date"] - pd.Timedelta(days=364)).dropna()  # same weekdays
        if len(year_ago) < PLAN_MIN_DAYS or f["forecast"].isna().any():
            continue
        change = f["forecast"].mean() / year_ago.mean() - 1
        if abs(change) < PLAN_CHANGE:
            continue
        span = f"{f['date'].min():%d %b} to {f['date'].max():%d %b %Y}"
        actual = f["actual"].dropna()
        outcome = (f" What actually happened: {actual.mean() / year_ago.mean() - 1:+.0%}."
                   if len(actual) >= PLAN_MIN_DAYS else "")
        diff = (f["forecast"].mean() - year_ago.mean()) * len(f)
        recs.append(_rec(
            "R4", r.building,
            f"Forecast for {span}: {change:+.0%} vs the same weeks a year earlier "
            f"({f['forecast'].mean():,.0f} vs {year_ago.mean():,.0f} kWh/day, {diff:+,.0f} kWh over the 14 days).",
            (f"Forecast made on {origin:%d %b %Y}, the latest date with 14 days of data after it."
             if as_of is None else
             f"Forecast for the 14 days after the selected week, from data up to {origin - pd.Timedelta(days=1):%d %b %Y}.")
            + f"{outcome} See Predictive Intelligence.",
            abs(change), pb.plan_ahead(r.building, span, change > 0)))
    return recs


# ------------------------------------------------------------ R6-R9: whole-year patterns

def window(as_of):
    """The 365 days ending with the day `as_of` (the selected week's last day): [start, end)."""
    end = pd.Timestamp(as_of).normalize() + pd.Timedelta(days=1)
    return end - pd.Timedelta(days=YEAR_DAYS), end


def last_year(energy, warnings=None, as_of=None):
    """Hourly readings in the 365 days ending at `as_of` (default: the end of the data), without
    buildings whose meter is flagged unreliable."""
    if energy is None or energy.empty:
        return pd.DataFrame()
    e = energy[~energy["building"].isin(list(warnings or {}))].dropna(subset=["kwh"])
    if e.empty:
        return e
    start, end = window(e["hour"].max() if as_of is None else as_of)
    return e[(e["hour"] >= start) & (e["hour"] < end)].copy()


def campus_year_kwh(energy, warnings=None, as_of=None):
    """Energy of all reliable buildings over the 365 days ending at `as_of`, each scaled to a full year."""
    e = last_year(energy, warnings, as_of)
    if e.empty:
        return None
    total = 0.0
    for _, g in e.groupby("building"):
        days = g["hour"].dt.normalize().nunique()
        if days >= MIN_DAYS:
            total += g["kwh"].sum() * YEAR_DAYS / days
    return total or None


def _hours_label(hours):
    top = pd.Series(hours).value_counts().head(2).index.sort_values()
    return " and ".join(f"{h:02d}:00" for h in top)


def _months_label(months):
    names = [pd.Timestamp(2000, m, 1).strftime("%B") for m in months]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def from_energy(energy, warnings=None, as_of=None):
    """R6 always-on, R7 days off, R9 seasonal swing (per building) and R8 campus peak."""
    e = last_year(energy, warnings, as_of)
    recs = []
    if e.empty:
        return recs
    span = f"{e['hour'].min():%d %b %Y} to {e['hour'].max():%d %b %Y}"
    for b, g in e.groupby("building"):
        days = g["hour"].dt.normalize().nunique()
        if days < MIN_DAYS:
            continue
        btype = pb.building_type(b)
        k = g["kwh"]
        per_year = YEAR_DAYS / days
        total = k.sum() * per_year
        scaled = "" if days >= YEAR_DAYS - 1 else f" Readings on {days} of {YEAR_DAYS} days; yearly totals are scaled up to a full year."
        base = k.quantile(BASE_QUANTILE)

        # R6 always-on
        base_year = base * 24 * YEAR_DAYS
        if total > 0 and base > 0 and base_year / total >= BASE_SHARE:
            recs.append(_rec(
                "R6", b,
                f"Even at its quietest, {b} draws {base:,.1f} kWh every hour. Running all day, all year, "
                f"that minimum is {base_year / total:.0%} of the building's energy ({base_year:,.0f} of "
                f"{total:,.0f} kWh a year).",
                f"Minimum = the {BASE_QUANTILE:.0%} lowest hourly readings, {span}.{scaled}",
                base_year, pb.always_on(b, btype, base),
                base_year, "a year of always-on energy"))

        # R7 days off (not residences or dining halls)
        if btype not in ("residence", "dining") and g["working_day"].notna().any():
            wd = g["working_day"].astype("boolean").fillna(False)
            daily = g.assign(wd=wd).groupby([g["hour"].dt.normalize(), "wd"])["kwh"].sum().reset_index()
            on, off = daily[daily["wd"]]["kwh"], daily[~daily["wd"]]["kwh"]
            if len(off) >= OFF_MIN_DAYS and len(on) >= OFF_MIN_DAYS and on.mean() > 0:
                ratio = off.mean() / on.mean()
                if ratio >= OFF_RATIO:
                    off_hours = g[~wd.to_numpy()]
                    above = (off_hours["kwh"] - base).clip(lower=0)
                    busy = off_hours.loc[above.nlargest(max(1, len(above) // 10)).index, "hour"].dt.hour
                    stake = above.sum() * per_year
                    recs.append(_rec(
                        "R7", b,
                        f"On a day off {b} uses {off.mean():,.0f} kWh, {ratio:.0%} of a working day's "
                        f"{on.mean():,.0f} kWh. Above its always-on minimum, days off add {stake:,.0f} kWh a year.",
                        f"{len(off)} non-working and {len(on)} working days, {span}; days off as marked in "
                        "the college calendar." + scaled,
                        stake, pb.days_off(b, ratio, _hours_label(busy)),
                        stake, "a year used on days off, above the always-on minimum"))

        # R9 seasonal swing
        month = g.groupby(g["hour"].dt.month)
        if month.ngroups >= SEASON_MIN_MONTHS:
            per_day = month.apply(lambda x: x["kwh"].sum() / x["hour"].dt.normalize().nunique())
            hot, cool = per_day.nlargest(3), per_day.nsmallest(3)
            extra = (hot - cool.mean()).sum() * 30.4
            if total > 0 and extra / total >= SEASON_SHARE:
                hot_l, cool_l = _months_label(sorted(hot.index)), _months_label(sorted(cool.index))
                recs.append(_rec(
                    "R9", b,
                    f"In {hot_l} {b} uses {hot.mean():,.0f} kWh a day, against {cool.mean():,.0f} in {cool_l}. "
                    f"Those three months add about {extra:,.0f} kWh, {extra / total:.0%} of its year.",
                    f"Average day per calendar month, {span}. No weather data: cooling and term-time "
                    "activity both show up here." + scaled,
                    extra, pb.seasonal(b, btype, hot_l, cool_l), extra, "a year of extra energy in the peak months"))

    # R8 campus peak: hours where every included building has a reading
    n = e["building"].nunique()
    wide = e.pivot_table(index="hour", columns="building", values="kwh", aggfunc="sum")
    wide = wide[wide.notna().sum(axis=1) == n]
    if len(wide) >= MIN_DAYS * 24 and n >= 2:
        campus = wide.sum(axis=1)
        peak, p95 = campus.max(), campus.quantile(0.95)
        if p95 > 0 and peak / p95 - 1 >= PEAK_OVER:
            top = campus.nlargest(max(1, int(len(campus) * PEAK_TOP)))
            shift = (campus - p95).clip(lower=0).sum() * YEAR_DAYS * 24 / len(campus)
            share_peak = wide.loc[top.index].sum() / top.sum()
            share_all = wide.sum() / campus.sum()
            rise = (share_peak - share_all).sort_values(ascending=False)
            b_up = rise.index[0]
            riser = (f"{b_up} makes up {share_peak[b_up]:.0%} of campus use in peak hours against "
                     f"{share_all[b_up]:.0%} on average, so start there.")
            months = top.index.month.value_counts().head(2).index
            recs.append(_rec(
                "R8", CAMPUS,
                f"The campus's highest hour used {peak:,.0f} kWh ({campus.idxmax():%a %d %b %Y, %H:%M}), "
                f"{peak / p95 - 1:.0%} above the level it stays under 95% of the time ({p95:,.0f} kWh). "
                f"Capping peaks at that level means moving about {shift:,.0f} kWh a year to other hours, "
                f"and the peak falls by about {peak - p95:,.0f} kW. Peaks cluster around "
                f"{_hours_label(top.index.hour)} in {_months_label(sorted(months))}.",
                f"Hourly totals of {n} buildings with reliable meters, {span}. kWh in an hour = average kW "
                "over that hour; the instant peak on the bill can be higher.",
                peak - p95, pb.campus_peak(_hours_label(top.index.hour), _months_label(sorted(months)), riser, p95),
                shift, "a year to move out of peak hours (shifted, not saved)", "shift"))
    return recs


def build(events, summary, evaluation, daily, types, forecast, calendar=None, energy=None,
          warnings=None, occ_years=None, as_of=None):
    """All recommendations for the 12 months ending at `as_of` (default: the end of the data),
    grouped by rule and largest first within each rule. `summary` should cover the same window."""
    recs = (from_events(events, calendar, as_of) + from_occupancy(summary, occ_years)
            + from_forecasts(evaluation, daily, types, forecast, as_of) + from_energy(energy, warnings, as_of))
    if not recs:
        return pd.DataFrame(columns=COLUMNS)
    out = pd.DataFrame(recs)
    rules = pd.DataFrame(RULES, columns=["rule", "kind", "title", "condition"])
    out = out.merge(rules[["rule", "kind", "title"]], on="rule")
    out = out.sort_values(["rule", "size"], ascending=[True, False], ignore_index=True)
    return out[COLUMNS]


def as_text(r):
    """One recommendation as plain text (for downloads and the chatbot)."""
    lines = [f"{r['title']} - {r['building']}", f"Finding: {r['finding']}", "Causes to rule out: "
             + "; ".join(r["causes"])]
    lines += [f"{stage}: {what} ({who})" for stage, what, who in r["actions"]]
    lines.append(f"How to know it worked: {r['verify']}")
    return "\n".join(lines)


def main():
    from nexus.data import ENERGY_WARNINGS
    from nexus.institutional import building_summary, load_occupancy
    from nexus.predictive import backtest, daily_energy, day_types, evaluate, forecast
    from nexus.resource import add_baseline, find_events, load_energy

    energy = add_baseline(load_energy())
    events = find_events(energy)
    occ = load_occupancy()
    years = (occ["hour"].max() - occ["hour"].min()).days / 365.25
    summary = building_summary(occ)
    daily, types = daily_energy(), day_types()
    recs = build(events, summary, evaluate(backtest(daily, types)), daily, types, forecast,
                 energy=energy, warnings=ENERGY_WARNINGS, occ_years=years)
    print(f"RECOMMENDATIONS  {len(recs)} from {recs['rule'].nunique() if len(recs) else 0} rules\n")
    for r in recs.to_dict("records"):
        stake = (f"   at stake:  {r['at_stake_kwh']:,.0f} kWh ({r['at_stake_what']})\n"
                 if r["worth_kind"] else "")
        print(f"[{r['rule']} {r['kind']}] {as_text(r)}\n{stake}")


if __name__ == "__main__":
    main()
