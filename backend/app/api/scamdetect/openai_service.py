import base64
import json

import weave
from openai import OpenAI

from app.core.config import settings
from app.database.schemas.Scan import VisionAnalysisResult


def analyze_image_bytes(
    image_bytes: bytes, content_type: str | None, source_text: str | None
) -> VisionAnalysisResult:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for image analysis")

    mime_type = content_type or "image/jpeg"
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    return _analyze_image_payload(
        image_data_url=f"data:{mime_type};base64,{image_base64}",
        source_text=source_text,
    )


def _analyze_image_payload(
    image_data_url: str, source_text: str | None
) -> VisionAnalysisResult:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.OPENAI_VISION_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze this image for scam indicators. Return JSON only with keys: "
                            "is_potential_scam, confidence_score, summary, scam_type, "
                            "impersonated_brand, detected_text, detected_urls, evidence, "
                            "extracted_details, recommended_actions. "
                            f"Additional user context: {source_text or 'none'}"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                    },
                ],
            }
        ],
    )
    return VisionAnalysisResult.model_validate(json.loads(response.output_text))


@weave.op
def embed_text(text: str) -> list[float]:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for embedding generation")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return list(response.data[0].embedding)
