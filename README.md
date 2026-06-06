# ScamGuard 🛡️

An AI desktop guardian that protects vulnerable users (e.g. older relatives) from
phishing, scams, and harmful actions on their computer. When the user feels unsafe,
they hit **"Check my screen"** — a pipeline of agents redacts sensitive info,
classifies the screen for scams, checks it against known scam patterns, and opens a
CopilotKit chat that explains what's happening and suggests safe actions.

Built for **WeaveHacks**.

## Architecture

```
┌─────────────────────────────────────────┐         ┌──────────────────────────────────────────────┐
│            Electron App (frontend)        │         │                FastAPI (backend)               │
│                                           │         │                                                │
│  React + Vite renderer                    │         │  /scan ─► Orchestrator pipeline:               │
│  • "Check my screen" button               │  HTTP   │    1. PrivacyRedactor  ┐ (parallel)            │
│  • desktopCapturer screenshot ───────────────────►  │    2. CollectDataAgent ┘  facts                │
│  • CopilotKit chat sidebar ──────────────────────►  │    3. ResearchAgent  (web search + Redis cmp)  │
│                                           │ /copilotkit│  4. Advisor  (vision + facts + research)     │
│                                           │         │                                                │
│                                           │         │  OpenAI Agents SDK  ── traced by ──► Weave     │
└─────────────────────────────────────────┘         └──────────────────────────────────────────────┘
                                                              │
                                          Redis Stack (scam+legit vector corpus, contacts, verdict cache)
```

### The agents (OpenAI Agents SDK)
The key design choice: **observe → research → judge**, instead of one agent guessing from
raw pixels (which over-flagged legit transactional email). Each stage feeds the next context.

| Agent | Stage | Job |
|-------|-------|-----|
| `PrivacyRedactor` | guard | Detects sensitive info (passwords, SSNs, account numbers) so it never flows through logs/traces. Runs in parallel with collection. |
| `CollectDataAgent` | 1. observe | Vision agent. Extracts **structured facts** (sender, subject, links, CTAs, requests, urgency) — no judgment. |
| `ResearchAgent` | 2. research | Uses **web search** to vet the sender domain/brand and **Redis** to pull similar known *scams* and known *legit* messages as comparison evidence. |
| `Advisor` | 3. judge | Looks at the screenshot **with** the facts + research, makes the final verdict + plain-language advice + suggested actions. Also powers the CopilotKit chat. |

All agent calls are traced in **Weave** (`weave.init`) so you get a full trace tree
per scan, plus an `Evaluation` harness for measuring scam recall / false positives.

## Sponsor tools
- **W&B Weave** — tracing of every agent op + an evaluation harness (`backend/eval/`).
- **Redis** — vector search over known scam messages, trusted/untrusted contacts, and verdict caching.
- **CopilotKit** — the in-app advisor chat + suggested actions UI.

## Repo layout
```
backend/                 FastAPI + OpenAI Agents SDK + Weave + Redis
  app/agents/            redactor, collector, researcher, advisor, pipeline (orchestrator)
  app/services/          redis_store (scam+legit vector corpus, contacts, cache)
  app/copilot.py         CopilotKit remote endpoint (advisor as an action)
  eval/                  Weave Evaluation harness + labeled dataset
frontend/                Electron app (teammate's main.js/preload.js + auto-update kept)
  renderer/              React + Vite renderer (CopilotKit UI + scan panel)
  copilotkit-runtime.mjs Node CopilotKit runtime bridging React -> FastAPI
```

## Quickstart

There are **three processes**: FastAPI backend, the CopilotKit Node runtime, and the
Electron app (which runs Vite + Electron together).

### 1. Backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in OPENAI_API_KEY and WANDB_API_KEY
# (optional) start Redis Stack for vector search:
#   docker run -d -p 6379:6379 redis/redis-stack-server:latest
python -m app.seed          # seed scam + legit comparison vectors (needs Redis)
uvicorn app.main:app --reload --port 8000
```

### 2. CopilotKit runtime (new terminal)
```bash
cd frontend
npm install
export OPENAI_API_KEY=sk-...   # the runtime needs it for the chat LLM
npm run copilot:runtime        # http://localhost:4000/copilotkit
```

### 3. Electron app (new terminal)
```bash
cd frontend
npm run dev                    # Vite (:5173) + Electron together
```

> If you just want to skip CopilotKit for now, the app still works: the scan panel
> calls the backend directly, and there's a plain `/advisor` REST endpoint.

### Run the Weave evaluation
```bash
cd backend && python -m eval.eval_classifier
```

## Version note on CopilotKit
CopilotKit's APIs move fast. The wiring lives in exactly two files — `backend/app/copilot.py`
(Python remote endpoint) and `frontend/copilotkit-runtime.mjs` (Node runtime) — so if your
installed version's API differs, those are the only places to adjust.

## Demo script (2 min)
1. Open a fake phishing email on screen.
2. Click **Check my screen** in ScamGuard.
3. Watch: redaction → verdict ("⚠️ Likely scam, 0.91") → reasons.
4. Open the CopilotKit chat: "Is this a scam? What do I do?"
5. Show the **Weave** trace of the whole pipeline.
6. Show the **Weave Evaluation** scorecard.

## Status / TODO
- [x] Backend pipeline (redactor → classifier → redis → advisor)
- [x] Electron screenshot capture + scan UI
- [x] CopilotKit chat wired to FastAPI
- [x] Redis vector-search stub + seeder
- [x] Weave tracing + eval harness
- [ ] **True pixel redaction** (OCR + blur regions) — currently the redactor *describes* what to censor
- [ ] Event-driven triggers (download/clipboard/navigation) instead of only manual scan
- [ ] Process / Activity Monitor scanner (stretch)
- [ ] Browser-control actions, e.g. "block sender" (stretch)
