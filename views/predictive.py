"""Predictive Intelligence tab: 14-day daily energy forecasts, tested on 2017."""
import altair as alt
import pandas as pd
import streamlit as st

from nexus.predictive import (BAND, HORIZON, METHODS, TEST_FROM, WARM_UP, backtest,
                              daily_energy, day_types, evaluate, forecast)

ACTUAL = "#2a78d6"
FORECAST = "#eb6834"
NEUTRAL = "#8c8b86"


@st.cache_data(show_spinner="Testing forecasts on past data ...")
def _data():
    daily, types = daily_energy(), day_types()
    return daily, types, evaluate(backtest(daily, types))


def show():
    daily, types, ev = _data()
    st.caption(f"Forecasts each building's daily energy {HORIZON} days ahead with two simple, "
               "transparent methods, and shows how accurate they were on past data. "
               "Pick any date to see what NEXUS would have forecast then, next to what "
               "actually happened.")

    # -------------------------------------------------------------- controls
    usable = ev[ev["note"] == ""]
    if usable.empty:
        st.info("Insufficient data to test forecasts.")
        return
    c1, c2 = st.columns([1, 1])
    building = c1.selectbox("Building", sorted(usable["building"]), key="pred_building")
    s = daily[daily["building"] == building].set_index("date")["kwh"].sort_index()
    first = (s.index.min() + pd.Timedelta(days=WARM_UP)).date()
    last = (s.index.max() - pd.Timedelta(days=HORIZON - 1)).date()
    origin = pd.Timestamp(c2.date_input("Forecast made on", last, min_value=first,
                                        max_value=last, key="pred_origin"))

    r = usable.set_index("building").loc[building]
    method = r["method"]
    f = forecast(s, types, origin)
    f["forecast"] = f[method]
    f["low"] = f["forecast"] * (1 + r["band_low"])
    f["high"] = f["forecast"] * (1 + r["band_high"])
    if f["forecast"].isna().all():
        st.info("Insufficient data: no complete days in the 4 weeks before this date.")
        return

    # ----------------------------------------------------------------- chart
    before = s[(s.index >= origin - pd.Timedelta(days=28)) & (s.index < origin)]
    chart_df = pd.concat([
        pd.DataFrame({"date": before.index, "actual": before.to_numpy()}),
        f[["date", "actual", "forecast", "low", "high", "day_type"]],
    ], ignore_index=True)

    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d %b"))
    band = alt.Chart(f).mark_area(color=FORECAST, opacity=0.2).encode(
        x=x, y=alt.Y("low:Q", title="kWh per day"), y2="high:Q")
    predicted = alt.Chart(f).mark_line(color=FORECAST, strokeWidth=2, strokeDash=[4, 3],
                                       point=alt.OverlayMarkDef(color=FORECAST, size=30)
                                       ).encode(x=x, y="forecast:Q")
    actual = alt.Chart(chart_df.dropna(subset=["actual"])).mark_line(
        color=ACTUAL, strokeWidth=2, point=alt.OverlayMarkDef(color=ACTUAL, size=30)
    ).encode(x=x, y="actual:Q")
    made = alt.Chart(pd.DataFrame({"date": [origin]})).mark_rule(
        color=NEUTRAL, strokeDash=[2, 2]).encode(x="date:T")
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["date"], empty=False)
    hover = alt.Chart(chart_df).mark_rule(color=NEUTRAL).encode(
        x="date:T",
        opacity=alt.condition(nearest, alt.value(0.4), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Day", format="%a %d %b %Y"),
                 alt.Tooltip("day_type:N", title="Day type"),
                 alt.Tooltip("actual:Q", title="Actual kWh", format=",.0f"),
                 alt.Tooltip("forecast:Q", title="Forecast kWh", format=",.0f"),
                 alt.Tooltip("low:Q", title="80% range from", format=",.0f"),
                 alt.Tooltip("high:Q", title="80% range to", format=",.0f")],
    ).add_params(nearest)

    st.subheader(f"{building}: forecast made on {origin:%d %b %Y}")
    st.markdown(
        f'<span style="color:{ACTUAL}">━━</span>&nbsp;Actual&emsp;'
        f'<span style="color:{FORECAST}">╍╍</span>&nbsp;Forecast&emsp;'
        f'<span style="color:{FORECAST};opacity:.4">■</span>&nbsp;80% range&emsp;'
        f'<span style="color:{NEUTRAL}">┊</span>&nbsp;Forecast made',
        unsafe_allow_html=True)
    st.altair_chart(band + actual + predicted + made + hover, width="stretch")
    st.caption("The 28 days before the forecast date, then the 14 forecast days. Missing "
               "points are days without a complete 24 hours of meter data.")

    # --------------------------------------------------------------- numbers
    scored = f.dropna(subset=["actual", "forecast"])
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Forecast, {HORIZON} days", f"{f['forecast'].sum():,.0f} kWh",
              help=f"80% range {f['low'].sum():,.0f} to {f['high'].sum():,.0f} kWh")
    if len(scored) == HORIZON:
        miss = scored["actual"].sum() / scored["forecast"].sum() - 1
        m2.metric("Actual", f"{scored['actual'].sum():,.0f} kWh")
        m3.metric("Actual vs forecast", f"{miss:+.1%}")
    else:
        m2.metric("Actual", "Incomplete",
                  help=f"Only {len(scored)} of {HORIZON} days have complete meter data.")
    st.markdown(
        f"**Method for {building}:** {METHODS[method].lower()}. "
        + ("For each day, the median of recent days of the same type (semester weekday, "
           "break weekday, Saturday, Sunday or holiday) from the institute calendar, "
           "which is published in advance."
           if method == "calendar" else
           "Each day is forecast as the same weekday in the most recent week.")
        + f" It was chosen because it was more accurate on 2014-2016. On 2017, which was "
          f"not used to choose it, it missed by **{r['error_pct']:.0%}** of a typical day on "
          f"average, and **{r['band_coverage']:.0%}** of actual days fell inside the 80% range."
        + ("" if method == "naive" else
           f" Compared with the simple rule on 2017, it was **{abs(r['skill']):.0%} "
           f"{'more' if r['skill'] >= 0 else 'less'} accurate**."))

    with st.expander("Day by day"):
        table = f.assign(error=(f["actual"] - f["forecast"]) / f["forecast"])
        st.dataframe(pd.DataFrame({
            "Day": table["date"].dt.strftime("%a %d %b %Y"),
            "Day type": table["day_type"],
            "Forecast kWh": table["forecast"].round(),
            "80% range": [f"{lo:,.0f} to {hi:,.0f}" for lo, hi in zip(table["low"], table["high"])],
            "Actual kWh": table["actual"].round(),
            "Actual vs forecast %": (table["error"] * 100).round(),
        }), hide_index=True)

    # -------------------------------------------------------------- accuracy
    st.subheader("How accurate is this?")
    cal = usable[usable["method"] == "calendar"]
    better = ", ".join(f"{b} {s:+.0%}" for b, s in zip(cal["building"], cal["skill"]) if s > 0)
    worse = ", ".join(f"{b} {s:+.0%}" for b, s in zip(cal["building"], cal["skill"]) if s <= 0)
    st.markdown(
        "Tested by forecasting every 7 days through the history, using only data available "
        f"at the time. Each building's method was chosen on 2014-2016, then scored on "
        f"{TEST_FROM:%Y}, which was not used to choose it.\n\n"
        f"- The calendar method was chosen for **{len(cal)} of {len(usable)}** buildings"
        + ("; the others use the simple 'same weekday last week' rule.\n"
           if len(cal) < len(usable) else ".\n")
        + f"- On {TEST_FROM:%Y} it beat the simple rule in: **{better or 'none'}**.\n"
        + (f"- On {TEST_FROM:%Y} it did not beat the simple rule in: **{worse}**. NEXUS reports "
           "this rather than switch methods after seeing the test year.\n" if worse else ""))
    st.dataframe(pd.DataFrame({
        "Building": usable["building"],
        "Method": usable["method"].map(METHODS),
        "Average miss, kWh/day": usable["mae_calendar"].where(
            usable["method"] == "calendar", usable["mae_naive"]).round(),
        "Average miss, % of a day": (usable["error_pct"] * 100).round(1),
        "Better than simple rule by %": (usable["skill"] * 100).round(),
        "Days inside 80% range %": (usable["band_coverage"] * 100).round(),
        "Forecasts scored": usable["test_days"],
    }), hide_index=True)
    for row in ev[ev["note"] != ""].itertuples():
        st.caption(f"{row.building}: not forecast. {row.note}.")

    st.warning(
        "**Limits.** Forecasts are statistical patterns, not guarantees. They cannot foresee "
        "events, equipment faults or unusual weather (the dataset has no weather), and they "
        "rely on the institute calendar being known in advance. Days without complete meter "
        f"data are skipped. The 80% range comes from the {BAND[0]:.0%}-{BAND[1]:.0%} spread of "
        "past forecast errors. Data covers 2013-2017, so forecasts are shown for past dates "
        "where the actual outcome is known.")
