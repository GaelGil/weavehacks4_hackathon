"""CopilotKit remote endpoint.

Exposes the Advisor as a CopilotKit *action* backed by the OpenAI Agents SDK. The
React app talks to a CopilotKit Runtime (see frontend/copilotkit-runtime.mjs), which
forwards to this FastAPI endpoint at /copilotkit.

CopilotKit's Python SDK API has shifted across versions; this is written against the
`CopilotKitRemoteEndpoint` + `add_fastapi_endpoint` shape. If your installed version
differs, adjust the imports here (everything is isolated to this file). If CopilotKit
fails to import, the rest of the API still runs and the /advisor REST endpoint works.
"""
from __future__ import annotations

from fastapi import FastAPI

from .agents import advisor


def mount_copilotkit(app: FastAPI) -> bool:
    try:
        from copilotkit import Action as CopilotAction
        from copilotkit import CopilotKitRemoteEndpoint
        from copilotkit.integrations.fastapi import add_fastapi_endpoint
    except Exception as e:  # noqa: BLE001
        print(f"[copilot] CopilotKit SDK not available ({e}); skipping /copilotkit mount.")
        return False

    async def ask_scam_advisor(question: str, scan_context: str = "") -> str:
        """Answer the user's question about whether something is a scam and what to do."""
        return await advisor.chat(question, scan_context)

    sdk = CopilotKitRemoteEndpoint(
        actions=[
            CopilotAction(
                name="askScamAdvisor",
                description="Ask the ScamGuard advisor whether something is a scam and what to do about it.",
                parameters=[
                    {"name": "question", "type": "string", "required": True,
                     "description": "The user's question."},
                    {"name": "scan_context", "type": "string", "required": False,
                     "description": "Summary of the latest screen scan, if any."},
                ],
                handler=ask_scam_advisor,
            )
        ]
    )
    add_fastapi_endpoint(app, sdk, "/copilotkit")
    print("[copilot] mounted CopilotKit endpoint at /copilotkit")
    return True
