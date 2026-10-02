"""Add college data: upload a CSV (or load the public sample) and see every check."""
from pathlib import Path

import pandas as pd
import streamlit as st

from nexus import importer
from views import common

SAMPLE = Path("data/samples/bdg2_fox_8_buildings.csv.gz")
SAMPLE_NAME = "Sample: BDG2 site Fox, USA"
SAMPLE_SOURCE = "Public sample: BDG2 site Fox, USA (CC BY-SA)."


def _add(name, raw, calendar=None, source=""):
    """Run the import; on success select the new college. Problems are kept for display."""
    try:
        ds, report = importer.build(name, raw, calendar, source)
    except importer.ImportProblem as e:
        st.session_state["import_result"] = {"name": name, "problem": str(e)}
        return
    except Exception as e:   # anything the checks did not foresee: say so, don't crash
        st.session_state["import_result"] = {
            "name": name, "problem": f"The file could not be read ({type(e).__name__}: {e}). "
                                     "Check it against the template and try again."}
        return
    common.uploads()[name] = {"dataset": ds, "report": report}
    st.session_state["import_result"] = {"name": name, "report": report}
    st.session_state["college"] = name
    from views.shell import _college_changed
    _college_changed()


def _load_sample():
    _add(SAMPLE_NAME, importer.read_csv(SAMPLE.read_bytes(), SAMPLE.name), source=SAMPLE_SOURCE)


def _upload():
    name = (st.session_state.get("up_name") or "").strip()
    energy = st.session_state.get("up_file")
    calendar = st.session_state.get("up_calendar")
    if not name or energy is None:
        st.session_state["import_result"] = {
            "name": name, "problem": "Give the college a name and choose an energy CSV file."}
        return
    if name in common.colleges():
        name = f"{name} ({len(common.colleges())})"
    try:
        raw = importer.read_csv(energy.getvalue(), energy.name)
        cal = importer.read_csv(calendar.getvalue(), calendar.name) if calendar else None
    except importer.ImportProblem as e:
        st.session_state["import_result"] = {"name": name, "problem": str(e)}
        return
    _add(name, raw, cal)


def _remove(name):
    common.uploads().pop(name, None)
    if st.session_state.get("college") == name:
        st.session_state["college"] = common.colleges()[0]
        from views.shell import _college_changed
        _college_changed()


def report_view(report):
    """Everything the import checked, in plain words."""
    rejected = sum(report["rejected"].values())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows read", f"{report['rows_read']:,}")
    c2.metric("Rows used", f"{report['rows_used']:,}")
    c3.metric("Rows set aside", f"{rejected:,}")
    c4.metric("Buildings", len(report["buildings"]))
    start, end = report["period"]
    st.caption(f"Energy column read as {report['unit']}. Period {start:%d %b %Y} to {end:%d %b %Y}. "
               "An hour counts only if at least 75% of its readings are present, and is then "
               "scaled to the full hour; hours with fewer are left blank.")
    if report["rejected"]:
        st.dataframe(pd.DataFrame(list(report["rejected"].items()),
                                  columns=["Why a row was set aside", "Rows"]), hide_index=True)
    for w in report["warnings"]:
        st.warning(w, icon=":material/info:")
    st.dataframe(pd.DataFrame(report["buildings"]).rename(columns={
        "building": "Building", "first": "First reading", "last": "Last reading",
        "reading_every_min": "Reading every (min)", "hours_with_energy": "Hours with energy",
        "hours_recorded_pct": "Hours recorded %", "zero_hours_pct": "Hours reading 0 %"}),
        hide_index=True)


def show():
    st.markdown("Run NEXUS on another college's meter data. Uploaded files are sent to the NEXUS "
                "server and kept in its memory for your session only: they are not written to "
                "disk or shown to other visitors, and reloading the page clears them.")

    # ------------------------------------------------------------ sample
    st.subheader("Try it with a public sample")
    st.markdown("Eight buildings (teaching labs, dormitories, dining, office, fitness centre) "
                "from site Fox of the Building Data Genome Project 2: real hourly electricity "
                "from a university campus in the United States, 2016-2017. Site and building "
                "names are anonymised in the source.")
    st.button("Load the sample college", icon=":material/school:", on_click=_load_sample,
              disabled=SAMPLE_NAME in common.colleges())

    # ------------------------------------------------------------ upload
    st.subheader("Upload a college's data")
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.form("upload"):
            st.text_input("College name", key="up_name", placeholder="e.g. PES University, RR campus")
            st.file_uploader("Energy readings (CSV, or CSV.GZ)", type=["csv", "gz"], key="up_file")
            st.file_uploader("Academic calendar (optional CSV)", type=["csv"], key="up_calendar")
            st.form_submit_button("Check and add college", type="primary", on_click=_upload)
    with right:
        st.markdown(
            "**Energy file columns**\n"
            "- `timestamp`: local date and time, e.g. 2024-01-08 09:00\n"
            "- `building`: building name\n"
            "- one of `kwh` (kWh used in that interval), `kw` (average kW) or `w` (watts)\n"
            "- `people` (optional): people or Wi-Fi devices counted\n\n"
            "Readings every hour or more often. **Calendar columns:** `date`, "
            "`working_day` (1/0), `activity` (high/low, optional).")
        d1, d2 = st.columns(2)
        d1.download_button("Energy template", importer.TEMPLATE, "nexus_energy_template.csv",
                           "text/csv", icon=":material/download:")
        d2.download_button("Calendar template", importer.CALENDAR_TEMPLATE,
                           "nexus_calendar_template.csv", "text/csv", icon=":material/download:")
        st.caption("The template rows are format examples, not real readings.")

    # ------------------------------------------------------------ result
    result = st.session_state.get("import_result")
    if result:
        st.subheader(f"Checks for {result['name'] or 'the upload'}")
        if "problem" in result:
            st.error(f"**Not added.** {result['problem']}")
        else:
            st.success(f"**{result['name']} added and selected.** Every page now shows this "
                       "college. Switch back with the College menu at the top.",
                       icon=":material/check_circle:")
            report_view(result["report"])

    loaded = list(common.uploads())
    if loaded:
        st.subheader("Colleges added in this session")
        for name in loaded:
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"**{name}**: {common.uploads()[name]['dataset'].source}")
            c2.button("Remove", key=f"rm_{name}", on_click=_remove, args=(name,))
