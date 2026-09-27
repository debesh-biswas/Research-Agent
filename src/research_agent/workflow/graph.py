"""The graph itself: nodes wired together with the conditional routes the TRD requires.

The routing predicates are pure functions of state, so every branch — empty week, the single
broadening pass, and the abstract-only path around parsing — is testable without a model, a network
or a database.
"""

from datetime import date

from langgraph.graph import END, StateGraph

from research_agent.workflow import nodes
from research_agent.workflow.services import WorkflowServices
from research_agent.workflow.state import ResearchState

_NODES = (
    ("load_topic", nodes.load_topic),
    ("plan_queries", nodes.plan_queries),
    ("discover", nodes.discover),
    ("broaden", nodes.broaden_queries),
    ("classify", nodes.classify),
    ("select", nodes.select_papers),
    ("acquire", nodes.acquire),
    ("parse", nodes.parse),
    ("analyze", nodes.analyze),
    ("synthesize", nodes.synthesize),
    ("ideate", nodes.ideate),
    ("report", nodes.report),
    ("persist", nodes.persist),
)


def after_discovery(state: ResearchState) -> str:
    """Empty discovery broadens exactly once, then reports an empty week rather than looping."""
    if state.candidates:
        return "classify"
    return "report" if state.broadened else "broaden"


def after_selection(state: ResearchState) -> str:
    """Nothing selected is an empty week for reporting purposes; there is nothing to read."""
    return "acquire" if state.selected_ids else "report"


def after_acquisition(state: ResearchState) -> str:
    """With no PDF at all there is nothing to parse, so analysis runs abstract-only."""
    return "parse" if state.pdf_paths else "analyze"


def after_analysis(state: ResearchState) -> str:
    """Synthesis needs at least one analysis; without one the report is still produced."""
    return "synthesize" if state.analyzed_ids else "report"


def after_synthesis(state: ResearchState) -> str:
    return "ideate" if state.synthesized else "report"


def build_graph(services: WorkflowServices) -> object:
    """Compile the weekly research graph for one topic's services."""
    graph = StateGraph(ResearchState)
    for name, factory in _NODES:
        graph.add_node(name, factory(services))

    graph.set_entry_point("load_topic")
    graph.add_edge("load_topic", "plan_queries")
    graph.add_edge("plan_queries", "discover")
    graph.add_conditional_edges(
        "discover",
        after_discovery,
        {"classify": "classify", "broaden": "broaden", "report": "report"},
    )
    graph.add_edge("broaden", "discover")
    graph.add_edge("classify", "select")
    graph.add_conditional_edges(
        "select", after_selection, {"acquire": "acquire", "report": "report"}
    )
    graph.add_conditional_edges(
        "acquire", after_acquisition, {"parse": "parse", "analyze": "analyze"}
    )
    graph.add_edge("parse", "analyze")
    graph.add_conditional_edges(
        "analyze", after_analysis, {"synthesize": "synthesize", "report": "report"}
    )
    graph.add_conditional_edges(
        "synthesize", after_synthesis, {"ideate": "ideate", "report": "report"}
    )
    graph.add_edge("ideate", "report")
    graph.add_edge("report", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


async def run_workflow(
    services: WorkflowServices, period_start: date, period_end: date
) -> ResearchState:
    """Execute one complete run and return its final validated state."""
    compiled = build_graph(services)
    initial = ResearchState(
        topic_id=services.topic.id, period_start=period_start, period_end=period_end
    )
    final = await compiled.ainvoke(initial)  # type: ignore[attr-defined]
    return ResearchState.model_validate(final)
