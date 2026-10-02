"""Predictive Intelligence page: 14-day daily energy forecasts, starting where the data ends."""
import altair as alt
import pandas as pd
import streamlit as st

from nexus.predictive import BAND, HORIZON, METHODS, forecast
from views import common
from views.common import ACTUAL, FORECAST, NEUTRAL


def show():
    daily, types, ev = common.predictive()
    usable = ev[ev["note"] == ""] if not ev.empty else ev
    if usable.empty:
        st.info("Insufficient data to forecast: no building has enough complete days.")
        return
    train, test = usable["train_period"].iloc[0], usable["test_period"].iloc[0]
    has_cal = common.dataset().has_calendar

    # ---------------------------------------------------- one forecast per building
    # Each forecast starts the day after that building's last complete day of data.
    rows, forecasts = [], {}
    for r in usable.itertuples():
        s = daily[daily["building"] == r.building].set_index("date")["kwh"].sort_index()
        origin = s.index.max() + pd.Timedelta(days=1)
        f = forecast(s, types, origin)
        f["forecast"] = f[r.method]
        f["low"] = f["forecast"] * (1 + r.band_low)
        f["high"] = f["forecast"] * (1 + r.band_high)
        forecasts[r.building] = (s, origin, f)
        recent = s[s.index >= origin - pd.Timedelta(days=HORIZON)]
        complete = not f["forecast"].isna().any()
        rows.append({"Building": r.building, "From": origin, "kwh": f["forecast"].sum() if complete else None,
                     "recent": recent.sum() if len(recent) == HORIZON else None})
    summary = pd.DataFrame(rows)
    last_data = max(o for _, o, _ in forecasts.values()) - pd.Timedelta(days=1)

    st.subheader(f"The next {HORIZON} days after the data ends")
    st.markdown(
        f"The data ends on **{last_data:%a %d %b %Y}**, so every forecast below starts the day after "
        f"and covers the {HORIZON} days that follow. Nothing here is a forecast of past days."
        + ("" if last_data >= pd.Timestamp.today().normalize() - pd.Timedelta(days=7) else
           f" These dates are in the past because this college's public data stops there; "
           "they are not predictions for today."))

    both = summary.dropna(subset=["kwh", "recent"])
    if len(both) == len(summary):
        change = both["kwh"].sum() / both["recent"].sum() - 1
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Campus, next {HORIZON} days", f"{both['kwh'].sum():,.0f} kWh")
        c2.metric(f"Last {HORIZON} days of data", f"{both['recent'].sum():,.0f} kWh")
        c3.metric("Forecast vs last 14 days", f"{change:+.1%}")
    else:
        st.info("Campus total not shown: at least one building has an incomplete forecast or "
                "too few recent complete days.")

    # -------------------------------------------------------------- building view
    building = st.selectbox("Building", sorted(usable["building"]), key="pred_building")
    s, origin, f = forecasts[building]
    r = usable.set_index("building").loc[building]
    method = r["method"]
    if f["forecast"].isna().all():
        st.info("Insufficient data: no complete days in the 4 weeks before the end of the data.")
        return
    missing_days = int(f["forecast"].isna().sum())

    before = s[(s.index >= origin - pd.Timedelta(days=28)) & (s.index < origin)]
    past = pd.DataFrame({"date": before.index, "actual": before.to_numpy()})
    # The line joins the last real day to the first forecast day so the break is visible.
    bridge = pd.concat([past.tail(1).rename(columns={"actual": "forecast"}),
                        f[["date", "forecast"]]], ignore_index=True)
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b"))
    band = alt.Chart(f).mark_area(color=FORECAST, opacity=0.2).encode(
        x=x, y=alt.Y("low:Q", title="kWh per day"), y2="high:Q")
    predicted = alt.Chart(bridge).mark_line(color=FORECAST, strokeWidth=2, strokeDash=[4, 3]
                                            ).encode(x=x, y="forecast:Q")
    points = alt.Chart(f).mark_point(color=FORECAST, filled=True, size=30).encode(x=x, y="forecast:Q")
    actual = alt.Chart(past).mark_line(color=ACTUAL, strokeWidth=2,
                                       point=alt.OverlayMarkDef(color=ACTUAL, size=30)
                                       ).encode(x=x, y="actual:Q")
    end = alt.Chart(pd.DataFrame({"date": [origin]})).mark_rule(
        color=NEUTRAL, strokeDash=[2, 2]).encode(x="date:T")
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["date"], empty=False)
    hover_df = pd.concat([past.assign(day_type=None), f[["date", "day_type", "forecast", "low", "high"]]],
                         ignore_index=True)
    hover = alt.Chart(hover_df).mark_rule(color=NEUTRAL).encode(
        x="date:T", opacity=alt.condition(nearest, alt.value(0.4), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Day", format="%a %d %b %Y"),
                 alt.Tooltip("actual:Q", title="Actual kWh", format=",.0f"),
                 alt.Tooltip("forecast:Q", title="Forecast kWh", format=",.0f"),
                 alt.Tooltip("low:Q", title="80% range from", format=",.0f"),
                 alt.Tooltip("high:Q", title="80% range to", format=",.0f")],
    ).add_params(nearest)

    st.subheader(f"{building}: forecast from {origin:%d %b %Y}")
    st.markdown(
        f'<span style="color:{ACTUAL}">━━</span>&nbsp;Recorded&emsp;'
        f'<span style="color:{FORECAST}">╍╍</span>&nbsp;Forecast&emsp;'
        f'<span style="color:{FORECAST};opacity:.4">■</span>&nbsp;80% range&emsp;'
        f'<span style="color:{NEUTRAL}">┊</span>&nbsp;End of data', unsafe_allow_html=True)
    st.altair_chart(band + actual + predicted + points + end + hover, width="stretch")
    st.caption("The last 28 recorded days, then the forecast. Missing points are days without a "
               "complete 24 hours of meter data.")

    m1, m2 = st.columns(2)
    if missing_days:
        m1.metric(f"Forecast, {HORIZON} days", "Incomplete",
                  help=f"{missing_days} of {HORIZON} days could not be forecast: not enough recent "
                       "complete days of the same weekday or day type. No total is given rather "
                       "than a partial one.")
    else:
        m1.metric(f"Forecast, {HORIZON} days", f"{f['forecast'].sum():,.0f} kWh",
                  help="Sum of the daily forecasts. The 80% range on the chart is per day; it was "
                       "tested on single days, not on 14-day totals.")
        recent = s[s.index >= origin - pd.Timedelta(days=HORIZON)]
        if len(recent) == HORIZON:
            m2.metric(f"Last {HORIZON} recorded days", f"{recent.sum():,.0f} kWh",
                      f"{f['forecast'].sum() / recent.sum() - 1:+.1%} forecast vs these")
        else:
            m2.metric(f"Last {HORIZON} recorded days", "Incomplete",
                      help="Some of those days lack a complete 24 hours of meter data.")

    st.markdown(
        f"**Method for {building}:** {METHODS[method].lower()}. "
        + (("For each day, the median of recent days of the same type"
            + (" (semester weekday, break weekday, Saturday, Sunday or holiday) from the "
               "institute calendar" if has_cal else " (weekday, Saturday, Sunday)")
            + ". Weekdays after the calendar ends fall back to the same weekday last week, "
              "because whether they are term days or holidays is not known.")
           if method == "calendar" else
           "Each day is forecast as the same weekday in the most recent week.")
        + f" It was chosen because it was more accurate on earlier data ({train}).")

    with st.expander("Forecast table"):
        st.dataframe(pd.DataFrame({
            "Day": f["date"].dt.strftime("%a %d %b %Y"),
            "Day type": f["day_type"].fillna("Weekday (calendar not known)"),
            "Forecast kWh": f["forecast"].round(),
            "80% range": [f"{lo:,.0f} to {hi:,.0f}" if pd.notna(lo) else "-"
                          for lo, hi in zip(f["low"], f["high"])],
        }), hide_index=True)

    # ------------------------------------------------------------ reliability
    with st.expander("How reliable has this method been?"):
        st.markdown(
            f"Each building's method was chosen on {train}, then checked on {test}, which was not used "
            f"to choose it. For {building}, the method missed by **{r['error_pct']:.0%}** of a typical "
            f"day on average in {test}, and **{r['band_coverage']:.0%}** of days fell inside the 80% "
            "range."
            + ("" if method == "naive" else
               f" It was **{abs(r['skill']):.0%} {'more' if r['skill'] >= 0 else 'less'} accurate** "
               "than the simple rule."))
        st.dataframe(pd.DataFrame({
            "Building": usable["building"],
            "Method": usable["method"].map(METHODS),
            "Average miss, % of a day": (usable["error_pct"] * 100).round(1),
            "Days inside 80% range %": (usable["band_coverage"] * 100).round(),
        }), hide_index=True)
    for row in ev[ev["note"] != ""].itertuples():
        st.caption(f"{row.building}: not forecast. {row.note}.")

    st.warning(
        "**Limits.** Forecasts are statistical patterns, not guarantees. They cannot foresee events, "
        "equipment faults or unusual weather (there is no weather input), and weekdays after the "
        "calendar ends are not known to be term days or holidays. Days without complete meter data "
        f"are skipped. The 80% range comes from the {BAND[0]:.0%}-{BAND[1]:.0%} spread of past errors.")
