from langgraph.graph import END, START, StateGraph

from apps.graph.nodes import (
    fallback,
    generate_answer,
    grade_documents,
    groundedness_check,
    query_analysis,
    query_rewrite,
    retrieve,
    route_after_grading,
)
from apps.graph.state import RAGState


def build_graph():
    """Construct the self-corrective LangGraph RAG workflow."""
    builder = StateGraph(RAGState)

    builder.add_node("query_analysis", query_analysis)
    builder.add_node("retrieval", retrieve)
    builder.add_node("document_grading", grade_documents)
    builder.add_node("query_rewrite", query_rewrite)
    builder.add_node("generation", generate_answer)
    builder.add_node("groundedness_check", groundedness_check)
    builder.add_node("fallback", fallback)

    
    builder.add_edge(START, "query_analysis")
    builder.add_edge("query_analysis", "retrieval")
    builder.add_edge("retrieval", "document_grading")

    builder.add_conditional_edges(
        "document_grading",
        route_after_grading,
        {
            "generate": "generation",
            "rewrite": "query_rewrite",
            "fallback": "fallback",
        },
    )

  
    builder.add_edge("query_rewrite", "retrieval")

  
    builder.add_edge("generation", "groundedness_check")
    builder.add_edge("groundedness_check", END)

    builder.add_edge("fallback", END)

    return builder.compile()


rag_graph = build_graph()
