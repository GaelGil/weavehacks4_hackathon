"""Shared helpers for building OpenAI Agents SDK inputs."""
from __future__ import annotations


def vision_input(prompt: str, image_b64: str | None) -> list[dict]:
    """Build a Responses-style multimodal input list for Runner.run.

    The OpenAI Agents SDK accepts either a plain string or a list of message dicts.
    For vision we pass an input_text + input_image content block.
    """
    content: list[dict] = [{"type": "input_text", "text": prompt}]
    if image_b64:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{image_b64}",
            }
        )
    return [{"role": "user", "content": content}]
