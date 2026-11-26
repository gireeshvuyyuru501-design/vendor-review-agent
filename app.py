from uuid import uuid4

import streamlit as st
from langgraph.types import Command

from engine import CASES, POLICIES, build_graph, evaluate

st.set_page_config(page_title="Vendor Review Agent", layout="wide")
st.title("Vendor Onboarding Review Agent")
st.caption("Synthetic data · LangGraph · Local policy retrieval")
vendor = st.selectbox("Vendor submission", CASES, index=1)
if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
graph = st.session_state.graph
if st.button("Run review", type="primary"):
    st.session_state.vendor_config = {"configurable": {"thread_id": uuid4().hex}}
    graph.invoke({"vendor_id": vendor}, st.session_state.vendor_config)

if "vendor_config" in st.session_state:
    config = st.session_state.vendor_config
    snapshot = graph.get_state(config)
    state = snapshot.values
    st.subheader(f'{state["vendor_id"]} · {state["route"]}')
    evidence, policies = st.columns(2)
    with evidence:
        st.write("Vendor evidence")
        st.json(state["evidence"])
        for gap in state["gaps"]:
            st.write(f"• {gap}")
    with policies:
        st.write("Retrieved policies")
        for key in state["citations"]:
            st.write(f"**{key}** · {POLICIES[key][1]}")
        st.write("Workflow trace")
        st.write(" → ".join(state["trace"]))
    if snapshot.next:
        st.warning("Paused for human review.")
        action = st.selectbox("Reviewer decision", ["Request updated documents", "Decline submission"])
        if st.button("Record decision"):
            graph.invoke(Command(resume=action), config)
            st.rerun()
    elif "outcome" in state:
        st.success(f'Reviewer decision · {state["outcome"]}')

st.divider()
if st.button("Run 10-case evaluation"):
    st.session_state.evaluation = evaluate()
if "evaluation" in st.session_state:
    rows = st.session_state.evaluation
    st.write(f'{sum(all(row[key] for key in ("Citations correct", "Route correct", "Pause correct")) for row in rows)}/{len(rows)} cases passed')
    st.dataframe(rows, hide_index=True)
