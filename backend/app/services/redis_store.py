"""Redis-backed storage: scam-message vector search, contacts, and verdict cache.

Uses Redis Stack (RediSearch + vectors). Everything degrades gracefully: if Redis
is unreachable, calls return empty/no-op results so the rest of the app keeps working.

    docker run -d -p 6379:6379 redis/redis-stack-server:latest
"""

from __future__ import annotations

import base64
import hashlib
import io
import json

import numpy as np
import redis
from openai import OpenAI
from PIL import Image
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.query import Query

try:
    # redis-py >= 5.1 (snake_case module)
    from redis.commands.search.index_definition import IndexDefinition, IndexType
except ImportError:  # pragma: no cover - older redis-py
    from redis.commands.search.indexDefinition import IndexDefinition, IndexType

from ..config import get_settings
from ..models import SimilarExample

# A single corpus holding BOTH known scams and known-legit messages, tagged by `label`,
# so the ResearchAgent can pull two-sided comparison evidence.
EXAMPLE_INDEX = "example_idx"
EXAMPLE_PREFIX = "example:"


def _perceptual_hash(image_b64: str) -> int:
    """Difference-hash (dHash): a 64-bit fingerprint of what the image LOOKS like.

    Resize to 9x8 grayscale, then for each row record whether each pixel is brighter
    than the one to its right (8 comparisons x 8 rows = 64 bits). This is deliberately
    coarse — a blinking cursor, font antialiasing, or a ticking clock barely move these
    bits, but a different email/page/app changes large regions and flips many of them.
    Raises on undecodable input; callers treat that as "can't hash, so don't cache".
    """
    raw = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(raw)).convert("L").resize((9, 8), Image.LANCZOS)
    pixels = np.asarray(img, dtype=np.int16)
    bits = pixels[:, :-1] > pixels[:, 1:]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
CONTACT_PREFIX = "contact:"
# v4: cache key switched from a raw-byte SHA1 (which misses on every cursor blink,
# antialiasing jitter, or ticking clock) to a perceptual hash with fuzzy matching —
# see _perceptual_hash / _hamming below.
CACHE_VERSION = "v4"
CACHE_PREFIX = f"verdict:{CACHE_VERSION}:"
# dHash produces an 8x8 = 64-bit fingerprint. Two screenshots of the *same* on-screen
# content typically differ by 0-3 bits (cursor/clock/AA noise); genuinely different
# content (a new email, a scrolled page) typically flips 15+ bits. 6 is a conservative
# midpoint — tune up if real changes are being cached, down if noise still misses.
PHASH_HAMMING_THRESHOLD = 6
# How many recent (hash, cache_key) pairs we keep around to fuzzy-match against. Bounded
# small on purpose: at a 15s poll / 300s TTL there are at most ~20 live entries anyway,
# so a linear Hamming scan over this list is a handful of XOR+popcount ops, not a search.
RECENT_PHASH_LIMIT = 40
RECENT_PHASH_KEY = "scamguard:cache:recent_phashes"
EMBED_DIM = 1536  # text-embedding-3-small

ALERT_KEY = "scamguard:alerts"
DETECTION_PROCESS_KEY = "scamguard:detections:process"
DETECTION_NETWORK_KEY = "scamguard:detections:network"
MAX_STORED = 1000

# In-memory fallbacks when Redis is unavailable
_alert_fallback: list[dict] = []
_process_fallback: list[dict] = []
_network_fallback: list[dict] = []


class RedisStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._oai = (
            OpenAI(api_key=self.settings.openai_api_key)
            if self.settings.openai_api_key
            else None
        )
        try:
            # Force RESP2: redis-py's FT.SEARCH result parser returns 0 results under
            # RESP3 on Redis 8 (vector/KNN search silently comes back empty otherwise).
            self.r: redis.Redis | None = redis.from_url(
                self.settings.redis_url, decode_responses=False, protocol=2
            )
            self.r.ping()
        except Exception as e:  # noqa: BLE001
            print(f"[redis_store] Redis unavailable ({e}); vector search disabled.")
            self.r = None

    # ---------- embeddings ----------
    def embed(self, text: str) -> np.ndarray | None:
        if not self._oai or not text.strip():
            return None
        resp = self._oai.embeddings.create(
            model=self.settings.openai_embed_model, input=text
        )
        return np.array(resp.data[0].embedding, dtype=np.float32)

    @staticmethod
    def _to_bytes(vec: np.ndarray) -> bytes:
        return vec.astype(np.float32).tobytes()

    # ---------- index ----------
    def ensure_index(self) -> None:
        if not self.r:
            return
        try:
            self.r.ft(EXAMPLE_INDEX).info()
            return  # already exists
        except Exception:  # noqa: BLE001
            pass
        schema = (
            TextField("text"),
            TagField("label"),  # "scam" | "legit"
            TagField("category"),
            VectorField(
                "embedding",
                "HNSW",
                {"TYPE": "FLOAT32", "DIM": EMBED_DIM, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        self.r.ft(EXAMPLE_INDEX).create_index(
            schema,
            definition=IndexDefinition(
                prefix=[EXAMPLE_PREFIX], index_type=IndexType.HASH
            ),
        )
        print("[redis_store] created example vector index")

    # ---------- example corpus (scams + legit) ----------
    def add_example(
        self, text: str, label: str = "scam", category: str = "generic"
    ) -> bool:
        if not self.r:
            return False
        vec = self.embed(text)
        if vec is None:
            return False
        key = EXAMPLE_PREFIX + hashlib.sha1(f"{label}:{text}".encode()).hexdigest()[:16]
        self.r.hset(
            key,
            mapping={
                "text": text,
                "label": label,
                "category": category,
                "embedding": self._to_bytes(vec),
            },
        )
        return True

    def search_examples(
        self, text: str, k: int = 3, label: str | None = None
    ) -> list[SimilarExample]:
        """KNN over the corpus. Pass label='scam' or 'legit' to restrict the comparison set."""
        if not self.r:
            return []
        vec = self.embed(text)
        if vec is None:
            return []
        prefilter = f"@label:{{{label}}}" if label else "*"
        q = (
            Query(f"{prefilter}=>[KNN {k} @embedding $vec AS score]")
            .sort_by("score")
            .return_fields("text", "label", "category", "score")
            .dialect(2)
        )
        try:
            res = self.r.ft(EXAMPLE_INDEX).search(
                q, query_params={"vec": self._to_bytes(vec)}
            )
        except Exception as e:  # noqa: BLE001
            print(f"[redis_store] search failed: {e}")
            return []

        def dec(v):
            return v.decode() if isinstance(v, bytes) else v

        out: list[SimilarExample] = []
        for doc in res.docs:
            distance = float(doc.score)  # COSINE distance -> similarity
            out.append(
                SimilarExample(
                    text=dec(doc.text),
                    score=round(1.0 - distance, 3),
                    label=dec(getattr(doc, "label", "scam")) or "scam",
                    category=dec(getattr(doc, "category", "")),
                )
            )
        return out

    # ---------- contacts ----------
    def set_contact(self, identifier: str, trusted: bool) -> None:
        if not self.r:
            return
        self.r.hset(
            CONTACT_PREFIX + identifier, mapping={"trusted": "1" if trusted else "0"}
        )

    def get_contact(self, identifier: str) -> bool | None:
        if not self.r:
            return None
        val = self.r.hget(CONTACT_PREFIX + identifier, "trusted")
        if val is None:
            return None
        return val == b"1" or val == "1"

    # ---------- verdict cache (skip re-scanning a screen that LOOKS unchanged) ----------
    # Keyed on a perceptual hash of the screenshot with fuzzy (Hamming-distance) matching,
    # NOT the raw image bytes — a byte-exact hash misses on every cursor blink, AA jitter,
    # or ticking clock, which makes the cache a near-permanent miss during active use.
    def _recent_phashes(self) -> list[tuple[int, str]]:
        if not self.r:
            return []
        out: list[tuple[int, str]] = []
        for raw in self.r.lrange(RECENT_PHASH_KEY, 0, RECENT_PHASH_LIMIT - 1):
            try:
                phash_hex, cache_key = json.loads(raw)
                out.append((int(phash_hex, 16), cache_key))
            except Exception:  # noqa: BLE001 - corrupt entry; skip it
                continue
        return out

    def _remember_phash(self, phash: int, cache_key: str, ttl: int) -> None:
        if not self.r:
            return
        entry = json.dumps([format(phash, "016x"), cache_key])
        pipe = self.r.pipeline()
        pipe.lpush(RECENT_PHASH_KEY, entry)
        pipe.ltrim(RECENT_PHASH_KEY, 0, RECENT_PHASH_LIMIT - 1)
        pipe.expire(RECENT_PHASH_KEY, ttl)
        pipe.execute()

    def cache_get(self, image_b64: str) -> dict | None:
        if not self.r:
            return None
        try:
            phash = _perceptual_hash(image_b64)
        except Exception as e:  # noqa: BLE001 - bad/undecodable image; just don't cache
            print(f"[redis_store] perceptual hash failed on lookup: {e}")
            return None
        for candidate, cache_key in self._recent_phashes():
            if _hamming(phash, candidate) <= PHASH_HAMMING_THRESHOLD:
                raw = self.r.get(cache_key)
                if raw:
                    return json.loads(raw)
        return None

    def cache_set(self, image_b64: str, result: dict, ttl: int = 300) -> None:
        if not self.r:
            return
        try:
            phash = _perceptual_hash(image_b64)
        except Exception as e:  # noqa: BLE001 - bad/undecodable image; nothing to key on
            print(f"[redis_store] perceptual hash failed on store: {e}")
            return
        cache_key = CACHE_PREFIX + format(phash, "016x")
        self.r.set(cache_key, json.dumps(result), ex=ttl)
        self._remember_phash(phash, cache_key, ttl)

    # ---------- alert history ----------
    def push_alert(self, alert: dict) -> None:
        if self.r:
            self.r.lpush(ALERT_KEY, json.dumps(alert))
            self.r.ltrim(ALERT_KEY, 0, MAX_STORED - 1)
        else:
            _alert_fallback.insert(0, alert)
            if len(_alert_fallback) > MAX_STORED:
                _alert_fallback.pop()

    def get_alerts(self, limit: int = 100) -> list[dict]:
        if self.r:
            return [json.loads(r) for r in self.r.lrange(ALERT_KEY, 0, limit - 1)]
        return _alert_fallback[:limit]

    # ---------- process detections ----------
    def push_process_detection(self, detection: dict) -> None:
        if self.r:
            self.r.lpush(DETECTION_PROCESS_KEY, json.dumps(detection))
            self.r.ltrim(DETECTION_PROCESS_KEY, 0, MAX_STORED - 1)
        else:
            _process_fallback.insert(0, detection)
            if len(_process_fallback) > MAX_STORED:
                _process_fallback.pop()

    # ---------- network events ----------
    def push_network_event(self, event: dict) -> None:
        if self.r:
            self.r.lpush(DETECTION_NETWORK_KEY, json.dumps(event))
            self.r.ltrim(DETECTION_NETWORK_KEY, 0, MAX_STORED - 1)
        else:
            _network_fallback.insert(0, event)
            if len(_network_fallback) > MAX_STORED:
                _network_fallback.pop()


_store: RedisStore | None = None


def get_store() -> RedisStore:
    global _store
    if _store is None:
        _store = RedisStore()
    return _store
