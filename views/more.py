"""Settings (tariff, carbon factor, thresholds), Reports (downloads) and Help (plain answers)."""
import html
from datetime import datetime

import pandas as pd
import streamlit as st

from nexus import data, institutional, insights, predictive, recommend, resource
from nexus.kpis import headline
from views import common


# ------------------------------------------------------------------ settings

def _store(key):
    st.session_state[key] = st.session_state.get(f"{key}_input")


def settings():
    st.subheader("Money and carbon")
    st.markdown("NEXUS shows kWh by default. Add your own figures to see rupees and CO₂ in Ask "
                "NEXUS and in Reports. They are kept for this session only and are always shown "
                "next to the result they produced.")
    c1, c2 = st.columns(2)
    c1.number_input("Electricity tariff, ₹ per kWh", min_value=0.0, step=0.5,
                    value=st.session_state.get("tariff"), key="tariff_input",
                    on_change=_store, args=("tariff",), placeholder="Your tariff",
                    help="Use the rate on the electricity bill. Leave empty to show kWh only.")
    c2.number_input("Grid carbon factor, kg CO₂ per kWh", min_value=0.0, step=0.01,
                    value=st.session_state.get("emission_factor"), key="emission_factor_input",
                    on_change=_store, args=("emission_factor",), placeholder="Your factor",
                    help="India's Central Electricity Authority publishes this yearly in its CO2 "
                         "Baseline Database (about 0.71 kg/kWh, provisional, for 2024-25). "
                         "Use the factor for the period you are reporting.")

    st.subheader("Analysis thresholds")
    st.markdown("These are fixed in the code so every visitor sees the same results. Each page "
                "explains how it uses them.")
    rows = [
        ("Hourly energy", "Readings needed for an hour to count", f"{data.MIN_COVERAGE:.0%} of the hour"),
        ("Baseline", "Comparable hours looked at", f"{resource.WINDOW} centred window, same hour, day type and activity"),
        ("Baseline", "Fewest comparable hours for a baseline", f"{resource.MIN_SAMPLES}"),
        ("Unusual hour", "Distance from normal variation", f"more than {resource.Z_LIMIT} robust standard deviations"),
        ("Unusual hour", "Smallest difference that counts", f"{resource.MIN_CHANGE:.0%}"),
        ("Occupancy", "Near-empty / busy", f"under {institutional.QUIET:.0%} / at least {institutional.BUSY:.0%} of the usual peak"),
        ("Forecast", "Horizon and range", f"{predictive.HORIZON} days, {predictive.BAND[0]:.0%}-{predictive.BAND[1]:.0%} of past errors"),
        ("Recommendations", "Unusual use worth a check (R1)", f"{recommend.EVENT_MIN_HOURS}+ hours, {recommend.EVENT_MIN_EXTRA:.0%}+ above expected"),
        ("Recommendations", "High use when near-empty (R3)", f"{recommend.QUIET_RATIO:.0%}+ of busy-hour energy"),
        ("Recommendations", "Forecast differs from last year (R4)", f"{recommend.PLAN_CHANGE:.0%}+"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Area", "Setting", "Value"]), hide_index=True)


# ------------------------------------------------------------------ reports

CSS = """body{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#111;max-width:900px;
margin:32px auto;padding:0 16px;line-height:1.5}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;
margin:28px 0 8px;border-bottom:1px solid #ddd;padding-bottom:4px}.note{background:#fff7e0;
border:1px solid #f0d68a;padding:8px 12px;border-radius:6px}table{border-collapse:collapse;width:100%;
font-size:13px}th,td{border:1px solid #ddd;padding:5px 8px;text-align:left}th{background:#f4f6fa}
.muted{color:#666;font-size:12px}"""


def _report_html(ds, snap, week_table, items, recs, week_events, tariff, factor):
    h = headline(snap)
    e = snap["energy"]
    lines = [f"<li>{html.escape(it['title'])}: {html.escape(it['text'])} <span class='muted'>"
             f"({html.escape(it['when'])})</span></li>" for it in items]
    money = ""
    if e["this"] is not None and (tariff or factor):
        bits = []
        if tariff:
            bits.append(f"about ₹{e['this'] * tariff:,.0f} at ₹{tariff:g}/kWh (your tariff)")
        if factor:
            bits.append(f"about {e['this'] * factor / 1000:,.1f} t CO₂ at {factor:g} kg/kWh (your factor)")
        money = "<p>Electricity this week, comparable hours: " + "; ".join(bits) + ".</p>"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>NEXUS week report</title>
<style>{CSS}</style></head><body>
<h1>NEXUS week report: {html.escape(ds.name)}</h1>
<p class="muted">{html.escape(h['when'])}. Made {datetime.now():%d %b %Y %H:%M}.</p>
<p class="note">{html.escape(ds.source)}{' Not PES data.' if ds.name == common.IIITD or ds.source.startswith('Public sample') else ''}
Every number below is calculated by NEXUS's code from the data; flags are measured differences,
not diagnosed causes.</p>
<h2>The week</h2><p><b>{html.escape(h['main'])}</b> {html.escape(' '.join(h['details']))}</p>{money}
<h2>Buildings</h2>{week_table.to_html(index=False, na_rep="-")}
<h2>Key insights</h2><ul>{''.join(lines) or '<li>Nothing stood out this week.</li>'}</ul>
<h2>Higher-than-usual events this week</h2>
{week_events.to_html(index=False) if not week_events.empty else '<p>None.</p>'}
<h2>Suggested checks</h2>
{recs[['title', 'building', 'finding', 'next_step']].rename(columns=str.capitalize).to_html(index=False) if not recs.empty else '<p>None.</p>'}
<p class="muted">Method: each hour is compared with the median of comparable hours (same hour,
day type and academic activity, 3 weeks either side); week figures compare the same hours in
both weeks. See the NEXUS README for details.</p></body></html>"""


def reports(week_end):
    ds = common.dataset()
    df, events = common.load()
    snap = common.week(week_end)
    recs = common.recommendations()
    daily, types, evaluation = common.predictive()
    _, _, change = common.compute(f"campus forecast {week_end:%Y-%m-%d}",
                                  lambda d: insights.campus_forecast(daily, types, evaluation, week_end))
    items = insights.feed(events, df, recs, week_end, change, limit=8)
    week_table = insights.building_week(df, week_end)
    start, end = snap["start"], snap["week_end"] + pd.Timedelta(days=1)
    wk = events[(events["start"] >= start) & (events["start"] < end) & (events["direction"] == "high")]
    week_events = common.events_table(wk)
    tariff, factor = st.session_state.get("tariff"), st.session_state.get("emission_factor")

    st.markdown(f"Reports for **{ds.name}**, week ending **{week_end:%a %-d %b %Y}** (change the "
                "week at the top).")
    report = _report_html(ds, snap, week_table, items, recs, week_events, tariff, factor)
    c1, c2, c3 = st.columns(3)
    c1.download_button("Week report (HTML)", report, f"nexus-week-{week_end:%Y-%m-%d}.html",
                       "text/html", icon=":material/description:", type="primary",
                       help="Opens in any browser; use Print to save it as a PDF.")
    c2.download_button("All unusual events (CSV)", common.events_table(events).to_csv(index=False),
                       "nexus-events.csv", "text/csv", icon=":material/table:")
    c3.download_button("Suggested checks (CSV)", recs.drop(columns=["size"], errors="ignore").to_csv(index=False),
                       "nexus-checks.csv", "text/csv", icon=":material/checklist:")

    st.subheader("Preview")
    h = headline(snap)
    st.markdown(f"**{h['main']}** {' '.join(h['details'])}")
    st.dataframe(week_table, hide_index=True)
    if tariff or factor:
        st.caption("The report adds rupees and CO₂ using the figures from Settings, labelled as yours.")
    else:
        st.caption("Add a tariff or carbon factor in Settings to include rupees or CO₂ in the report.")


# ------------------------------------------------------------------ help

HELP = [
    ("What data is this?",
     "By default, public data from IIIT-Delhi (I-BLEND, 2013-2017): electricity for 7 buildings "
     "every minute, Wi-Fi connection counts every 10 minutes, and the academic calendar. It is not "
     "PES data. You can add another college's data on the Add college data page."),
    ("What is a baseline?",
     "For each building and hour, the median of comparable hours: same hour of day, same type of "
     "day (working or not), same academic activity, within 3 weeks either side. Its middle half "
     "is the normal range shown on charts."),
    ("When is an hour 'higher than usual'?",
     "When it is more than 3.5 robust standard deviations above the baseline and at least 10% "
     "higher. Back-to-back flagged hours form one event. It is a measured difference, not a cause."),
    ("Why is Lecture's energy left out?",
     "Its meter reads exactly 0 for 82% of recorded minutes, including half of class hours, so "
     "its readings cannot be trusted. Its Wi-Fi counts are still used."),
    ("What do busy and near-empty mean?",
     "Relative to each building's own usual peak (its 95th-percentile hour of people on Wi-Fi): "
     "busy is at least half of it, near-empty is under 10%. There are no room capacities in the "
     "data, so these are not room-use rates."),
    ("How good are the forecasts?",
     "Each building's method was chosen using forecast days before the last year of data, then "
     "scored on forecasts made in that last year. Predictive Intelligence shows the error for "
     "every building, including where the simple rule did better."),
    ("Where do the map's buildings come from?",
     "OpenStreetMap outlines of today's campus. Five I-BLEND buildings are matched (four by name, "
     "Dining by use); Lecture and Facilities are not identified there, so they are left off."),
    ("How does searching for a college work?",
     "Type its name in the College box. NEXUS checks its own list of vetted datasets, then searches "
     "Zenodo, Figshare and Harvard Dataverse for records that name the college and mention "
     "electricity or energy. It only downloads files under an open licence, and only analyses a "
     "CSV with a clear time column and energy columns labelled kWh, kW or W. If nothing qualifies "
     "it says 'College data unavailable'. That means none was found in those sources, not that "
     "none exists. Colleges rarely publish meter data, so this is common."),
    ("Where does the map come from for other colleges?",
     "OpenStreetMap: the college is looked up by name and its buildings are drawn in 3D. A meter "
     "building is placed on the map only when its name matches exactly one outline; the rest are "
     "listed as not placed."),
    ("What does the conversation send to the AI?",
     "Your questions, and the NEXUS numbers the assistant looks up to answer them (for example a "
     "week's building table), go to Anthropic's API. The raw data files are never sent. Without an "
     "API key the Quick answers tab still works, using fixed rules only."),
    ("Is uploaded data stored?",
     "It is sent to the NEXUS server and kept in its memory for your session only. It is not "
     "written to disk or shown to other visitors, and it is cleared when you reload or close "
     "the page."),
    ("Why no rupees by default?",
     "The data has no tariff. Add yours in Settings and Ask NEXUS and Reports show rupees next "
     "to the kWh, labelled as your figure."),
]


def help_page():
    for q, a in HELP:
        with st.expander(q):
            st.markdown(a)
    st.caption("More detail: the README and DATA.md in the project repository, and the Data & "
               "method page.")
