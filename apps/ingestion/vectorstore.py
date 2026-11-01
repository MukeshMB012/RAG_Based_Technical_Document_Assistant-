import logging
from pathlib import Path
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer

from apps.ingestion.loader import load_documents
from apps.ingestion.chunker import chunk_documents, split_text

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
CHROMA_PATH = BASE_DIR / "chroma_db"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "fastapi_technical_docs"

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)

_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Retrieve the cached SentenceTransformer singleton instance."""
    global _embedding_model

    if _embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        try:
            # Prefer local cache to prevent network delays or offline timeouts
            _embedding_model = SentenceTransformer(
                EMBEDDING_MODEL_NAME,
                local_files_only=True,
            )
        except Exception:
            # Fall back to downloading if not cached locally
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded successfully.")

    return _embedding_model


def ingest_documents() -> dict[str, int]:
    """Load and index all Markdown documents from the docs/ directory."""
    documents = load_documents()

    if not documents:
        raise ValueError("No Markdown documents found in the docs directory.")

    chunks = chunk_documents(documents)
    if not chunks:
        raise ValueError("No chunks were generated from documents.")

    logger.info(
        f"Ingesting {len(documents)} documents ({len(chunks)} total chunks) into ChromaDB."
    )

    texts = [chunk["content"] for chunk in chunks]
    ids = [chunk["id"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True)

    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings.tolist(),
    )

    total_chunks = collection.count()
    logger.info(f"Ingestion complete. Total chunks in collection: {total_chunks}")

    return {
        "documents_loaded": len(documents),
        "chunks_created": len(chunks),
        "total_chunks_in_database": total_chunks,
    }


def ingest_custom_document(
    content: str,
    title: str,
    source: str,
    url: str = "",
) -> dict[str, int]:
    """Index an arbitrary text document into the vector store."""
    if not content.strip():
        raise ValueError("Document content cannot be empty.")

    text_chunks = split_text(content)
    if not text_chunks:
        raise ValueError("No chunks generated from the provided content.")

    clean_source = source.strip() or "custom_doc"
    clean_title = title.strip() or clean_source

    ids = [f"{clean_source}_{idx}" for idx in range(len(text_chunks))]
    metadatas = [
        {
            "source": clean_source,
            "title": clean_title,
            "url": url.strip(),
            "chunk_id": idx,
        }
        for idx in range(len(text_chunks))
    ]

    model = get_embedding_model()
    embeddings = model.encode(text_chunks, convert_to_numpy=True)

    collection.upsert(
        ids=ids,
        documents=text_chunks,
        metadatas=metadatas,
        embeddings=embeddings.tolist(),
    )

    total_chunks = collection.count()
    logger.info(
        f"Indexed custom document '{clean_title}' ({len(text_chunks)} chunks). Total: {total_chunks}"
    )

    return {
        "documents_loaded": 1,
        "chunks_created": len(text_chunks),
        "total_chunks_in_database": total_chunks,
    }


def search_documents(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Search ChromaDB for document chunks most similar to the query."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Query cannot be empty.")

    total_chunks = collection.count()
    if total_chunks == 0:
        raise RuntimeError("Vector database is empty. Run ingestion first.")

    top_k = min(max(1, top_k), total_chunks)
    model = get_embedding_model()
    query_embedding = model.encode(clean_query, convert_to_numpy=True)

    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    matches: list[dict[str, Any]] = []
    if not results or not results["ids"] or not results["ids"][0]:
        return matches

    for index in range(len(results["ids"][0])):
        matches.append({
            "id": results["ids"][0][index],
            "content": results["documents"][0][index],
            "metadata": results["metadatas"][0][index],
            "distance": results["distances"][0][index],
        })

    return matches


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    stats = ingest_documents()
    print("\nIngestion Summary:", stats)
