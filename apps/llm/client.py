import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

MAX_RETRIES = 2
INITIAL_BACKOFF = 1.5
BACKOFF_MULTIPLIER = 2.0
REQUEST_TIMEOUT_MS = 120000

T = TypeVar("T", bound=BaseModel)


def get_active_model_name() -> str:
    """Return the active model name."""
    return MODEL_NAME


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Retrieve or initialize the singleton Gemini client."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Please set it in your .env file."
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )
    logger.info(f"Initialized Gemini client singleton for model: {MODEL_NAME}")
    return client


def reset_gemini_client() -> None:
    """Clear the cached client singleton to reset stale HTTP connection pools."""
    get_gemini_client.cache_clear()
    logger.info("Cleared cached Gemini client instance.")


def _call_with_retry(fn: Callable[[], Any], description: str = "Gemini API call") -> Any:
    """Execute a Gemini API call on gemini-3.8-flash with exponential backoff."""
    last_error: Exception | None = None
    backoff = INITIAL_BACKOFF

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            error_str = str(exc).lower()

            is_transient = any(k in error_str for k in [
                "disconnected",
                "remoteprotocolerror",
                "connection",
                "timeout",
                "503",
                "504",
                "high demand",
                "spikes in demand",
                "deadline exceeded",
                "429",
                "resource exhausted",
                "unavailable",
            ])

            if "disconnected" in error_str or "remoteprotocolerror" in error_str:
                reset_gemini_client()

            if not is_transient or attempt == MAX_RETRIES:
                break

            logger.warning(
                f"{description} with {MODEL_NAME} attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                f"Retrying in {backoff:.1f}s..."
            )
            time.sleep(backoff)
            backoff *= BACKOFF_MULTIPLIER

    raise RuntimeError(
        f"{description} with {MODEL_NAME} failed after {MAX_RETRIES} attempts: {last_error}"
    ) from last_error


def generate_text(
    prompt: str,
    temperature: float = 0.1,
    max_output_tokens: int = 2048,
) -> str:
    """Generate freeform text using gemini-3.8-flash."""
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    def _invoke():
        client = get_gemini_client()
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=clean_prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )

    response = _call_with_retry(_invoke, "generate_text")

    if not response.text:
        raise RuntimeError(f"Gemini {MODEL_NAME} returned an empty text response.")

    return response.text.strip()


def generate_structured(
    prompt: str,
    response_schema: type[T],
    temperature: float = 0.0,
    max_output_tokens: int = 2048,
) -> T:
    """Generate a structured Pydantic object from gemini-3.8-flash."""
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    def _invoke():
        client = get_gemini_client()
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=clean_prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                response_schema=response_schema,
            ),
        )

    response = _call_with_retry(_invoke, "generate_structured")

    if not response.text:
        raise RuntimeError(f"Gemini {MODEL_NAME} returned an empty structured response.")

    return response_schema.model_validate_json(response.text)
