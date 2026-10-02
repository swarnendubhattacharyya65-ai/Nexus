"""The frame around every page: styles, top bar (college, week, search) and page headers."""
import html

import pandas as pd
import streamlit as st

from nexus.kpis import default_week_end
from views.common import load
from views.resource import event_ids

COLLEGES = ["IIIT-Delhi, New Delhi"]

CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 520px at 88% -8%, rgba(79,140,255,0.13), transparent 62%),
    radial-gradient(800px 480px at -12% 18%, rgba(144,133,233,0.08), transparent 60%),
    #0a1020;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"] { padding-top: 3.4rem; }

/* page header */
.nx-page h1 { font-family: "Chakra Petch", sans-serif; font-weight: 700; font-size: 2.1rem;
  letter-spacing: 0.01em; margin: 0 0 0.25rem; padding: 0; color: #f2f6ff; }
.nx-page p { color: #a3b0cc; margin: 0; max-width: 78ch; }

/* public-data notice, always visible */
.nx-notice { display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px;
  border-radius: 10px; border: 1px solid rgba(250,178,25,0.32); background: rgba(250,178,25,0.07);
  color: #f3d58f; font-size: 0.85rem; line-height: 1.3; }
.nx-notice b { color: #ffe3a3; font-weight: 600; }

/* hero */
.nx-hero { position: relative; overflow: hidden; padding: 30px 34px 26px; border-radius: 20px;
  border: 1px solid rgba(127,178,255,0.24);
  background:
    radial-gradient(600px 260px at 100% 0%, rgba(144,133,233,0.22), transparent 70%),
    linear-gradient(135deg, rgba(57,135,229,0.20), rgba(17,27,48,0.35) 55%, rgba(10,16,32,0.2)); }
.nx-hero::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background-image: linear-gradient(rgba(127,178,255,0.06) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(127,178,255,0.06) 1px, transparent 1px);
  background-size: 28px 28px; mask-image: linear-gradient(90deg, transparent 35%, #000 100%); }
.nx-when { color: #a3b0cc; font-size: 0.95rem; margin: 0 0 6px; }
.nx-hero h2 { font-family: "Chakra Petch", sans-serif; font-weight: 600; color: #f4f7ff;
  font-size: clamp(1.7rem, 3vw, 2.6rem); line-height: 1.12; margin: 0 0 10px; padding: 0;
  max-width: 24ch; }
.nx-details { color: #c9d4ee; font-size: 1.02rem; margin: 0; max-width: 72ch; line-height: 1.55; }
.nx-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; position: relative; z-index: 1; }
.nx-chip { padding: 6px 12px; border-radius: 999px; font-size: 0.86rem; color: #b9c6e4;
  background: rgba(127,178,255,0.07); border: 1px solid rgba(127,178,255,0.18); }
.nx-chip b { color: #f2f6ff; font-weight: 600; }

/* glass cards: the week cards and bordered containers */
.st-key-kpis [data-testid="stMetric"] { background: rgba(20,30,54,0.55); backdrop-filter: blur(6px); }
[data-testid="stMetricValue"] { font-family: "Chakra Petch", sans-serif; }
[data-testid="stVerticalBlockBorderWrapper"] { background: rgba(17,26,46,0.45); }

/* narrow main area (portrait tablet, or sidebar open on a small screen) */
[data-testid="stMainBlockContainer"] { container-type: inline-size; }
@container (max-width: 760px) {
  .st-key-kpis [data-testid="stHorizontalBlock"],
  .st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 1rem; }
  .st-key-kpis [data-testid="stColumn"],
  .st-key-topbar [data-testid="stColumn"] { min-width: calc(50% - 0.5rem); }
  .st-key-questions [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 0.5rem; }
  .st-key-questions [data-testid="stColumn"] { min-width: 100%; }
}
</style>
"""


def style():
    st.html(CSS)


def notice():
    st.html('<div class="nx-notice"><span>Public IIIT-Delhi data. <b>Not PES data.</b></span></div>')


def page_header(title, description):
    st.html(f'<div class="nx-page"><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(description)}</p></div>')


# ------------------------------------------------------------------ top bar

@st.cache_data(show_spinner=False)
def _last_full_day():
    return default_week_end()


def top_bar():
    """College, week and search controls shared by every page."""
    last = _last_full_day().date()
    df, _ = load()
    first = (df["hour"].min() + pd.Timedelta(days=14)).date()
    c1, c2, c3, c4 = st.container(key="topbar").columns([1.5, 1.1, 2.2, 1.5],
                                                         vertical_alignment="bottom")
    c1.selectbox("College", COLLEGES, key="college")
    c2.date_input("Week ending", value=last, min_value=first, max_value=df["hour"].max().date(),
                  key="week_end", format="DD/MM/YYYY",
                  help="The Overview compares the 7 days ending on this date with the 7 days "
                       "before. Defaults to the last date with both energy and Wi-Fi data.")
    query = c3.text_input("Search", placeholder="A building, a date (2016-09) or a check",
                          key="search")
    with c4:
        notice()
    if query.strip():
        _results(query.strip())


def _go(page, state=None):
    """Button callback: remember where to go; app.py switches page on the next run."""
    for key, value in (state or {}).items():
        st.session_state[key] = value
    st.session_state["search"] = ""
    st.session_state["_goto"] = page


def _results(query):
    from views import recommend

    df, events = load()
    q = query.lower()
    hits = []
    for b in sorted(df.loc[df["flag"] != "unreliable meter", "building"].unique()):
        if q in b.lower():
            hits.append((f"{b}: energy against its baseline", ":material/bolt:",
                         "resource", {"res_building": b}))
    high = events[events["direction"] == "high"]
    text = (high["building"] + " " + high["start"].dt.strftime("%Y-%m-%d %d %b %Y")).str.lower()
    whole = (df["hour"].min().date(), df["hour"].max().date())
    found = high[text.str.contains(q, regex=False)].head(4)
    for e, eid in zip(found.itertuples(), event_ids(found)):
        hits.append((f"{e.building}, {e.start:%d %b %Y}: {e.actual_kwh:,.0f} kWh vs "
                     f"{e.expected_kwh:,.0f} expected", ":material/warning:", "resource",
                     {"res_building": e.building, "res_direction": "higher",
                      "res_period": whole, "res_event": eid}))
    recs = recommend._recs(events)
    rec_text = (recs["title"] + " " + recs["building"] + " " + recs["finding"] + " "
                + recs["next_step"]).str.lower()
    for r in recs[rec_text.str.contains(q, regex=False)].head(4).itertuples():
        hits.append((f"{r.title}, {r.building}", ":material/checklist:", "recommendations", {}))

    with st.container(border=True):
        if not hits:
            st.caption(f'Nothing matches "{query}". Try a building name such as Library, '
                       "a date such as 2016-09, or a word such as meter.")
            return
        st.caption(f"{len(hits)} result{'s' if len(hits) != 1 else ''}")
        for i, (label, icon, page, state) in enumerate(hits[:10]):
            st.button(label, icon=icon, key=f"hit_{i}", type="tertiary",
                      on_click=_go, args=(page, state))
