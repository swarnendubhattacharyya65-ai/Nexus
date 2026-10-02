"""Recommendations tab: rule-based next steps, each with its evidence."""
import pandas as pd
import streamlit as st

from nexus.recommend import RULES
from views import common

KINDS = ["Investigate", "Check data", "Plan", "Caution"]


def show():
    recs = common.recommendations()
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
                    "enough data are skipped rather than guessed. The data has no tariff, so "
                    "rules use kWh; rupees appear in Ask NEXUS and Reports only from a tariff "
                    "you enter in Settings.")
