import streamlit as st
import pandas as pd

st.title("NEXUS")
st.write("Day 0 smoke test: the app runs and deploys.")

df = pd.DataFrame({"hour": range(24), "value": [i % 6 for i in range(24)]})
st.line_chart(df, x="hour", y="value")
st.caption("Placeholder numbers for a deployment test, not real data.")
""