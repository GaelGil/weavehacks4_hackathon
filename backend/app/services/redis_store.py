"""Redis-backed storage: scam-message vector search, contacts, and verdict cache.

Uses Redis Stack (RediSearch + vectors). Everything degrades gracefully: if Redis
is unreachable, calls return empty/no-op results so the rest of the app keeps working.

    docker run -d -p 6379:6379 redis/redis-stack-server:latest
"""
from __future__ import annotations

import hashlib
import json
import struct
from typing import Optional

import numpy as np
import redis
from openai import OpenAI
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from ..config import get_settings
from ..models import SimilarScam

SCAM_INDEX = "scam_idx"
SCAM_PREFIX = "scam:"
CONTACT_PREFIX = "contact:"
CACHE_PREFIX = "verdict:"
EMBED_DIM = 1536  # text-embedding-3-small


class RedisStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._oai = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None
        try:
            self.r: Optional[redis.Redis] = redis.from_url(
                self.settings.redis_url, decode_responses=False
            )
            self.r.ping()
        except Exception as e:  # noqa: BLE001
            print(f"[redis_store] Redis unavailable ({e}); vector search disabled.")
            self.r = None

    # ---------- embeddings ----------
    def embed(self, text: str) -> Optional[np.ndarray]:
        if not self._oai or not text.strip():
            return None
        resp = self._oai.embeddings.create(model=self.settings.openai_embed_model, input=text)
        return np.array(resp.data[0].embedding, dtype=np.float32)

    @staticmethod
    def _to_bytes(vec: np.ndarray) -> bytes:
        return vec.astype(np.float32).tobytes()

    # ---------- index ----------
    def ensure_index(self) -> None:
        if not self.r:
            return
        try:
            self.r.ft(SCAM_INDEX).info()
            return  # already exists
        except Exception:  # noqa: BLE001
            pass
        schema = (
            TextField("text"),
            TagField("category"),
            VectorField(
                "embedding",
                "HNSW",
                {"TYPE": "FLOAT32", "DIM": EMBED_DIM, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        self.r.ft(SCAM_INDEX).create_index(
            schema,
            definition=IndexDefinition(prefix=[SCAM_PREFIX], index_type=IndexType.HASH),
        )
        print("[redis_store] created scam vector index")

    # ---------- scam corpus ----------
    def add_scam(self, text: str, category: str = "generic") -> bool:
        if not self.r:
            return False
        vec = self.embed(text)
        if vec is None:
            return False
        key = SCAM_PREFIX + hashlib.sha1(text.encode()).hexdigest()[:16]
        self.r.hset(key, mapping={"text": text, "category": category, "embedding": self._to_bytes(vec)})
        return True

    def search_similar(self, text: str, k: int = 3) -> list[SimilarScam]:
        if not self.r:
            return []
        vec = self.embed(text)
        if vec is None:
            return []
        q = (
            Query(f"*=>[KNN {k} @embedding $vec AS score]")
            .sort_by("score")
            .return_fields("text", "category", "score")
            .dialect(2)
        )
        try:
            res = self.r.ft(SCAM_INDEX).search(q, query_params={"vec": self._to_bytes(vec)})
        except Exception as e:  # noqa: BLE001
            print(f"[redis_store] search failed: {e}")
            return []
        out: list[SimilarScam] = []
        for doc in res.docs:
            # COSINE distance -> similarity
            distance = float(doc.score)
            out.append(
                SimilarScam(
                    text=doc.text.decode() if isinstance(doc.text, bytes) else doc.text,
                    score=round(1.0 - distance, 3),
                    category=(doc.category.decode() if isinstance(doc.category, bytes) else doc.category),
                )
            )
        return out

    # ---------- contacts ----------
    def set_contact(self, identifier: str, trusted: bool) -> None:
        if not self.r:
            return
        self.r.hset(CONTACT_PREFIX + identifier, mapping={"trusted": "1" if trusted else "0"})

    def get_contact(self, identifier: str) -> Optional[bool]:
        if not self.r:
            return None
        val = self.r.hget(CONTACT_PREFIX + identifier, "trusted")
        if val is None:
            return None
        return val == b"1" or val == "1"

    # ---------- verdict cache (skip re-scanning an unchanged screen) ----------
    def cache_get(self, image_b64: str) -> Optional[dict]:
        if not self.r:
            return None
        key = CACHE_PREFIX + hashlib.sha1(image_b64.encode()).hexdigest()
        raw = self.r.get(key)
        return json.loads(raw) if raw else None

    def cache_set(self, image_b64: str, result: dict, ttl: int = 300) -> None:
        if not self.r:
            return
        key = CACHE_PREFIX + hashlib.sha1(image_b64.encode()).hexdigest()
        self.r.set(key, json.dumps(result), ex=ttl)


_store: Optional[RedisStore] = None


def get_store() -> RedisStore:
    global _store
    if _store is None:
        _store = RedisStore()
    return _store
