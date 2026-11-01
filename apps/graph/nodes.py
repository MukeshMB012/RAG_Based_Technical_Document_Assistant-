import json
import logging
from typing import Any

from apps.graph.schemas import (
    DocumentGradingOutput,
    GroundednessCheckOutput,
    QueryRewriteOutput,
)
from apps.graph.state import RAGState
from apps.ingestion.vectorstore import search_documents
from apps.llm.client import generate_structured, generate_text, get_active_model_name

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = (
    "I don't know based on the available documentation. "
    "The indexed documentation does not contain sufficient "
    "information to answer this question."
)


def _append_trace(
    state: RAGState, step: str, status: str, data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Append a structured step entry to the execution trace."""
    trace = list(state.get("execution_trace", []))
    trace.append({"step": step, "status": status, "data": data})
    return trace


def query_analysis(state: RAGState) -> dict[str, Any]:
    """Validate and prepare the user question for initial retrieval."""
    raw_question = state.get("question", "")
    question = raw_question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    logger.info(f"[Query Analysis] question='{question}'")

    trace = _append_trace(
        state,
        "query_analysis",
        "completed",
        {
            "original_query": question,
            "search_query": question,
        },
    )

    return {
        "question": question,
        "search_query": question,
        "retry_count": 0,
        "max_retries": 2,
        "relevant_documents": [],
        "rewritten_queries": [],
        "sources": [],
        "answer": "",
        "fallback_used": False,
        "execution_trace": trace,
    }


def retrieve(state: RAGState) -> dict[str, Any]:
    """Retrieve candidate document chunks from ChromaDB for the active query."""
    query = state["search_query"]
    retry_count = state.get("retry_count", 0)

    logger.info(f"[Retrieval] query='{query}' (attempt {retry_count + 1})")

    documents = search_documents(query=query, top_k=5)

    retrieval_data = {
        "query": query,
        "documents_retrieved": len(documents),
        "attempt": retry_count + 1,
        "documents": [
            {
                "id": doc["id"],
                "source": doc["metadata"].get("source", ""),
                "title": doc["metadata"].get("title", ""),
                "distance": round(doc.get("distance", 0.0), 4),
                "content_preview": doc["content"][:250],
            }
            for doc in documents
        ],
    }

    trace = _append_trace(state, "retrieval", "completed", retrieval_data)

    return {
        "retrieved_documents": documents,
        "execution_trace": trace,
    }


def grade_documents(state: RAGState) -> dict[str, Any]:
    """Grade retrieved chunks with Gemini and filter out irrelevant content."""
    question = state["question"]
    documents = state.get("retrieved_documents", [])

    logger.info(f"[Document Grading] Grading {len(documents)} retrieved chunks.")

    if not documents:
        trace = _append_trace(
            state,
            "document_grading",
            "completed",
            {
                "grades": [],
                "relevant_count": 0,
                "total_count": 0,
            },
        )
        return {
            "relevant_documents": [],
            "document_grades": [],
            "is_relevant": False,
            "grade_feedback": "No documents were retrieved to grade.",
            "execution_trace": trace,
        }

    grading_payload = [
        {
            "document_id": doc["id"],
            "title": doc.get("metadata", {}).get("title", ""),
            "source": doc.get("metadata", {}).get("source", ""),
            "content": doc["content"],
        }
        for doc in documents
    ]

    prompt = f"""You are an expert technical documentation evaluator.
Evaluate whether each retrieved document chunk contains relevant information to answer the user question.

USER QUESTION:
{question}

RETRIEVED DOCUMENT CHUNKS:
{json.dumps(grading_payload, indent=2, ensure_ascii=False)}

EVALUATION RULES:
1. Grade each document independently by document_id.
2. Mark relevant=true if the chunk contains direct facts, code snippets, or useful context for answering the question.
3. Mark relevant=false if the chunk discusses an unrelated concept or does not assist in answering the question.
4. Return exactly one grade per document_id.
5. Provide a concise, clear reason for each decision.
"""

    grading_result = generate_structured(
        prompt=prompt,
        response_schema=DocumentGradingOutput,
        temperature=0.0,
    )

    grades_by_id = {grade.document_id: grade for grade in grading_result.grades}

    relevant_documents = []
    document_grades = []

    for doc in documents:
        doc_id = doc["id"]
        grade = grades_by_id.get(doc_id)
        relevant = grade.relevant if grade else False
        reason = grade.reason if grade else "No explicit grading response."

        document_grades.append({
            "document_id": doc_id,
            "source": doc["metadata"].get("source", ""),
            "title": doc["metadata"].get("title", ""),
            "relevant": relevant,
            "reason": reason,
        })

        if relevant:
            relevant_documents.append({**doc, "grade_reason": reason})

        logger.info(
            f"  [{'RELEVANT' if relevant else 'IRRELEVANT'}] {doc_id}: {reason}"
        )

    is_relevant = len(relevant_documents) > 0
    feedback = f"{len(relevant_documents)} of {len(documents)} chunks are relevant."

    trace = _append_trace(
        state,
        "document_grading",
        "completed",
        {
            "grades": document_grades,
            "relevant_count": len(relevant_documents),
            "total_count": len(documents),
        },
    )

    return {
        "relevant_documents": relevant_documents,
        "document_grades": document_grades,
        "is_relevant": is_relevant,
        "grade_feedback": feedback,
        "execution_trace": trace,
    }


def query_rewrite(state: RAGState) -> dict[str, Any]:
    """Rewrite a failed query using Gemini to target the indexed FastAPI corpus."""
    question = state["question"]
    current_query = state["search_query"]
    retry_count = state.get("retry_count", 0)
    rewritten_queries = list(state.get("rewritten_queries", []))

    logger.info(
        f"[Query Rewrite] original='{question}', failed='{current_query}', retry={retry_count + 1}"
    )

    prompt = f"""You are a search query optimizer for a FastAPI documentation assistant.
The previous search query failed to retrieve relevant documentation from the vector index.

ORIGINAL USER QUESTION:
{question}

FAILED SEARCH QUERY:
{current_query}

PREVIOUSLY ATTEMPTED QUERIES:
{json.dumps(rewritten_queries) if rewritten_queries else "None"}

AVAILABLE DOCUMENTATION TOPICS:
- FastAPI Request Body (Pydantic models, validation, Field, nested models)
- FastAPI Dependencies (Depends, dependency injection, sub-dependencies, yield)
- FastAPI Handling Errors (HTTPException, custom exception handlers, RequestValidationError)

INSTRUCTIONS:
1. Reformulate the query into a search query targeting FastAPI documentation.
2. If the user asked about an external technology (e.g. Django, Flask, AWS), identify the closest FastAPI equivalent topic or general FastAPI concepts.
3. Keep the rewritten query concise and keyword-focused.
4. Do not repeat any previously attempted queries.
"""

    result = generate_structured(
        prompt=prompt,
        response_schema=QueryRewriteOutput,
        temperature=0.2,
    )

    new_query = result.rewritten_query.strip()
    rewritten_queries.append(new_query)

    trace = _append_trace(
        state,
        "query_rewrite",
        "completed",
        {
            "original_query": question,
            "previous_query": current_query,
            "rewritten_query": new_query,
            "reasoning": result.reasoning,
            "retry_number": retry_count + 1,
        },
    )

    return {
        "search_query": new_query,
        "retry_count": retry_count + 1,
        "rewritten_queries": rewritten_queries,
        "execution_trace": trace,
    }


def generate_answer(state: RAGState) -> dict[str, Any]:
    """Generate a factual response grounded exclusively in the relevant documents."""
    question = state["question"]
    relevant_docs = state.get("relevant_documents", [])

    logger.info(
        f"[Generation] Generating response using {len(relevant_docs)} relevant chunks."
    )

    context_segments = []
    source_map: dict[str, dict[str, str]] = {}

    for doc in relevant_docs:
        context_segments.append(doc["content"])
        meta = doc.get("metadata", {})
        source_key = meta.get("source", "")
        if source_key and source_key not in source_map:
            source_map[source_key] = {
                "title": meta.get("title", source_key),
                "source": source_key,
                "url": meta.get("url", ""),
            }

    context = "\n\n---\n\n".join(context_segments)
    sources = list(source_map.values())

    prompt = f"""You are a technical documentation assistant.
Answer the user's question using ONLY the provided documentation context.

USER QUESTION:
{question}

DOCUMENTATION CONTEXT:
{context}

STRICT INSTRUCTIONS:
1. Answer accurately and stay strictly grounded in the context.
2. Provide code examples from the context where relevant.
3. If the context does not contain enough information to answer completely, clearly state what information is missing.
4. Do NOT speculate, hallucinate, or assume facts outside the context.
5. Keep your explanation structured, clear, and professional.
"""

    answer = generate_text(prompt=prompt, temperature=0.1, max_output_tokens=2048)

    trace = _append_trace(
        state,
        "generation",
        "completed",
        {
            "context_chunks_used": len(relevant_docs),
            "model": "Gemini 3.8 Flash",
            "sources": sources,
        },
    )

    return {
        "answer": answer,
        "sources": sources,
        "fallback_used": False,
        "execution_trace": trace,
    }


def groundedness_check(state: RAGState) -> dict[str, Any]:
    """Verify that the generated answer does not contain ungrounded hallucinations."""
    answer = state.get("answer", "")
    relevant_docs = state.get("relevant_documents", [])

    logger.info("[Groundedness Check] Evaluating answer against context.")

    context = "\n\n---\n\n".join(doc["content"] for doc in relevant_docs)

    prompt = f"""You are a strict fact-checking evaluator for a technical documentation system.
Verify whether every factual claim in the generated answer is directly supported by the context documents.

GENERATED ANSWER:
{answer}

CONTEXT DOCUMENTS:
{context}

EVALUATION CRITERIA:
1. All technical claims, parameters, and explanations must be supported by the context.
2. Code examples directly derived from context examples are considered grounded.
3. If the answer introduces external claims or unverifiable features, mark grounded=false.
"""

    result = generate_structured(
        prompt=prompt,
        response_schema=GroundednessCheckOutput,
        temperature=0.0,
    )

    trace = _append_trace(
        state,
        "groundedness_check",
        "completed",
        {
            "grounded": result.grounded,
            "reasoning": result.reasoning,
        },
    )

    if not result.grounded:
        logger.warning(f"Groundedness check flagged: {result.reasoning}")
        annotated_answer = (
            f"{answer}\n\n"
            f"> [!WARNING]\n"
            f"> **Groundedness Note**: Some elements of this answer may not be fully "
            f"supported by the indexed documentation."
        )
        return {
            "answer": annotated_answer,
            "execution_trace": trace,
        }

    return {"execution_trace": trace}


def fallback(state: RAGState) -> dict[str, Any]:
    """Produce the deterministic fallback response when retrieval retries are exhausted."""
    logger.info("[Fallback] Max retries exhausted without relevant documents.")

    trace = _append_trace(
        state,
        "fallback",
        "completed",
        {
            "reason": "Retry limit reached. No relevant documents found.",
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 2),
        },
    )

    return {
        "answer": FALLBACK_ANSWER,
        "sources": [],
        "fallback_used": True,
        "execution_trace": trace,
    }


def route_after_grading(state: RAGState) -> str:
    """Conditional routing function after document grading."""
    if state.get("is_relevant", False):
        return "generate"

    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    if retry_count < max_retries:
        return "rewrite"

    return "fallback"
