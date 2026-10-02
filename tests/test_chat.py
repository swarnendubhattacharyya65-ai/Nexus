"""Offline test of the chat loop with a fake model (run: python tests/test_chat.py)."""
import json
import sys
from types import SimpleNamespace as NS

import pandas as pd

sys.path.insert(0, ".")
from nexus import chat


class FakeStream:
    def __init__(self, blocks, stop, texts):
        self.final = NS(content=blocks, stop_reason=stop)
        self.text_stream = iter(texts)
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_final_message(self): return self.final


def fake_client(script, seen):
    def stream(**kw):
        seen.append(kw)
        return script.pop(0)
    return NS(messages=NS(stream=stream))


def ctx():
    bw = pd.DataFrame({"Building": ["Library", "Dining"], "kWh this week": [1200.4, float("nan")]})
    return chat.Context(
        college="Test College", source="Public data. Not PES data.", week_end=pd.Timestamp("2023-03-12"),
        first=pd.Timestamp("2023-01-02"), last=pd.Timestamp("2023-03-12"),
        overview=lambda: {"buildings": ["Library", "Dining"]}, snapshot=lambda: {"headline": "x"},
        building_week=lambda: bw, events=lambda: pd.DataFrame(), summary=lambda: None,
        forecasts=lambda: pd.DataFrame(), recommendations=lambda: pd.DataFrame(), tariff=8.0)


seen = []
tool = NS(type="tool_use", id="t1", name="building_week", input={})
script = [FakeStream([NS(type="text", text="Let me look."), tool], "tool_use", ["Let me look."]),
          FakeStream([NS(type="text", text="Library used 1,200 kWh.")], "end_turn", ["Library used ", "1,200 kWh."])]
c = ctx()
out = "".join(chat.reply(fake_client(script, seen), "m", [{"role": "user", "content": "hi"}], c))
assert out == "Let me look.\n\nLibrary used 1,200 kWh.", out
assert c.used == ["building_week"]
# the tool result went back to the model, NaN as null
last = seen[1]["messages"][-1]["content"][0]
assert last["type"] == "tool_result" and last["tool_use_id"] == "t1"
rows = json.loads(last["content"])["rows"]
assert rows[0]["kWh this week"] == 1200.4 and rows[1]["kWh this week"] is None
assert "Test College" in seen[0]["system"] and "Not PES data" in seen[0]["system"]

# money only from the person's own tariff
r = json.loads(chat.run_tool("convert_kwh", {"kwh": 100}, ctx()))
assert r["rupees"] == 800.0 and r["co2_kg"] is None
r = json.loads(chat.run_tool("convert_kwh", {"kwh": 100}, chat.Context(**{**ctx().__dict__, "tariff": None})))
assert r["rupees"] is None and "not entered" in r["note"]

# unknown tool and a failing lookup are reported, not raised
assert "unknown tool" in chat.run_tool("nope", {}, ctx())
bad = ctx(); bad.overview = lambda: 1 / 0
assert "ZeroDivisionError" in chat.run_tool("college_overview", {}, bad)

# an endless tool loop stops
loop = [FakeStream([tool], "tool_use", []) for _ in range(chat.MAX_ROUNDS)]
assert "stopped after several lookups" in "".join(chat.reply(fake_client(loop, []), "m", [{"role": "user", "content": "x"}], ctx()))

# history starts with a user message and is capped
h = [{"role": "assistant", "content": "a"}] + [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(40)]
t = chat.trim(h)
assert t[0]["role"] == "user" and len(t) <= chat.HISTORY_TURNS
print("chat tests passed")
