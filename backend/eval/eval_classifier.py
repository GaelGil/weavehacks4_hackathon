"""Weave Evaluation harness for the ScamClassifier.

This is the differentiating Weave story: a labeled dataset + scorers that measure
scam recall and false-positive rate, viewable as a scorecard in the Weave UI.

    cd backend && python -m eval.eval_classifier

Note: this version evaluates on TEXT context (no screenshots) so it runs cheaply and
without image fixtures. Drop screenshots into the dataset and pass image_b64 to extend it.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import weave

from app.agents.classifier import classify
from app.config import get_settings

DATA = Path(__file__).parent / "dataset.jsonl"


def load_examples() -> list[dict]:
    rows = []
    for line in DATA.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


@weave.op()
async def model(context_text: str) -> dict:
    verdict = await classify(image_b64=None, context_text=context_text)
    return {"verdict": verdict.verdict, "risk_score": verdict.risk_score}


@weave.op()
def scam_recall(expected: str, output: dict) -> dict:
    """Did we catch scams? (only counts on scam examples)"""
    if expected != "scam":
        return {"applicable": False}
    caught = output["verdict"] in ("scam", "suspicious")
    return {"applicable": True, "caught": caught}


@weave.op()
def false_positive(expected: str, output: dict) -> dict:
    """Did we wrongly flag a safe screen? (only counts on safe examples)"""
    if expected != "safe":
        return {"applicable": False}
    flagged = output["verdict"] in ("scam", "suspicious")
    return {"applicable": True, "false_positive": flagged}


async def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("Set OPENAI_API_KEY in backend/.env first.")
    weave.init(settings.weave_project)

    evaluation = weave.Evaluation(
        dataset=load_examples(),
        scorers=[scam_recall, false_positive],
    )
    await evaluation.evaluate(model)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONPATH", str(Path(__file__).parents[1]))
    asyncio.run(main())
