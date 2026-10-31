"""Ask NEXUS: a conversation with Claude that looks numbers up in NEXUS's own tables, plus
fixed-rule quick answers that need no API key."""
import os

import pandas as pd
import streamlit as st

from nexus import ask, chat, insights
from nexus.kpis import headline
from nexus.predictive import next_forecasts
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
        share = st.session_state.get(f"share_{i}", round(common.reduction() * 100)) / 100
        return ask.savings(summary, share, st.session_state.get("tariff"),
                           st.session_state.get("emission_factor"), common.dataset().has_calendar)
    if key == "underused":
        return ask.underused(summary, common.dataset().has_calendar)


def quick_answers(week_end):
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
                st.slider("If near-empty use were lower by (%)", 5, 50, round(common.reduction() * 100), 5,
                          key=f"share_{i}", help="A scenario you choose, not a forecast of savings. "
                          "Starts at the cut set in Settings.")
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


# ------------------------------------------------------------------ the conversation

MAX_QUESTIONS = 30   # per session, so a public link cannot run up the API bill
SUGGESTED = ["Which building needs attention this week?", "How is electricity trending?",
             "What does the next two weeks look like?", "Where could this college save energy?",
             "How does NEXUS decide an hour is unusual?"]


def _secret(name):
    try:
        value = st.secrets.get(name)
    except Exception:   # no secrets file at all
        value = None
    return value or os.environ.get(name)


def provider():
    """('gemini' | 'anthropic', key, model) from the app's secrets, or None. Gemini is preferred (free tier)."""
    if _secret("GEMINI_API_KEY"):
        return "gemini", _secret("GEMINI_API_KEY"), _secret("GEMINI_MODEL") or chat.GEMINI_MODEL
    if _secret("ANTHROPIC_API_KEY"):
        return "anthropic", _secret("ANTHROPIC_API_KEY"), _secret("ANTHROPIC_MODEL") or chat.DEFAULT_MODEL
    return None


def context(week_end):
    """What the language model may look up for this college and week (used by chat and the AI summary)."""
    ds = common.dataset()
    df, events = common.load()
    week_end = pd.Timestamp(week_end)

    def overview():
        return {"college": ds.name, "source": ds.source,
                "data_from": ds.first, "data_to": ds.last,
                "buildings": sorted(df["building"].unique()),
                "unreliable_energy_meters": ds.warnings,
                "has_wifi_occupancy": ds.occupancy is not None,
                "has_academic_calendar": ds.has_calendar, "notes": ds.notes}

    def snapshot():
        snap = common.week(week_end)
        h = headline(snap)
        keep = lambda c: {k: c[k] for k in ("this", "prev", "change", "coverage")}   # noqa: E731
        return {"week_ending": week_end, "headline": h["main"], "details": h["details"],
                "electricity_kwh": keep(snap["energy"]), "wifi_activity": keep(snap["wifi"]),
                "avg_people_on_wifi_and_share_of_hours_used": snap["wifi_avg"],
                "higher_than_usual_events_this_week": snap["events"],
                "events_week_before": snap["events_prev"],
                "share_of_building_hours_missing": snap["missing"]}

    def forecasts():
        daily, types, ev = common.predictive()
        return next_forecasts(daily, types, ev)

    def recs():
        r = common.recommendations()
        keep = ("rule", "title", "building", "finding", "next_step", "at_stake_kwh", "at_stake_what", "worth_kind")
        return r[[c for c in keep if c in r.columns]]

    return chat.Context(
        college=ds.name, source=ds.source, week_end=week_end, first=ds.first, last=ds.last,
        overview=overview, snapshot=snapshot, building_week=lambda: insights.building_week(df, week_end),
        events=lambda: events, summary=lambda: common.institutional()[1], forecasts=forecasts,
        recommendations=recs, tariff=st.session_state.get("tariff"),
        factor=st.session_state.get("emission_factor"), reduction=common.reduction())


def stream(setup, history, ctx):
    """The model's answer as text chunks, from Gemini or Anthropic, running lookups as it asks."""
    kind, key, model = setup
    if kind == "gemini":
        import requests
        return chat.reply_gemini(requests.post, key, model, history, ctx)
    import anthropic
    client = anthropic.Anthropic(api_key=key, timeout=60, max_retries=1)
    return chat.reply(client, model, history, ctx)


def provider_name(setup):
    return {"gemini": "Google Gemini", "anthropic": "Claude"}[setup[0]] + f" ({setup[2]})"


def _chat_log():
    return st.session_state.setdefault("chat", {}).setdefault(common.college(), [])


def conversation(week_end):
    setup = provider()
    if not setup:
        st.info(
            "**The conversation needs an API key.** Add a free Gemini key once in the app's secrets "
            "as `GEMINI_API_KEY` (Streamlit Cloud: Manage app, Settings, Secrets), or an Anthropic "
            "key as `ANTHROPIC_API_KEY`. Until then, the **Quick answers** tab works without one.",
            icon=":material/key:")
        return
    log = _chat_log()
    asked = sum(m["role"] == "user" for m in log)
    if not log:
        st.caption("Ask anything. Questions about this college are answered from NEXUS's numbers; "
                   "NEXUS shows which lookups it used.")
        picked = st.pills("Try asking", SUGGESTED, key="chat_pick")
    else:
        picked = None
    thread = st.container()          # the whole conversation lives here, above the input box
    with thread:
        for m in log:
            _bubble(m["role"], m["content"], m.get("used"))
    prompt = st.chat_input("Ask NEXUS anything", key="chat_text") or picked
    if log:
        st.button("New conversation", type="tertiary", on_click=lambda: log.clear())
    if not prompt:
        return
    if asked >= MAX_QUESTIONS:
        st.warning(f"This session has reached {MAX_QUESTIONS} questions. Reload the page to start again.")
        return
    log.append({"role": "user", "content": prompt})
    ctx = context(week_end)
    with thread:
        _bubble("user", prompt)
        with st.chat_message("assistant", avatar=":material/hub:"):
            try:
                text = st.write_stream(stream(setup, log, ctx))
            except Exception as e:   # key rejected, no credit, offline ...
                text = chat.friendly_error(e)
                st.error(text)
            if ctx.used:
                st.caption("Looked up: " + ", ".join(dict.fromkeys(ctx.used)).replace("_", " "))
    log.append({"role": "assistant", "content": text if isinstance(text, str) else str(text),
                "used": list(ctx.used)})


def _bubble(role, content, used=None):
    with st.chat_message(role, avatar=":material/person:" if role == "user" else ":material/hub:"):
        st.markdown(content)
        if used:
            st.caption("Looked up: " + ", ".join(dict.fromkeys(used)).replace("_", " "))


def show(week_end):
    tab_chat, tab_quick = st.tabs(["Conversation", "Quick answers (no AI)"])
    with tab_chat:
        conversation(week_end)
    with tab_quick:
        quick_answers(week_end)
