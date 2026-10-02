"""Recommendations tab: rule-based next steps, each with its evidence."""
import pandas as pd
import streamlit as st

from nexus.predictive import forecast
from nexus.recommend import RULES, build
from views import institutional, predictive

KINDS = ["Investigate", "Check data", "Plan", "Caution"]


@st.cache_data(show_spinner="Applying recommendation rules ...")
def _recs(events):
    _, summary = institutional._data()
    daily, types, evaluation = predictive._data()
    return build(events, summary, evaluation, daily, types, forecast)


def show(events):
    recs = _recs(events)
    st.warning("**These are things to check, not diagnosed causes.** The data shows what was "
               "measured; only people on site can confirm why.")

    cols = st.columns(len(KINDS))
    for col, kind in zip(cols, KINDS):
        col.metric(kind, int((recs["kind"] == kind).sum()))

    if recs.empty:
        st.info("No rule was triggered by the current data.")
    for (rule, title, kind), group in recs.groupby(["rule", "title", "kind"], sort=True):
        st.subheader(f"{title}")
        st.caption(f"{kind} · rule {rule}")
        for r in group.itertuples():
            with st.container(border=True):
                st.markdown(f"**{r.building}:** {r.finding}")
                st.markdown(f"**Next step:** {r.next_step}")
                st.caption(r.evidence)

    with st.expander("The rules"):
        st.dataframe(pd.DataFrame(RULES, columns=["Rule", "Type", "Name", "Triggered when"]),
                     hide_index=True)
        st.markdown("Thresholds are set in `nexus/recommend.py`. Buildings or periods without "
                    "enough data are skipped rather than guessed. Money values are not shown "
                    "because the dataset has no electricity tariff.")
