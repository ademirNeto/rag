"""
Embedding and indexing: converts validated rules into dense vectors and upserts into Qdrant.
Payload metadata enables pre-search filtering (brand, modality, product, MCC, vigency).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict

from src.extraction.llm_extractor import InterchangeRule

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams
except ImportError:
    QdrantClient = None  # type: ignore[assignment,misc]

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore[assignment,misc]

COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "interchange_rules")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
VECTOR_DIM = 3072  # text-embedding-3-large output dimension


def _rule_to_text(rule: InterchangeRule) -> str:
    conditions = "; ".join(rule.conditions) if rule.conditions else "none"
    modality = "Card Present" if rule.card_present else "Card Not Present"
    return (
        f"{rule.brand.upper()} {rule.product} {rule.card_category} {modality} "
        f"Program: {rule.fee_program}. "
        f"Rate: {rule.rate_pct}% + ${rule.rate_fixed_usd:.2f}. "
        f"Conditions: {conditions}."
    )


def _rule_to_id(rule: InterchangeRule) -> str:
    key = f"{rule.brand}|{rule.fee_program}|{rule.card_present}|{rule.product}"
    return hashlib.md5(key.encode()).hexdigest()


class QdrantIndexer:
    def __init__(self, url: str | None = None) -> None:
        url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        if QdrantClient is None:
            raise ImportError("qdrant-client is required")
        self.client = QdrantClient(url=url)
        self._openai = OpenAI() if OpenAI else None
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in existing:
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )

    def upsert(self, rules: list[InterchangeRule]) -> int:
        points = []
        texts = [_rule_to_text(r) for r in rules]
        vectors = self._embed_batch(texts)
        for rule, vector in zip(rules, vectors):
            points.append(
                PointStruct(
                    id=_rule_to_id(rule),
                    vector=vector,
                    payload={
                        "brand": rule.brand,
                        "card_category": rule.card_category,
                        "product": rule.product,
                        "fee_program": rule.fee_program,
                        "rate_pct": rule.rate_pct,
                        "rate_fixed_usd": rule.rate_fixed_usd,
                        "cap_usd": rule.cap_usd,
                        "floor_usd": rule.floor_usd,
                        "card_present": rule.card_present,
                        "conditions": rule.conditions,
                    },
                )
            )
        self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        return len(points)

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._openai is None:
            raise ImportError("openai package required for embedding")
        response = self._openai.embeddings.create(input=texts, model=EMBEDDING_MODEL)
        return [item.embedding for item in response.data]
