"""Overview tab: what is happening, what might happen next, what to check."""
import altair as alt
import pandas as pd
import streamlit as st

from nexus.data import ENERGY_WARNINGS
from nexus.recommend import EXTREME, PLAN_CHANGE
from views import institutional, predictive, recommend

BLUE = "#2a78d6"


def _bullets(lines):
    st.markdown("\n".join(f"- {line}" for line in lines) if lines else "- Insufficient data.")


def show(df, events):
    analysed = df[df["flag"] != "unreliable meter"]
    high = events[events["direction"] == "high"]
    _, summary = institutional._data()
    _, _, evaluation = predictive._data()
    recs = recommend._recs(events)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Buildings analysed", f"{analysed['building'].nunique()} of {df['building'].nunique()}")
    c2.metric("Period", f"{df['hour'].min():%Y}-{df['hour'].max():%Y}",
              help=f"{df['hour'].min():%d %b %Y} to {df['hour'].max():%d %b %Y}")
    c3.metric("Higher-than-usual events", f"{len(high):,}")
    c4.metric("Recommendations", f"{len(recs):,}")
    for building, why in ENERGY_WARNINGS.items():
        st.warning(f"**{building} energy is not analysed.** {why}")

    # average energy per complete day, used below and for the biggest user
    per_day = (analysed.assign(day=analysed["hour"].dt.normalize())
               .groupby(["building", "day"])["kwh"].agg(["sum", "count"]))
    per_day = per_day[per_day["count"] == 24]
    avg = per_day.groupby("building")["sum"].mean().reset_index(name="kwh_per_day")

    # ------------------------------------------------------ three questions
    now, nxt, check = st.columns(3, gap="large")
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
        quiet = summary[summary["energy_note"] == ""].sort_values("quiet_vs_busy", ascending=False)
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
                         "tested on 2017, a year not used to build them.")
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
