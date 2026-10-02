"""Ask NEXUS: plain-language answers built only from NEXUS's own tables, with fixed rules.

There is no language model here. Each question maps to one function; each answer says
how it was worked out. Questions NEXUS cannot answer get a list of the ones it can.
"""
import re
from dataclasses import dataclass, field

import pandas as pd

from nexus.kpis import HOURS_PER_WEEK, compare, window
from nexus.recommend import OUT_OF_HOURS

YEAR = pd.Timedelta(days=364)       # 52 weeks: same weekdays a year earlier
MONTH = pd.Timedelta(days=28)


@dataclass
class Answer:
    question: str
    text: str                                   # markdown, a few sentences
    table: pd.DataFrame | None = None
    how: str = ""                               # how it was worked out
    pages: list = field(default_factory=list)   # where to look next


QUESTIONS = {
    "attention": "Which building needs attention this week?",
    "trend": "How is energy use trending?",
    "why": "Why is a building using more energy?",
    "next": "What will the next 2 weeks look like?",
    "save": "Where could we save energy?",
    "underused": "Which buildings are underused?",
}

KEYWORDS = [
    ("why", r"\bwhy\b|\bcause|\breason"),
    ("attention", r"attention|problem|issue|alert|worst|wrong|urgent|look at"),
    ("next", r"predict|forecast|next (week|2 weeks|two weeks|month)|coming|expect"),
    ("trend", r"trend|compare|last year|over time|history|pattern"),
    ("save", r"sav(e|ing)|cost|reduce|cut|money|bill|efficien|waste"),
    ("underused", r"under ?us|under ?utili[sz]|empty|unused|idle|utili[sz]"),
]


def route(text, buildings):
    """Which question a typed message is asking, and the building it names (if any)."""
    t = text.lower()
    building = next((b for b in sorted(buildings, key=len, reverse=True) if b.lower() in t), None)
    if building is None:   # also match single words such as "library" or "dorm"
        words = set(re.findall(r"[a-z]+", t))
        building = next((b for b in buildings if set(b.lower().split()) & words - {"building"}), None)
    for key, pattern in KEYWORDS:
        if re.search(pattern, t):
            return key, building
    return ("why" if building else None), building


def unknown(text):
    return Answer(text, "NEXUS answers questions from its own numbers, using fixed rules, so it "
                        "does not guess. It can answer these:\n\n"
                  + "\n".join(f"- {q}" for q in QUESTIONS.values())
                  + "\n\nName a building to ask about it, e.g. *Why is the Library using more energy?*")


# --------------------------------------------------------------- answers

def attention(df, events, recs, week_end):
    start, end = window(week_end)
    w = df[(df["hour"] >= start) & (df["hour"] < end) & (df["flag"] != "unreliable meter")]
    t = w.groupby("building").agg(
        high=("flag", lambda f: int((f == "high").sum())),
        low=("flag", lambda f: int((f == "low").sum())),
        recorded=("kwh", "count"))
    t["missing"] = HOURS_PER_WEEK - t["recorded"]
    t["checks"] = t.index.map(recs["building"].value_counts()).fillna(0).astype(int)
    t = t.sort_values(["high", "missing", "checks"], ascending=False)
    top = t.index[0]
    r = t.iloc[0]
    if r["high"] == 0 and r["missing"] < HOURS_PER_WEEK * 0.3:
        text = (f"Nothing stood out in the week ending {pd.Timestamp(week_end):%a %-d %b %Y}: no hours "
                "were higher than usual and no meter had large gaps. The standing checks are in "
                "Recommendations.")
    else:
        wk = events[(events["building"] == top) & (events["direction"] == "high")
                    & (events["start"] >= start) & (events["start"] < end)]
        detail = (f" The largest: {wk.iloc[0]['extra_pct']:+.0%} above expected on "
                  f"{wk.iloc[0]['start']:%a %-d %b, %H:%M}." if not wk.empty else "")
        text = (f"**{top}**: {r['high']} hour{'s' if r['high'] != 1 else ''} higher than usual "
                f"this week" + (f" and {r['missing']} hours with no meter data" if r["missing"] else "")
                + f".{detail} Open it in Resource Intelligence to see each hour against its baseline.")
    table = t.reset_index().rename(columns={
        "building": "Building", "high": "Hours higher than usual", "low": "Hours lower than usual",
        "missing": "Hours without data", "checks": "Standing checks"}).drop(columns="recorded")
    return Answer(QUESTIONS["attention"], text, table,
                  "Buildings ranked by hours flagged higher than usual this week, then hours "
                  "without meter data, then the number of standing checks in Recommendations. "
                  "A flag means a measured difference, not a diagnosed cause.",
                  ["Resource Intelligence", "Recommendations"])


def trend(df, week_end):
    end = window(week_end)[1]
    energy = df[df["flag"] != "unreliable meter"][["hour", "building", "kwh"]]
    rows = []
    for b, g in energy.groupby("building"):
        this = g[(g["hour"] >= end - MONTH) & (g["hour"] < end)]
        before = g[(g["hour"] >= end - MONTH - YEAR) & (g["hour"] < end - YEAR)]
        before = before.assign(hour=before["hour"] + YEAR)
        both = this.merge(before, on=["hour", "building"], suffixes=("", "_ago")).dropna()
        if len(both) >= 0.5 * len(this) and len(this):
            rows.append({"Building": b, "Last 4 weeks, kWh": round(both["kwh"].sum()),
                         "Same weeks a year earlier, kWh": round(both["kwh_ago"].sum()),
                         "Change %": round((both["kwh"].sum() / both["kwh_ago"].sum() - 1) * 100, 1),
                         "Hours compared": len(both)})
    if not rows:
        return Answer(QUESTIONS["trend"], "Insufficient data: there is no year-earlier data for "
                      "the 4 weeks to this date. Pick a later week at the top.", None,
                      "Compares the same hours a year (52 weeks) apart.", ["Resource Intelligence"])
    t = pd.DataFrame(rows).sort_values("Change %", ascending=False)
    total = t["Last 4 weeks, kWh"].sum() / t["Same weeks a year earlier, kWh"].sum() - 1
    up, down = t.iloc[0], t.iloc[-1]
    text = (f"Over the 4 weeks to {pd.Timestamp(week_end):%-d %b %Y}, campus electricity was "
            f"**{abs(total):.0%} {'higher' if total >= 0 else 'lower'}** than the same weeks a year "
            f"earlier. Biggest rise: **{up['Building']}** ({up['Change %']:+.0f}%). Biggest fall: "
            f"**{down['Building']}** ({down['Change %']:+.0f}%).")
    return Answer(QUESTIONS["trend"], text, t,
                  "Hour-for-hour comparison with the same weekdays 52 weeks earlier, counting only "
                  "hours recorded in both years. Weather and term dates differ between years; the "
                  "data has no weather.", ["Resource Intelligence", "Predictive Intelligence"])


def why(df, events, occ, recs, week_end, building):
    if building is None:
        return Answer(QUESTIONS["why"], "Which building? Name one, e.g. *Why is the Library "
                      "using more energy?*")
    q = f"Why is {building} using more energy?"
    end = window(week_end)[1]
    g = df[df["building"] == building]
    if g["flag"].eq("unreliable meter").all():
        return Answer(q, f"{building}'s energy meter is unreliable in this data, so NEXUS does not "
                         "analyse its energy.", None, "", ["Data & method"])
    c = compare(g[["hour", "building", "kwh"]], "kwh", week_end)
    month = g[(g["hour"] >= end - MONTH) & (g["hour"] < end)]
    flagged = month[month["flag"] == "high"]
    lines = [f"NEXUS cannot see causes; it can show **when** and **how much**. Here is what the "
             f"data shows for **{building}**:"]
    if c["change"] is not None:
        lines.append(f"- This week: {abs(c['change']):.0%} {'more' if c['change'] >= 0 else 'less'} "
                     "than the week before, comparing the same hours.")
    if flagged.empty:
        lines.append("- No hours higher than usual in the last 4 weeks.")
    else:
        hours = flagged["hour"].dt.hour
        off = ((hours < OUT_OF_HOURS[0]) | (hours >= OUT_OF_HOURS[1])
               | ~flagged["working_day"].astype(bool)).mean()
        extra = (flagged["kwh"] - flagged["expected"]).sum()
        lines.append(f"- Last 4 weeks: {len(flagged)} hour{'s' if len(flagged) != 1 else ''} higher "
                     f"than usual, {extra:,.0f} kWh above "
                     f"expected in total; {off:.0%} of them were out of hours (before "
                     f"{OUT_OF_HOURS[0]:02d}:00, after {OUT_OF_HOURS[1]:02d}:00 or non-working days).")
    if occ is not None and building in set(occ["building"]):
        o = compare(occ[occ["building"] == building][["hour", "building", "occ_mean"]], "occ_mean", week_end)
        if o["change"] is not None:
            lines.append(f"- Wi-Fi activity this week: {abs(o['change']):.0%} "
                         f"{'higher' if o['change'] >= 0 else 'lower'} than the week before. "
                         + ("More people may explain more use." if o["change"] > 0.05 and (c["change"] or 0) > 0
                            else "Use rose without more people: worth checking schedules and equipment."
                            if (c["change"] or 0) > 0.05 else ""))
    mine = recs[recs["building"] == building]
    if not mine.empty:
        lines.append("\n**Things to check** (from Recommendations):")
        lines += [f"- {r.next_step}" for r in mine.head(3).itertuples()]
    table = None
    if not flagged.empty:
        ev = events[(events["building"] == building) & (events["direction"] == "high")
                    & (events["start"] >= end - MONTH) & (events["start"] < end)]
        table = pd.DataFrame({"Start": ev["start"].dt.strftime("%a %d %b %H:%M"), "Hours": ev["hours"],
                              "Actual kWh": ev["actual_kwh"].round(), "Expected kWh": ev["expected_kwh"].round(),
                              "Extra %": (ev["extra_pct"] * 100).round()})
    return Answer(q, "\n".join(lines), table,
                  "Week change: same hours compared. Flagged hours: more than 3.5 times the normal "
                  "variation above the baseline and at least 10% higher. Out of hours uses the "
                  "calendar's working days.", ["Resource Intelligence", "Recommendations"])


def outlook(fc, skipped, change, week_end):
    if fc.empty:
        return Answer(QUESTIONS["next"], "Insufficient data to forecast from this date.")
    total = fc["forecast"].sum()
    known = fc.dropna(subset=["actual"])
    if len(known) == len(fc):
        check = (f" What actually happened: {known['actual'].sum():,.0f} kWh "
                 f"({known['actual'].sum() / total - 1:+.0%} vs forecast).")
    elif len(known):
        check = (f" On the {len(known)} days with complete meter data, actual use was "
                 f"{known['actual'].sum():,.0f} kWh vs {known['forecast'].sum():,.0f} forecast "
                 f"({known['actual'].sum() / known['forecast'].sum() - 1:+.0%}).")
    else:
        check = " There is no complete meter data for these days, so nothing to check it against."
    text = (f"For the 14 days from {fc['date'].min():%a %-d %b %Y}, NEXUS forecasts about "
            f"**{total:,.0f} kWh** for the campus"
            + (f", **{change:+.0%}** compared with the 14 days before." if change is not None else ".")
            + check + (f" Not included: {', '.join(skipped)}." if skipped else ""))
    table = pd.DataFrame({"Day": fc["date"].dt.strftime("%a %d %b"), "Forecast kWh": fc["forecast"].round(),
                          "Actual kWh": fc["actual"].round()})
    return Answer(QUESTIONS["next"], text, table,
                  "Each building's tested method (same weekday last week, or the median of recent "
                  "days of the same calendar day type), summed. Forecasts use only days before the "
                  "first forecast day.", ["Predictive Intelligence"])


def savings(summary, share=0.2, tariff=None, factor=None):
    q = QUESTIONS["save"]
    if summary is None or summary.empty:
        return Answer(q, "This college has no occupancy data, so NEXUS cannot tell when buildings "
                         "are near-empty. See Recommendations for unusual-use checks.", None, "",
                      ["Recommendations"])
    ok = summary[summary["energy_note"] == ""].copy()
    if ok.empty:
        return Answer(q, "Insufficient data: no building has enough near-empty and busy hours "
                         "with energy readings to compare.")
    ok["near_empty_kwh"] = ok["quiet_kwh"] * ok["quiet_energy_hours"]
    ok = ok.sort_values("near_empty_kwh", ascending=False)
    t = pd.DataFrame({
        "Building": ok["building"],
        "Near-empty kWh/h": ok["quiet_kwh"].round(1),
        "Busy kWh/h": ok["busy_kwh"].round(1),
        "Near-empty vs busy %": (ok["quiet_vs_busy"] * 100).round(),
        "Near-empty semester hours": ok["quiet_energy_hours"],
        "kWh in those hours": ok["near_empty_kwh"].round(),
        f"kWh if {share:.0%} lower": (ok["near_empty_kwh"] * share).round(),
    })
    saved = (ok["near_empty_kwh"] * share).sum()
    money = (f" At your tariff of ₹{tariff:g}/kWh that is about **₹{saved * tariff:,.0f}**."
             if tariff else " Add a tariff in Settings to see this in rupees.")
    carbon = (f" With your factor of {factor:g} kg CO₂/kWh, about **{saved * factor / 1000:,.1f} t CO₂**."
              if factor else "")
    top = ok.iloc[0]
    text = (f"The clearest place to look is energy used while buildings are near-empty. "
            f"**{top['building']}** draws {top['quiet_kwh']:.1f} kWh/h when near-empty, "
            f"{top['quiet_vs_busy']:.0%} of its busy level. **If** near-empty use across these "
            f"buildings were {share:.0%} lower, the hours in this data would have used about "
            f"**{saved:,.0f} kWh** less.{money}{carbon} This is a scenario you set, not a forecast "
            "of savings: only a site check can say what can be switched off.")
    return Answer(q, text, t,
                  "Near-empty = under 10% of the building's usual peak of people on Wi-Fi; busy = "
                  "at least 50%. Semester weeks only. kWh in those hours = median near-empty kWh/h "
                  "x number of near-empty hours with readings. The reduction is your assumption.",
                  ["Institutional Intelligence", "Recommendations"])


def underused(summary):
    q = QUESTIONS["underused"]
    if summary is None or summary.empty:
        return Answer(q, "This college has no occupancy data, so NEXUS cannot tell how much "
                         "buildings are used.")
    t = summary.sort_values("quiet_in_class_hours", ascending=False)
    top = t.iloc[0]
    text = (f"During semester class hours (weekdays 09:00-17:00), **{top['building']}** was "
            f"near-empty most often: {top['quiet_in_class_hours']:.0%} of {top['class_hours']:,} hours "
            f"had fewer than {0.1 * top['busy_level']:.0f} people on Wi-Fi. The data has no rooms, "
            "timetables or capacities, so this is building-level, not room utilisation.")
    table = pd.DataFrame({
        "Building": t["building"],
        "Near-empty in class hours %": (t["quiet_in_class_hours"] * 100).round(1),
        "Median people, class hours": t["class_hours_people"].round(),
        "Usual peak (95th pct hour)": t["busy_level"].round(),
        "Class hours": t["class_hours"]})
    return Answer(q, text, table,
                  "Near-empty = under 10% of the building's own usual peak (its 95th-percentile "
                  "hour). Semester weeks come from the academic calendar.",
                  ["Institutional Intelligence"])
