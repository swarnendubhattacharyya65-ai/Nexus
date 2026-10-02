"""Ask NEXUS: suggested questions and typed questions, answered from NEXUS's own numbers."""
import streamlit as st

from nexus import ask, insights
from views import common


def _history():
    return st.session_state.setdefault("ask_history", {}).setdefault(common.college(), [])


def _ask(key, building=None, text=None):
    _history().append({"key": key, "building": building, "text": text})


def _picked():
    question = st.session_state.get("ask_pick")
    if question:
        key = {v: k for k, v in ask.QUESTIONS.items()}[question]
        _ask(key, None if key != "why" else st.session_state.get("ask_building"))
    st.session_state["ask_pick"] = None


def _typed():
    text = (st.session_state.get("ask_text") or "").strip()
    if text:
        df, _ = common.load()
        key, building = ask.route(text, sorted(df["building"].unique()))
        _ask(key, building, text)


def _answer(item, week_end, i):
    df, events = common.load()
    recs = common.recommendations()
    _, summary = common.institutional()
    key, building = item["key"], item["building"]
    if key is None:
        return ask.unknown(item["text"])
    if key == "attention":
        return ask.attention(df, events, recs, week_end)
    if key == "trend":
        return ask.trend(df, week_end)
    if key == "why":
        return ask.why(df, events, common.dataset().occupancy, recs, week_end, building)
    if key == "next":
        daily, types, evaluation = common.predictive()
        fc, skipped, change = common.compute(
            f"campus forecast {week_end:%Y-%m-%d}",
            lambda d: insights.campus_forecast(daily, types, evaluation, week_end))
        return ask.outlook(fc, skipped, change, week_end)
    if key == "save":
        share = st.session_state.get(f"share_{i}", 20) / 100
        return ask.savings(summary, share, st.session_state.get("tariff"),
                           st.session_state.get("emission_factor"), common.dataset().has_calendar)
    if key == "underused":
        return ask.underused(summary, common.dataset().has_calendar)


def show(week_end):
    st.info("Ask NEXUS answers from the numbers on the other pages, using fixed rules. It does "
            "not use a language model and it does not guess causes.", icon=":material/info:")

    st.pills("Suggested questions", list(ask.QUESTIONS.values()), key="ask_pick", on_change=_picked)
    df, _ = common.load()
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    building = c1.selectbox("Ask about one building", sorted(df["building"].unique()), key="ask_building")
    c2.button("Why is it using more?", on_click=_ask, args=("why", building))

    history = _history()
    for i, item in enumerate(history):
        with st.chat_message("user"):
            st.markdown(item["text"] or (ask.QUESTIONS[item["key"]] if item["key"] != "why"
                                         else f"Why is {item['building']} using more energy?"))
        with st.chat_message("assistant", avatar=":material/hub:"):
            if item["key"] == "save":
                st.slider("If near-empty use were lower by (%)", 5, 50, 20, 5, key=f"share_{i}",
                          help="A scenario you choose, not a forecast of savings.")
            a = _answer(item, week_end, i)
            st.markdown(a.text)
            if a.table is not None and not a.table.empty:
                st.dataframe(a.table, hide_index=True)
            if a.how:
                with st.expander("How NEXUS worked this out"):
                    st.markdown(a.how)
                    if a.pages:
                        st.caption("See also: " + ", ".join(a.pages) + ".")
    if history:
        st.button("Clear the conversation", type="tertiary",
                  on_click=lambda: st.session_state["ask_history"].pop(common.college(), None))
    st.chat_input("Ask about this college's energy and buildings", key="ask_text", on_submit=_typed)
