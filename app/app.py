"""
QueryMind — Streamlit UI
Run: streamlit run app.py
"""

import asyncio
import json
import uuid
import streamlit as st
import pandas as pd
import plotly.express as px

from agents import run_query

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="QueryMind",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.thinking-box {
    background: #0f1117;
    border: 1px solid #2d2d3a;
    border-radius: 8px;
    padding: 12px 16px;
    font-family: monospace;
    font-size: 12px;
    color: #a0f0a0;
    max-height: 360px;
    overflow-y: auto;
    margin-bottom: 8px;
}
.agent-label {
    color: #7eb8f7;
    font-weight: bold;
}
.key-finding {
    background: linear-gradient(90deg, #1a1a2e, #16213e);
    border-left: 4px solid #4f8ef7;
    border-radius: 4px;
    padding: 14px 18px;
    font-size: 18px;
    font-weight: 600;
    color: #e0e8ff;
    margin-bottom: 16px;
}
.stButton > button {
    background: #4f8ef7;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 28px;
    font-size: 15px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://fonts.gstatic.com/s/i/productlogos/gemini_sparkle/v1/192px.svg", width=40)
    st.title("QueryMind")
    st.caption("Natural language analyst · Medicare data · Powered by Google ADK + Gemini 2.5 Flash")

    st.divider()
    st.subheader("Example queries")
    examples = [
        "Which states had the highest average Medicare payment per beneficiary?",
        "What are the top 10 procedures by total payment amount?",
        "Show me inpatient discharge volume by state.",
        "Which providers had the most unique beneficiaries?",
        "Compare average submitted charges vs Medicare payments by specialty.",
    ]
    for ex in examples:
        if st.button(ex, key=ex, use_container_width=True):
            st.session_state["prefill"] = ex
            st.rerun()

    st.divider()
    st.caption("Track B · Quantitative Forge · Gemini Nexus Boss Raid 2026")

# ── Main UI ───────────────────────────────────────────────────────────────────

st.markdown("## 🔍 QueryMind")
st.markdown("Ask any question about Medicare public data. The agent swarm writes the SQL, recovers from errors, and explains the results.")

prefill = st.session_state.pop("prefill", "")
with st.form("query_form", clear_on_submit=False):
    question = st.text_input(
        "Your question",
        value=prefill,
        placeholder="e.g. Which states had the highest average Medicare payment per beneficiary?",
        label_visibility="collapsed",
    )
    run_btn = st.form_submit_button("Run query →")

# ── Session history ───────────────────────────────────────────────────────────

if "history" not in st.session_state:
    st.session_state["history"] = []

# ── Query execution ───────────────────────────────────────────────────────────

if run_btn and question.strip():
    session_id = str(uuid.uuid4())

    col_main, col_log = st.columns([3, 2])

    with col_log:
        st.markdown("#### 🧠 Agent thinking log")
        log_placeholder = st.empty()

    with col_main:
        st.markdown("#### 📊 Results")
        result_placeholder = st.empty()

    with st.spinner("Agents thinking…"):
        result = asyncio.run(run_query(question, session_id=session_id))

    # ── Thinking log ──────────────────────────────────────────────────────────
    with col_log:
        log_html = '<div class="thinking-box">'
        for step in result.get("thinking_log", []):
            agent = step.get("agent", "agent")
            text = step.get("step", "").replace("<", "&lt;").replace(">", "&gt;")
            log_html += f'<div><span class="agent-label">[{agent}]</span> {text}</div><br/>'
        if not result.get("thinking_log"):
            log_html += '<div style="color:#666">No thinking steps captured.</div>'
        log_html += "</div>"
        log_placeholder.markdown(log_html, unsafe_allow_html=True)

    # ── Results panel ─────────────────────────────────────────────────────────
    with col_main:
        key_finding = result.get("key_finding", "")
        if key_finding:
            st.markdown(f'<div class="key-finding">💡 {key_finding}</div>', unsafe_allow_html=True)

        summary = result.get("summary", "")
        if summary:
            st.markdown(summary)

        chart = result.get("chart", {})
        data = chart.get("data", [])

        if data:
            df = pd.DataFrame(data)
            chart_type = chart.get("type", "table")
            title = chart.get("title", question)
            x = chart.get("x_field", df.columns[0] if len(df.columns) > 0 else None)
            y = chart.get("y_field", df.columns[1] if len(df.columns) > 1 else None)

            try:
                if chart_type == "bar" and x and y:
                    fig = px.bar(df, x=x, y=y, title=title, color_discrete_sequence=["#4f8ef7"])
                    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "line" and x and y:
                    fig = px.line(df, x=x, y=y, title=title, markers=True)
                    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig, use_container_width=True)
                elif chart_type == "pie" and x and y:
                    fig = px.pie(df, names=x, values=y, title=title)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.dataframe(df, use_container_width=True)
                st.caption(f"Chart render note: {e}")
        elif result.get("raw_output"):
            st.text_area("Raw output", result["raw_output"], height=200)

    st.session_state["history"].append({"question": question, "result": result})

elif run_btn:
    st.warning("Please enter a question first.")

# ── History ───────────────────────────────────────────────────────────────────

if st.session_state["history"]:
    st.divider()
    st.markdown("#### Previous queries this session")
    for i, item in enumerate(reversed(st.session_state["history"][-5:])):
        with st.expander(f"Q: {item['question'][:80]}…"):
            st.write(item["result"].get("summary", item["result"].get("raw_output", "")))
