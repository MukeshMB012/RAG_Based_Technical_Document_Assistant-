from typing import Any, TypedDict


class RAGState(TypedDict, total=False):
    """Execution state schema tracked throughout the LangGraph RAG pipeline."""

    # User input
    question: str
    search_query: str

    # Retrieval and grading
    retrieved_documents: list[dict[str, Any]]
    relevant_documents: list[dict[str, Any]]
    document_grades: list[dict[str, Any]]
    is_relevant: bool
    grade_feedback: str

    # Iteration & retry management
    retry_count: int
    max_retries: int
    rewritten_queries: list[str]

    # Generation & citations
    answer: str
    sources: list[dict[str, str]]
    fallback_used: bool

    # Full audit trace for UI visualization
    execution_trace: list[dict[str, Any]]
