"""Overview page: the chosen week at a glance, then what is happening, what next, what to check."""
import html

import altair as alt
import pandas as pd
import streamlit as st

from nexus import insights
from nexus.kpis import HOURS_PER_WEEK, headline, window
from nexus.recommend import EXTREME, PLAN_CHANGE
from views import campus_map, common
from views.common import ACTUAL as BLUE, FORECAST as FORECAST_C, UNUSUAL


def _bullets(lines):
    st.markdown("\n".join(f"- {line}" for line in lines) if lines else "- Insufficient data.")


def _hero(df, analysed, high, recs, snap, ds):
    h = headline(snap)
    chips = [
        f"<b>{analysed['building'].nunique()} of {df['building'].nunique()}</b> buildings analysed",
        f"<b>{df['hour'].min():%b %Y}</b> to <b>{df['hour'].max():%b %Y}</b>",
        f"<b>{len(high):,}</b> higher-than-usual events",
        f"<b>{len(recs):,}</b> suggested checks",
    ]
    st.html(
        '<div class="nx-hero">'
        f'<p class="nx-when">{html.escape(h["when"])}, {html.escape(ds.name)}</p>'
        f'<h2>{html.escape(h["main"])}</h2>'
        f'<p class="nx-details">{html.escape(" ".join(h["details"]))}</p>'
        '<div class="nx-chips">' + "".join(f'<span class="nx-chip">{c}</span>' for c in chips)
        + "</div></div>")


def _energy_text(kwh):
    """kWh up to 99,999, then MWh, so the number fits its card."""
    return f"{kwh:,.0f} kWh" if kwh < 100_000 else f"{kwh / 1000:,.1f} MWh"


def _spark(series):
    """Sparkline values: days without data are left out rather than drawn as zero."""
    values = series.dropna().round(2).tolist()
    return values or None


def _cards(snap, ds):
    """Four week-on-week cards, each with a 4-week sparkline."""
    e, w = snap["energy"], snap["wifi"]
    c1, c2, c3, c4 = st.container(key="kpis").columns(4)
    if e["change"] is None:
        c1.metric("Electricity", "Insufficient data", border=True,
                  help=f"Only {e['coverage']:.0%} of building-hours were recorded in both weeks.")
    else:
        c1.metric("Electricity", _energy_text(e["this"]), f"{e['change']:+.1%}",
                  delta_color="inverse", delta_description="vs last week", border=True,
                  chart_data=_spark(snap["energy_daily"]), chart_type="area",
                  help="Hour-for-hour comparison with the 7 days before, using only "
                       f"building-hours recorded in both weeks ({e['coverage']:.0%}). Lecture is "
                       "excluded (unreliable meter). Sparkline: average kWh per building-hour, "
                       "each day for 4 weeks.")
    if w["change"] is None:
        occ = ds.occupancy
        c2.metric("People on Wi-Fi", "No data", border=True,
                  help=("This college's data has no people or Wi-Fi counts." if occ is None else
                        f"Wi-Fi counts cover {occ['hour'].min():%d %b %Y} to "
                        f"{occ['hour'].max():%d %b %Y}. Pick a week inside that range."))
    else:
        c2.metric("People on Wi-Fi", f"{w['this'] / HOURS_PER_WEEK:,.0f} avg", f"{w['change']:+.0%}",
                  delta_color="off", delta_description="vs last week", border=True,
                  chart_data=_spark(snap["wifi_daily"]), chart_type="area",
                  help="Estimated people connected across all buildings, averaged over the "
                       "week's hours. Wi-Fi counts devices, not exact people. Compared hour for "
                       f"hour with the week before ({w['coverage']:.0%} of building-hours "
                       "comparable).")
    diff = snap["events"] - snap["events_prev"]
    c3.metric("Unusual events", f"{snap['events']}", f"{diff:+d}" if diff else "no change",
              delta_arrow="auto" if diff else "off",
              delta_color="inverse", delta_description="vs last week", border=True,
              chart_data=_spark(snap["events_daily"]), chart_type="bar",
              help="Higher-than-usual events that started this week: hours in a row well above each "
                   "building's baseline (see Resource Intelligence). Bars: flagged hours per day.")
    if snap["missing"] is not None:
        pts = (snap["missing"] - (snap["missing_prev"] or 0)) * 100
        c4.metric("Meter gaps", f"{snap['missing']:.1%}",
                  f"{pts:+.1f} pts" if abs(pts) >= 0.05 else "no change",
                  delta_arrow="auto" if abs(pts) >= 0.05 else "off",
                  delta_color="inverse", delta_description="vs last week", border=True,
                  chart_data=_spark(snap["missing_daily"] * 100),
                  chart_type="area",
                  help="Share of building-hours this week with no energy reading (analysed buildings, counted "
                       "only while each meter was in service). Gaps hide "
                       "real use, so a rising share is a meter or data-feed problem to check.")

ICONS = {"high": "warning", "data": "power_off", "plan": "trending_up", "pattern": "schedule",
         "caution": "info"}   # Material Symbols names (the font Streamlit already loads)
KIND_COLOR = {"high": "#ec835a", "data": "#8b94a8", "plan": "#9085e9", "pattern": "#fab219",
              "caution": "#8ab4ff"}
HOURS_COLORS = {"Busy": "#86b6ef", "In use": "#3987e5", "Near-empty": "#1c5cab",
                "Normal": "#3987e5", "Higher than usual": "#ec835a", "Lower than usual": "#9085e9",
                "No data": "#3a4560"}


def _feed_html(items):
    if not items:
        return '<p class="nx-empty">Nothing stood out this week.</p>'
    rows = []
    for it in items:
        color = KIND_COLOR[it["kind"]]
        rows.append(
            f'<li><span class="nx-ico" style="color:{color};border-color:{color}55" '
            f'aria-hidden="true">{ICONS[it["kind"]]}</span>'
            f'<div><div class="nx-row"><b style="color:{color}">{html.escape(it["title"])}</b>'
            f'<time>{html.escape(it["when"])}</time></div>'
            f'<p>{html.escape(it["text"])}</p></div></li>')
    return '<ul class="nx-feed">' + "".join(rows) + "</ul>"


def _map_and_feed(df, events, recs, ds, week_end, forecast_change):
    items = insights.feed(events, df, recs, week_end, forecast_change)
    if ds.has_map and campus_map.outlines_ready():
        left, right = st.container(key="mapfeed").columns([1.7, 1], gap="medium")
        with left:
            st.subheader("Campus this week")
            status = campus_map.week_status(pd.Timestamp(week_end), df, ds.occupancy)
            buildings, outline = campus_map.load_outlines()
            picked = campus_map.render(
                campus_map.payload(buildings, outline, status, f"Week ending {week_end:%a %-d %b %Y}"),
                height=540, key="overview_map")
            if picked and picked.picked:   # a tapped building opens on the Campus Map page
                st.session_state["campus_picked"] = picked.picked
                st.session_state["_goto"] = "campus"
                st.rerun()
        box = right
    else:
        box = st.container()
    with box:
        st.subheader("Key insights")
        st.html(_feed_html(items))
        st.caption("This week's unusual events and meter gaps first, then patterns across the "
                   "data. All in Recommendations and Resource Intelligence.")


def _panels(df, events, ds, week_end, fc, skipped, change):
    c1, c2, c3 = st.container(key="panels").columns(3, gap="medium")

    with c1:
        st.subheader("Electricity, 30 days")
        trend = insights.daily_trend(df, week_end)
        if trend.empty:
            st.info("Insufficient data: no day in these 30 days has 90% of its hours recorded.")
        else:
            base = alt.Chart(trend).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%-d %b", tickCount=4)))
            line = base.mark_line(color=BLUE, strokeWidth=2).encode(
                y=alt.Y("kwh:Q", title="kWh per day", scale=alt.Scale(zero=False), axis=alt.Axis(tickCount=4)))
            dots = base.transform_filter("datum.high_hours > 0").mark_circle(
                color=UNUSUAL, size=70, opacity=1, stroke="#0a1020", strokeWidth=2).encode(y="kwh:Q")
            hover = base.mark_circle(size=220, opacity=0).encode(
                y="kwh:Q", tooltip=[alt.Tooltip("date:T", title="Day", format="%a %-d %b %Y"),
                                    alt.Tooltip("kwh:Q", title="kWh", format=",.0f"),
                                    alt.Tooltip("high_hours:Q", title="Hours higher than usual")])
            st.altair_chart((line + dots + hover).properties(height=210), width="stretch")
            start, end = window(week_end)
            month = events[(events["direction"] == "high") & (events["start"] >= end - pd.Timedelta(days=30))
                           & (events["start"] < end)]
            note = ("Orange: days with hours higher than usual."
                    + (f" Largest: {month.iloc[0]['building']}, {month.iloc[0]['extra_pct']:+.0%} on "
                       f"{month.iloc[0]['start']:%a %-d %b}." if not month.empty else ""))
            st.caption(note + " Days missing over 10% of building-hours are left out.")

    with c2:
        wifi = insights.building_hours(ds.occupancy, week_end)
        use_wifi = wifi is not None and wifi.loc[wifi["state"] != "No data", "hours"].sum() > 0
        hours = wifi if use_wifi else insights.energy_hours(df, week_end)
        st.subheader("Building hours, this week" if use_wifi else "Energy hours, this week")
        total = int(hours["hours"].sum())
        hours = hours.assign(share=hours["hours"] / max(total, 1))
        order = list(hours["state"])
        donut = alt.Chart(hours).mark_arc(innerRadius=62, outerRadius=92, stroke="#0a1020", strokeWidth=2).encode(
            theta=alt.Theta("hours:Q", stack=True),
            order=alt.Order("order:Q"),
            color=alt.Color("state:N", scale=alt.Scale(domain=order, range=[HOURS_COLORS[s] for s in order]),
                            legend=None),
            tooltip=[alt.Tooltip("state:N", title="State"), alt.Tooltip("hours:Q", title="Building-hours"),
                     alt.Tooltip("share:Q", title="Share", format=".0%")],
        ).transform_calculate(order=f"indexof({order}, datum.state)")
        centre = alt.Chart(pd.DataFrame({"t": [f"{total:,}"]})).mark_text(
            font="Chakra Petch", fontSize=22, fontWeight=600, color="#f2f6ff", dy=-6).encode(text="t:N")
        sub = alt.Chart(pd.DataFrame({"t": ["building-hours"]})).mark_text(
            fontSize=11, color="#a3b0cc", dy=14).encode(text="t:N")
        st.altair_chart((donut + centre + sub).properties(height=200), width="stretch")
        st.html('<div class="nx-keys">' + "".join(
            f'<div class="nx-key"><i style="background:{HOURS_COLORS[r.state]}"></i>{html.escape(r.state)}'
            f'<b>{r.share:.0%}</b></div>' for r in hours.itertuples()) + "</div>")
        st.caption("Busy: at least half the building's usual peak of people on Wi-Fi. Near-empty: "
                   "under 10%. No room capacities exist in this data, so these are not room-use rates."
                   if use_wifi else
                   "Each building-hour this week by its energy flag (see Resource Intelligence). "
                   "No Wi-Fi data for this week.")

    with c3:
        st.subheader("Next 14 days")
        if fc.empty:
            st.info("Insufficient data to forecast from this date.")
        else:
            long = fc.melt("date", ["forecast", "actual"], var_name="series", value_name="kwh").dropna()
            long["series"] = long["series"].map({"forecast": "Forecast", "actual": "Actual"})
            names = ["Actual", "Forecast"]
            chart = alt.Chart(long).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=28)).encode(
                x=alt.X("date:T", title=None, axis=alt.Axis(format="%-d %b", tickCount=4)),
                y=alt.Y("kwh:Q", title="kWh per day", scale=alt.Scale(zero=False), axis=alt.Axis(tickCount=4)),
                color=alt.Color("series:N", scale=alt.Scale(domain=names, range=[BLUE, FORECAST_C]),
                                legend=alt.Legend(orient="top", title=None)),
                strokeDash=alt.StrokeDash("series:N", scale=alt.Scale(domain=names, range=[[1, 0], [4, 3]]),
                                          legend=None),
                tooltip=[alt.Tooltip("date:T", title="Day", format="%a %-d %b %Y"),
                         alt.Tooltip("series:N", title=""), alt.Tooltip("kwh:Q", title="kWh", format=",.0f")])
            st.altair_chart(chart.properties(height=210), width="stretch")
            bits = []
            if change is not None:
                bits.append(f"Forecast {change:+.0%} vs the 14 days before.")
            if fc["actual"].notna().any():
                bits.append("Actual shown on days with complete meter data.")
            else:
                bits.append("No complete meter data for these days yet, so no actual to compare.")
            if skipped:
                bits.append(f"Not included: {', '.join(skipped)}.")
            st.caption(" ".join(bits) + " Sum of each building's forecast; see Predictive Intelligence.")


def show(df, events, snap):
    analysed = df[df["flag"] != "unreliable meter"]
    high = events[events["direction"] == "high"]
    ds = common.dataset()
    _, summary = common.institutional()
    _, _, evaluation = common.predictive()
    recs = common.recommendations()

    _hero(df, analysed, high, recs, snap, ds)
    _cards(snap, ds)
    for building, why in ds.warnings.items():
        st.warning(f"**{building} energy is not analysed.** {why}")

    week_end = snap["week_end"]
    daily, types, _ = common.predictive()
    fc, skipped, change = common.compute(
        f"campus forecast {week_end:%Y-%m-%d}",
        lambda d: insights.campus_forecast(daily, types, evaluation, week_end))
    _map_and_feed(df, events, recs, ds, week_end, change)
    _panels(df, events, ds, week_end, fc, skipped, change)
    st.subheader("Across all the data")

    # average energy per complete day, used below and for the biggest user
    per_day = (analysed.assign(day=analysed["hour"].dt.normalize())
               .groupby(["building", "day"])["kwh"].agg(["sum", "count"]))
    per_day = per_day[per_day["count"] == 24]
    avg = per_day.groupby("building")["sum"].mean().reset_index(name="kwh_per_day")

    # ------------------------------------------------------ three questions
    now, nxt, check = st.container(key="questions").columns(3, gap="large")
    with now:
        st.subheader("What is happening")
        lines = []
        if not avg.empty:
            top = avg.sort_values("kwh_per_day", ascending=False).iloc[0]
            lines.append(f"**{top['building']}** uses the most energy: "
                         f"{top['kwh_per_day']:,.0f} kWh on an average day.")
        if not high.empty:
            e = high.iloc[0]
            lines.append(f"Largest unusual event: **{e['building']}**, {e['start']:%d %b %Y}: "
                         f"{e['actual_kwh']:,.0f} kWh vs {e['expected_kwh']:,.0f} expected "
                         f"over {e['hours']} hours."
                         + (" So far above normal that a meter fault is as likely as real use."
                            if e["extra_pct"] >= EXTREME else ""))
        quiet = (summary[summary["energy_note"] == ""].sort_values("quiet_vs_busy", ascending=False)
                 if not summary.empty else summary)
        if not quiet.empty:
            q = quiet.iloc[0]
            lines.append(f"**{q['building']}** still uses {q['quiet_vs_busy']:.0%} of its "
                         "busy-hour energy when near-empty.")
        _bullets(lines)
        st.caption("Measured. Details in Resource and Institutional Intelligence.")

    with nxt:
        st.subheader("What might happen next")
        lines = []
        ok = evaluation[evaluation["note"] == ""]
        if not ok.empty:
            low, high_err = f"{ok['error_pct'].min():.0%}", f"{ok['error_pct'].max():.0%}"
            spread = low if low == high_err else f"{low} to {high_err}"
            lines.append(f"Daily forecasts missed by **{spread}** of a typical day when "
                         f"tested on {ok['test_period'].iloc[0]}, a year not used to build them.")
        plans = recs[recs["rule"] == "R4"]
        for r in plans.itertuples():
            lines.append(f"**{r.building}:** {r.finding}")
        if ok.shape[0] and plans.empty:
            lines.append("No building's latest forecast differs from the same weeks last year "
                         f"by {PLAN_CHANGE:.0%} or more.")
        _bullets(lines)
        st.caption("Forecast. Details in Predictive Intelligence.")

    with check:
        st.subheader("What to check")
        picks = pd.concat([recs[recs["kind"] == kind].head(1)
                           for kind in ["Investigate", "Check data", "Plan"]])
        if len(picks) < 3:
            picks = pd.concat([picks, recs.drop(picks.index)]).head(3)
        _bullets([f"**{r.title}, {r.building}.** {r.next_step}" for r in picks.itertuples()])
        st.caption(f"Suggested checks, not diagnosed causes. All {len(recs)} in Recommendations.")

    # --------------------------------------------------------------- detail
    st.subheader("Average energy per day")
    bars = alt.Chart(avg).mark_bar(color=BLUE, cornerRadiusEnd=4).encode(
        x=alt.X("kwh_per_day:Q", title="kWh per day (average over complete days)",
                axis=alt.Axis(tickCount=5)),
        y=alt.Y("building:N", sort="-x", title=None, axis=alt.Axis(grid=False),
                scale=alt.Scale(paddingInner=0.45)),
        tooltip=[alt.Tooltip("building:N", title="Building"),
                 alt.Tooltip("kwh_per_day:Q", title="kWh per day", format=",.0f")],
    ).properties(height=alt.Step(36))  # 36 px per building, plus room for the axis
    st.altair_chart(bars, width="stretch")
