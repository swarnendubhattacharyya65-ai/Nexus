"""Overview page: the chosen week at a glance, then what is happening, what next, what to check."""
import html

import altair as alt
import pandas as pd
import streamlit as st

from nexus.kpis import HOURS_PER_WEEK, headline
from nexus.recommend import EXTREME, PLAN_CHANGE
from views import common
from views.common import ACTUAL as BLUE


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

    st.subheader("Largest higher-than-usual events")
    top = high.head(5)
    st.dataframe(pd.DataFrame({
        "Building": top["building"],
        "Start": top["start"].dt.strftime("%Y-%m-%d %H:%M"),
        "Hours": top["hours"],
        "Actual kWh": top["actual_kwh"].round(),
        "Expected kWh": top["expected_kwh"].round(),
        "Extra %": (top["extra_pct"] * 100).round(),
    }), hide_index=True)
