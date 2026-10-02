"""The frame around every page: styles, top bar (college, week, search) and page headers."""
import html

import pandas as pd
import streamlit as st

from nexus.dataset import IIITD
from views import common
from views.resource import event_ids

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

/* key insights feed and legends */
.nx-feed { list-style: none; margin: 0; padding: 0; }
.nx-feed li { display: grid; grid-template-columns: 32px 1fr; gap: 10px; align-items: start;
  padding: 10px 2px; border-bottom: 1px solid rgba(127,178,255,0.1); }
.nx-feed li:last-child { border-bottom: 0; }
.nx-ico { width: 30px; height: 30px; border-radius: 8px; border: 1px solid; display: grid;
  place-items: center; background: rgba(255,255,255,0.03);
  font-family: "Material Symbols Rounded"; font-size: 18px; line-height: 1; overflow: hidden; }
.nx-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.nx-feed b { font-weight: 600; font-size: 0.95rem; }
.nx-feed p { margin: 2px 0 0; color: #c9d4ee; font-size: 0.88rem; line-height: 1.4; }
.nx-feed time { color: #8b94a8; font-size: 0.78rem; white-space: nowrap; }
.nx-empty { color: #a3b0cc; }
.nx-keys { display: flex; flex-wrap: wrap; gap: 4px 18px; }
.nx-key { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; color: #c9d4ee; padding: 2px 0; }
.nx-key i { width: 10px; height: 10px; border-radius: 3px; flex: none; }
.nx-key b { color: #f2f6ff; font-weight: 600; }

/* narrow main area (portrait tablet, or sidebar open on a small screen) */
[data-testid="stMainBlockContainer"] { container-type: inline-size; }
@container (max-width: 760px) {
  .st-key-kpis [data-testid="stHorizontalBlock"],
  .st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 1rem; }
  .st-key-kpis [data-testid="stColumn"],
  .st-key-topbar [data-testid="stColumn"] { min-width: calc(50% - 0.5rem); }
  .st-key-questions [data-testid="stHorizontalBlock"],
  .st-key-mapfeed [data-testid="stHorizontalBlock"],
  .st-key-panels [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 0.5rem; }
  .st-key-questions [data-testid="stColumn"],
  .st-key-mapfeed [data-testid="stColumn"],
  .st-key-panels [data-testid="stColumn"] { min-width: 100%; }
}
</style>
"""


def style():
    st.html(CSS)


def notice(ds):
    """Where the data on screen comes from, always visible."""
    if ds.name == IIITD:
        text = "Public IIIT-Delhi data. <b>Not PES data.</b>"
    elif ds.source.startswith("Public sample"):
        text = f"{html.escape(ds.source)} <b>Not PES data.</b>"
    else:
        text = html.escape(ds.source)
    st.html(f'<div class="nx-notice"><span>{text}</span></div>')


def page_header(title, description):
    st.html(f'<div class="nx-page"><h1>{html.escape(title)}</h1>'
            f'<p>{html.escape(description)}</p></div>')


# ------------------------------------------------------------------ top bar

# Widgets whose options depend on the college; cleared when the college changes.
PER_COLLEGE = ["res_building", "res_period", "res_direction", "res_event", "inst_building",
               "inst_period", "pred_building", "pred_origin", "search"]


def week_key():
    """Each college keeps its own week, so switching college starts at that college's latest week."""
    return f"week_end::{common.college()}"


def week_end():
    return st.session_state[week_key()]


def _college_changed():
    for key in PER_COLLEGE:
        st.session_state.pop(key, None)


def top_bar():
    """College, week and search controls shared by every page."""
    names = common.colleges()
    if st.session_state.get("college") not in names:
        st.session_state["college"] = names[0]
    c1, c2, c3, c4 = st.container(key="topbar").columns([1.5, 1.1, 2.2, 1.5],
                                                         vertical_alignment="bottom")
    c1.selectbox("College", names, key="college", on_change=_college_changed)

    ds = common.dataset()
    last = common.last_full_day().date()
    latest = ds.last.date()
    first = min((ds.first + pd.Timedelta(days=14)).date(), latest)
    key = week_key()
    chosen = st.session_state.get(key)
    if chosen is not None and not first <= chosen <= latest:
        st.session_state.pop(key)
    default = {} if key in st.session_state else {"value": last}
    c2.date_input("Week ending", min_value=first, max_value=latest, key=key,
                  format="DD/MM/YYYY", **default,
                  help="The Overview compares the 7 days ending on this date with the 7 days "
                       "before. Defaults to the last date with energy data (and Wi-Fi data, "
                       "where the college has it).")
    query = c3.text_input("Search", placeholder="A building, a date (2016-09) or a check",
                          key="search")
    with c4:
        notice(ds)
    if query.strip():
        _results(query.strip())


def _go(page, state=None):
    """Button callback: remember where to go; app.py switches page on the next run."""
    for key, value in (state or {}).items():
        st.session_state[key] = value
    st.session_state["search"] = ""
    st.session_state["_goto"] = page


def _results(query):
    df, events = common.load()
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
    recs = common.recommendations()
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
