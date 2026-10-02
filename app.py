"""NEXUS web app.

Run in the codespace:   streamlit run app.py
Reads only the small tables in data/processed/, so it also runs when deployed.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from nexus.data import OUT

st.set_page_config(page_title="NEXUS", page_icon=":material/hub:", layout="wide")

from views import shell  # noqa: E402  (after set_page_config)

shell.style()
st.logo("static/logo.svg", size="large", icon_image="static/icon.svg")

if not (OUT / "energy_hourly.parquet").exists():
    st.error("No processed data found. In the codespace, run `python -m nexus.data` first.")
    st.stop()

from views import (ask, campus_map, common, institutional, more, overview,  # noqa: E402
                   predictive, recommend, resource, upload)
from nexus.predictive import HORIZON  # noqa: E402


# ------------------------------------------------------------------- pages

def overview_page():
    df, events = common.load()
    overview.show(df, events, common.week(shell.week_end()))


def resource_page():
    shell.page_header("Resource Intelligence",
                      "Each building's hourly electricity against its own baseline: the median "
                      "of comparable hours. Hours far outside the normal range are flagged.")
    resource.show(*common.load())


def institutional_page():
    shell.page_header("Institutional Intelligence",
                      "Building-level patterns from Wi-Fi connection counts. The data has no "
                      "rooms, timetables or capacities, so NEXUS does not report a utilization "
                      "rate: each building is compared with its own busiest hours instead.")
    institutional.show()


def predictive_page():
    shell.page_header("Predictive Intelligence",
                      f"Each building's daily energy forecast {HORIZON} days ahead with two "
                      "simple, transparent methods, tested on past data. Pick any date to see "
                      "what NEXUS would have forecast then, next to what actually happened.")
    predictive.show()


def recommendations_page():
    shell.page_header("Recommendations",
                      "Each suggestion comes from an explicit rule applied to the findings on "
                      "the other pages, and shows the numbers behind it.")
    recommend.show()


def campus_page():
    shell.page_header("Campus Map",
                      "IIIT-Delhi's real buildings in 3D, coloured by what NEXUS found in the "
                      "week chosen at the top. Switch layers on the map; drag to rotate, pinch "
                      "to zoom.")
    if not common.dataset().has_map:
        st.info("The 3D map is available for IIIT-Delhi. An uploaded college would also need "
                "its building outlines; switch College at the top to IIIT-Delhi to see the map.")
        return
    if not campus_map.outlines_ready():
        st.info("Building outlines are not downloaded yet. In the codespace, run "
                "`python scripts/fetch_campus.py`, then commit the `data/campus` folder.")
        return
    week_end = pd.Timestamp(shell.week_end())
    df, _ = common.load()
    status = campus_map.week_status(week_end, df, common.occupancy())
    buildings, outline = campus_map.load_outlines()
    replay = campus_map.timeline(week_end, df, common.occupancy())
    picked = campus_map.render(campus_map.payload(buildings, outline, status,
                                                  f"Week ending {week_end:%a %-d %b %Y}", replay))
    st.caption("Press ▶ on the map to replay the 12 weeks to the chosen date, one day at a time, "
               "or drag the slider to any day. Colours follow the selected layer.")
    if picked and picked.picked:
        st.session_state["campus_picked"] = picked.picked
    campus_map.details(status, st.session_state.get("campus_picked"))
    campus_map.status_table(status)
    campus_map.matching_notes(status)


def data_page():
    ds = common.dataset()
    if ds.name == common.IIITD:
        st.markdown(Path("DATA.md").read_text())
        return
    shell.page_header("Data & method", ds.source)
    if ds.name == upload.SAMPLE_NAME:
        st.markdown(Path("data/samples/README.md").read_text())
    for note in ds.notes:
        st.info(note)
    st.subheader("Import checks")
    upload.report_view(common.uploads()[ds.name]["report"])
    st.markdown("The analyses use the same methods as for IIIT-Delhi; see the README and "
                "the IIIT-Delhi Data & method page for details.")


def ask_page():
    shell.page_header("Ask NEXUS",
                      "Questions about the selected college and week, answered from the numbers "
                      "on the other pages.")
    ask.show(pd.Timestamp(shell.week_end()))


def reports_page():
    shell.page_header("Reports", "Download the chosen week as a report you can print or share, "
                      "and the full tables behind it.")
    more.reports(pd.Timestamp(shell.week_end()))


def settings_page():
    shell.page_header("Settings", "Your tariff and carbon factor, and the thresholds behind every "
                      "finding.")
    more.settings()


def help_page():
    shell.page_header("Help", "Plain answers to the questions people ask most.")
    more.help_page()


def upload_page():
    shell.page_header("Add college data",
                      "Run the same analyses on another college: upload its meter readings, "
                      "see every check, then use every page with that college selected.")
    upload.show()


PAGES = {
    "overview": st.Page(overview_page, title="Overview", icon=":material/space_dashboard:",
                        url_path="overview", default=True),
    "resource": st.Page(resource_page, title="Resource Intelligence", icon=":material/bolt:",
                        url_path="resource"),
    "institutional": st.Page(institutional_page, title="Institutional Intelligence",
                             icon=":material/groups:", url_path="institutional"),
    "predictive": st.Page(predictive_page, title="Predictive Intelligence",
                          icon=":material/trending_up:", url_path="predictive"),
    "recommendations": st.Page(recommendations_page, title="Recommendations",
                               icon=":material/checklist:", url_path="recommendations"),
    "campus": st.Page(campus_page, title="Campus Map", icon=":material/map:", url_path="campus"),
    "data": st.Page(data_page, title="Data & method", icon=":material/description:",
                    url_path="data"),
    "upload": st.Page(upload_page, title="Add college data", icon=":material/upload_file:",
                      url_path="add-college"),
    "ask": st.Page(ask_page, title="Ask NEXUS", icon=":material/forum:", url_path="ask"),
    "reports": st.Page(reports_page, title="Reports", icon=":material/summarize:", url_path="reports"),
    "settings": st.Page(settings_page, title="Settings", icon=":material/settings:", url_path="settings"),
    "help": st.Page(help_page, title="Help", icon=":material/help:", url_path="help"),
}

page = st.navigation({
    "Intelligence": [PAGES[k] for k in ["overview", "resource", "institutional", "predictive",
                                        "recommendations", "campus", "reports"]],
    "Assistant": [PAGES["ask"]],
    "Data": [PAGES["upload"], PAGES["data"]],
    "More": [PAGES["settings"], PAGES["help"]],
})

# A search result was picked: go to its page (state was set by the button callback).
goto = st.session_state.pop("_goto", None)
if goto:
    st.switch_page(PAGES[goto])

with st.sidebar:
    st.caption("Demo data: I-BLEND, IIIT-Delhi (CC0). Public data, not PES data.")

shell.top_bar()
page.run()
