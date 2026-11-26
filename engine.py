"""Synthetic vendor onboarding with policy retrieval and a LangGraph review gate."""
import re
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

POLICIES = {
    "POL-01": ("insurance certificate expired missing coverage",
               "An insurance certificate must be current and present."),
    "POL-02": ("tax form w9 missing documentation taxpayer",
               "A W-9 tax form must be on file."),
    "POL-03": ("security questionnaire incomplete missing assessment",
               "A completed security questionnaire must be on file."),
}
CASES = {
    "V001": ("Current", True, True),
    "V002": ("Expired", True, True),
    "V003": ("Missing", True, True),
    "V004": ("Current", False, True),
    "V005": ("Current", True, False),
    "V006": ("Expired", False, True),
    "V007": ("Expired", True, False),
    "V008": ("Current", False, False),
    "V009": ("Missing", False, False),
    "V010": ("Current", True, True),
}
EXPECTED = {
    "V001": (), "V002": ("POL-01",), "V003": ("POL-01",),
    "V004": ("POL-02",), "V005": ("POL-03",), "V006": ("POL-01", "POL-02"),
    "V007": ("POL-01", "POL-03"), "V008": ("POL-02", "POL-03"),
    "V009": ("POL-01", "POL-02", "POL-03"), "V010": (),
}


class State(TypedDict, total=False):
    vendor_id: str
    evidence: dict
    citations: list[str]
    gaps: list[str]
    route: str
    outcome: str
    trace: list[str]


def lookup_vendor(vendor_id):
    insurance, tax_form, security = CASES[vendor_id]
    return {"Insurance": insurance, "W-9 on file": tax_form,
            "Security questionnaire complete": security}


def retrieve(query):
    terms = set(re.findall(r"\w+", query.lower()))
    return max(POLICIES, key=lambda key: len(terms & set(POLICIES[key][0].split())))


def lookup(state):
    return {"evidence": lookup_vendor(state["vendor_id"]),
            "trace": ["Retrieved synthetic vendor record"]}


def assess(state):
    evidence = state["evidence"]
    checks = [
        ("insurance certificate coverage", evidence["Insurance"] != "Current",
         f"Insurance certificate is {evidence['Insurance'].lower()}"),
        ("tax form w9 taxpayer", not evidence["W-9 on file"], "W-9 is missing"),
        ("security questionnaire assessment", not evidence["Security questionnaire complete"],
         "Security questionnaire is incomplete"),
    ]
    gaps = [detail for _, failed, detail in checks if failed]
    return {"gaps": gaps, "citations": [retrieve(query) for query, _, _ in checks],
            "route": "Human review" if gaps else "Ready for onboarding review",
            "trace": state["trace"] + ["Retrieved three requirements and checked vendor evidence"]}


def review(state):
    verdict = interrupt({"vendor_id": state["vendor_id"], "gaps": state["gaps"]})
    if verdict not in {"Request updated documents", "Decline submission"}:
        raise ValueError("Choose a supported reviewer decision.")
    return {"outcome": verdict, "trace": state["trace"] + ["Recorded reviewer decision"]}


def build_graph():
    flow = StateGraph(State)
    flow.add_node("lookup", lookup)
    flow.add_node("assess", assess)
    flow.add_node("review", review)
    flow.add_edge(START, "lookup")
    flow.add_edge("lookup", "assess")
    flow.add_conditional_edges("assess", lambda state: "review" if state["gaps"] else END,
                               {"review": "review", END: END})
    flow.add_edge("review", END)
    return flow.compile(checkpointer=InMemorySaver())


def evaluate():
    graph = build_graph()
    results = []
    for vendor_id, expected in EXPECTED.items():
        config = {"configurable": {"thread_id": vendor_id}}
        result = graph.invoke({"vendor_id": vendor_id}, config)
        gap_policies = tuple(result["citations"][index] for index, gap in enumerate((
            result["evidence"]["Insurance"] != "Current",
            not result["evidence"]["W-9 on file"],
            not result["evidence"]["Security questionnaire complete"],
        )) if gap)
        results.append({
            "Vendor": vendor_id,
            "Expected": ", ".join(expected) or "No gaps",
            "Citations correct": gap_policies == expected
            and result["citations"] == ["POL-01", "POL-02", "POL-03"],
            "Route correct": (result["route"] == "Human review") == bool(expected),
            "Pause correct": bool(graph.get_state(config).next) == bool(expected),
        })
    return results
