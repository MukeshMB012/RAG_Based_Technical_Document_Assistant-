from pydantic import BaseModel, Field


class DocumentGrade(BaseModel):
    """Grading evaluation for a single retrieved chunk."""

    document_id: str = Field(
        description="Exact ID of the retrieved document chunk"
    )
    relevant: bool = Field(
        description="Whether the chunk contains useful information for answering the question"
    )
    reason: str = Field(
        description="Brief explanation for the relevance decision"
    )


class DocumentGradingOutput(BaseModel):
    """Container for batch grading of retrieved document chunks."""

    grades: list[DocumentGrade]


class QueryRewriteOutput(BaseModel):
    """Rewritten query optimized for searching the FastAPI documentation corpus."""

    rewritten_query: str = Field(
        description="Search-optimized version of the query targeting FastAPI documentation"
    )
    reasoning: str = Field(
        description="Brief explanation of why the query was reformulated"
    )


class GroundednessCheckOutput(BaseModel):
    """Factuality and groundedness evaluation of a generated answer."""

    grounded: bool = Field(
        description="True if all claims in the answer are supported by the context documents"
    )
    reasoning: str = Field(
        description="Detailed explanation of the groundedness assessment"
    )
