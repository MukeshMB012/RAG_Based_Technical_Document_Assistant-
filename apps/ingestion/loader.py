import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
DOCS_DIR = BASE_DIR / "docs"


def load_documents() -> list[dict[str, Any]]:
    """Load Markdown documentation files from the docs/ directory.

    Extracts the document title from the top-level H1 header and
    the canonical source URL from the 'Source:' comment if present.
    """
    documents = []

    if not DOCS_DIR.exists():
        logger.warning(f"Docs directory not found at {DOCS_DIR}")
        return documents

    for file_path in sorted(DOCS_DIR.glob("*.md")):
        content = file_path.read_text(encoding="utf-8")

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else file_path.stem

        url_match = re.search(r"^Source:\s*(https?://\S+)", content, re.MULTILINE)
        source_url = url_match.group(1).strip() if url_match else ""

        documents.append({
            "content": content,
            "metadata": {
                "source": file_path.name,
                "title": title,
                "url": source_url,
            },
        })

    logger.info(f"Loaded {len(documents)} markdown documents from {DOCS_DIR}")
    return documents
