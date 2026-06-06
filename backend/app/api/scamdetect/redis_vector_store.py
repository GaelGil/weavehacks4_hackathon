from array import array
from uuid import UUID

from redis import Redis

from app.core.config import settings
from app.database.schemas.Scan import ScanRiskLevel


class RedisScamVectorStore:
    def __init__(self) -> None:
        self._client = Redis.from_url(settings.REDIS_URL, decode_responses=False) if settings.REDIS_URL else None

    def index_confirmed_scam(
        self,
        *,
        scan_id: UUID,
        session_id: str,
        summary: str,
        detected_text: str,
        detected_urls: list[str],
        scam_type: str,
        risk_level: ScanRiskLevel,
    ) -> None:
        if self._client is None:
            return
        embedding = self._embedding_for_index(summary, detected_text, detected_urls, scam_type)
        self._ensure_index(len(embedding))
        self._client.hset(
            f"scam:{scan_id}",
            mapping={
                "scan_id": str(scan_id),
                "session_id": session_id,
                "summary": summary,
                "detected_text": detected_text,
                "detected_urls": "\n".join(detected_urls),
                "scam_type": scam_type,
                "risk_level": risk_level.value,
                "embedding": array("f", embedding).tobytes(),
            },
        )

    def search_similar_scams(
        self, *, embedding: list[float], limit: int | None = None
    ) -> list[dict[str, str | float | None]]:
        if self._client is None:
            return []
        self._ensure_index(len(embedding))
        top_k = limit or settings.SCAM_VECTOR_TOP_K
        raw = self._client.execute_command(
            "FT.SEARCH",
            settings.REDIS_INDEX_NAME,
            f"*=>[KNN {top_k} @embedding $vector AS score]",
            "PARAMS",
            2,
            "vector",
            array("f", embedding).tobytes(),
            "SORTBY",
            "score",
            "RETURN",
            6,
            "scan_id",
            "session_id",
            "summary",
            "scam_type",
            "risk_level",
            "score",
            "DIALECT",
            2,
        )
        results: list[dict[str, str | float | None]] = []
        for index in range(1, len(raw), 2):
            fields = raw[index + 1]
            parsed = _parse_fields(fields)
            distance = float(parsed.get("score", b"1"))
            if distance > settings.REDIS_VECTOR_DISTANCE_THRESHOLD:
                continue
            results.append(
                {
                    "id": parsed["scan_id"].decode("utf-8"),
                    "session_id": parsed["session_id"].decode("utf-8"),
                    "summary": parsed.get("summary", b"").decode("utf-8") or None,
                    "scam_type": parsed.get("scam_type", b"").decode("utf-8") or None,
                    "risk_level": _risk_level_from_bytes(parsed.get("risk_level")),
                    "similarity_score": round(1 - distance, 4),
                }
            )
        return results

    def _ensure_index(self, dimension: int) -> None:
        if self._client is None:
            return
        try:
            self._client.execute_command("FT.INFO", settings.REDIS_INDEX_NAME)
        except Exception:
            self._client.execute_command(
                "FT.CREATE",
                settings.REDIS_INDEX_NAME,
                "ON",
                "HASH",
                "PREFIX",
                1,
                "scam:",
                "SCHEMA",
                "scan_id",
                "TEXT",
                "session_id",
                "TEXT",
                "summary",
                "TEXT",
                "detected_text",
                "TEXT",
                "detected_urls",
                "TEXT",
                "scam_type",
                "TEXT",
                "risk_level",
                "TAG",
                "embedding",
                "VECTOR",
                "HNSW",
                6,
                "TYPE",
                "FLOAT32",
                "DIM",
                dimension,
                "DISTANCE_METRIC",
                "COSINE",
            )

    @staticmethod
    def _embedding_for_index(
        summary: str, detected_text: str, detected_urls: list[str], scam_type: str
    ) -> list[float]:
        from app.api.scamdetect.openai_service import embed_text

        return embed_text(
            "\n".join([summary, detected_text, " ".join(detected_urls), scam_type])
        )


def _parse_fields(fields: list[bytes]) -> dict[str, bytes]:
    return {
        fields[index].decode("utf-8"): fields[index + 1]
        for index in range(0, len(fields), 2)
    }


def _risk_level_from_bytes(value: bytes | None) -> str | None:
    if value is None:
        return None
    return value.decode("utf-8")
