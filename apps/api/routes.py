import logging
import re
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.graph.workflow import rag_graph
from apps.ingestion.vectorstore import (
    collection,
    ingest_custom_document,
    ingest_documents,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="The question to submit to the RAG assistant",
        examples=["What does Depends do in FastAPI?"],
    )


class SourceInfo(BaseModel):
    title: str
    source: str
    url: str = ""


class ExecutionDetail(BaseModel):
    original_query: str = ""
    rewritten_queries: list[str] = []
    retrievals: list[dict[str, Any]] = []
    grading: list[dict[str, Any]] = []
    retry_count: int = 0
    generation_used: bool = False
    fallback_used: bool = False
    execution_trace: list[dict[str, Any]] = []


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceInfo] = []
    rewritten_query: Optional[str] = None
    retry_count: int = 0
    execution: ExecutionDetail


class IngestRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="Re-ingest default documentation from the docs/ directory",
    )
    url: Optional[str] = Field(
        default=None,
        description="Optional documentation URL to fetch and index",
    )
    text: Optional[str] = Field(
        default=None,
        description="Optional raw text or Markdown document to index directly",
    )
    title: Optional[str] = Field(
        default=None,
        description="Title for the custom document or URL",
    )
    source: Optional[str] = Field(
        default=None,
        description="Source identifier (filename or slug)",
    )


class IngestResponse(BaseModel):
    status: str
    documents_loaded: int
    chunks_created: int
    total_chunks_in_database: int


class DocumentInfo(BaseModel):
    title: str
    source: str
    url: str = ""
    chunk_count: int = 0


class DocumentsResponse(BaseModel):
    total_chunks: int
    documents: list[DocumentInfo]


class FeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5, description="Star rating from 1 to 5")
    feedback: str = Field(default="", description="Optional qualitative feedback")


class FeedbackResponse(BaseModel):
    status: str
    message: str


# In-memory storage for feedback
_feedback_store: list[dict[str, Any]] = []


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """Execute the complete self-corrective RAG pipeline for a user question."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = rag_graph.invoke({"question": question})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Pipeline runtime error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service temporarily unavailable: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Unexpected pipeline error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the question.",
        )

    rewritten_queries = result.get("rewritten_queries", [])
    raw_sources = result.get("sources", [])
    sources = [
        SourceInfo(
            title=s.get("title", ""),
            source=s.get("source", ""),
            url=s.get("url", ""),
        )
        for s in raw_sources
    ]

    trace = result.get("execution_trace", [])
    retrievals = [step["data"] for step in trace if step.get("step") == "retrieval"]
    grading = [step["data"] for step in trace if step.get("step") == "document_grading"]

    execution = ExecutionDetail(
        original_query=question,
        rewritten_queries=rewritten_queries,
        retrievals=retrievals,
        grading=grading,
        retry_count=result.get("retry_count", 0),
        generation_used=not result.get("fallback_used", False),
        fallback_used=result.get("fallback_used", False),
        execution_trace=trace,
    )

    return QueryResponse(
        question=question,
        answer=result.get("answer", ""),
        sources=sources,
        rewritten_query=(rewritten_queries[-1] if rewritten_queries else None),
        retry_count=result.get("retry_count", 0),
        execution=execution,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint(request: Request):
    """Ingest documents from docs/, an external URL, uploaded file, or provided raw text."""
    content_type = request.headers.get("content-type", "").lower()

    url: Optional[str] = None
    text: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            url = body.get("url")
            text = body.get("text")
            title = body.get("title")
            source = body.get("source")

    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse form data: {e}")

        url = form.get("url")
        text = form.get("text")
        title = form.get("title")
        source = form.get("source")

        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "read"):
            try:
                file_bytes = await file_obj.read()
                try:
                    text = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    text = file_bytes.decode("latin-1")

                filename = getattr(file_obj, "filename", "uploaded_doc.md") or "uploaded_doc.md"
                if not source:
                    source = filename
                if not title:
                    title_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
                    title = title_match.group(1).strip() if title_match else filename.rsplit(".", 1)[0]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {e}")
    else:
        try:
            body = await request.json()
            if isinstance(body, dict):
                url = body.get("url")
                text = body.get("text")
                title = body.get("title")
                source = body.get("source")
        except Exception:
            pass

    try:
        # Case 1: Fetch and index from an external URL
        if url:
            url_str = str(url).strip()
            if not url_str:
                raise HTTPException(status_code=400, detail="Provided URL is empty.")

            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(url_str)
                if res.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to fetch document from URL. HTTP status: {res.status_code}",
                    )
                raw_text = res.text

            title_match = re.search(r"^#\s+(.+)", raw_text, re.MULTILINE)
            extracted_title = title_match.group(1).strip() if title_match else url_str
            doc_title = title or extracted_title
            doc_source = source or url_str.split("/")[-1] or "url_document"

            stats = ingest_custom_document(
                content=raw_text,
                title=doc_title,
                source=doc_source,
                url=url_str,
            )

        # Case 2: Index provided raw text or uploaded file content
        elif text:
            raw_text = str(text).strip()
            if not raw_text:
                raise HTTPException(status_code=400, detail="Document content cannot be empty.")

            doc_title = title or "Custom Document"
            doc_source = source or "custom_document"

            stats = ingest_custom_document(
                content=raw_text,
                title=doc_title,
                source=doc_source,
            )

        # Case 3: Re-index the docs/ corpus
        else:
            stats = ingest_documents()

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ingestion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    return IngestResponse(
        status="success",
        documents_loaded=stats["documents_loaded"],
        chunks_created=stats["chunks_created"],
        total_chunks_in_database=stats["total_chunks_in_database"],
    )


@router.get("/documents", response_model=DocumentsResponse)
async def documents_endpoint():
    """List all indexed documents and chunk statistics."""
    try:
        total = collection.count()
        if total == 0:
            return DocumentsResponse(total_chunks=0, documents=[])

        all_results = collection.get(include=["metadatas"])
        doc_map: dict[str, DocumentInfo] = {}

        for metadata in all_results["metadatas"]:
            source = metadata.get("source", "unknown")
            if source not in doc_map:
                doc_map[source] = DocumentInfo(
                    title=metadata.get("title", source),
                    source=source,
                    url=metadata.get("url", ""),
                    chunk_count=0,
                )
            doc_map[source].chunk_count += 1

        return DocumentsResponse(
            total_chunks=total,
            documents=list(doc_map.values()),
        )
    except Exception as e:
        logger.error(f"Documents listing error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve indexed documents: {str(e)}"
        )


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(request: FeedbackRequest):
    """Store user evaluation feedback for generated answers."""
    entry = {
        "question": request.question,
        "answer": request.answer,
        "rating": request.rating,
        "feedback": request.feedback,
        "timestamp": datetime.now().isoformat(),
    }
    _feedback_store.append(entry)

    logger.info(
        f"Recorded feedback: rating={request.rating}, question='{request.question[:40]}...'"
    )

    return FeedbackResponse(
        status="success",
        message="Thank you for your feedback!",
    )
