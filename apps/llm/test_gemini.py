from apps.llm.client import generate_structured
from pydantic import BaseModel


class TestOutput(BaseModel):
    answer: str
    relevant: bool


result = generate_structured(
    """
    Determine whether this document is relevant to the question.

    Question:
    What does Depends do in FastAPI?

    Document:
    FastAPI Depends allows declaring dependencies that FastAPI
    resolves and injects when handling a request.

    Return whether the document is relevant and explain why.
    """,
    TestOutput,
)

print(result)