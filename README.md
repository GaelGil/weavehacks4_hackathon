# ScamGuard 🛡️

An AI desktop guardian that protects vulnerable users (e.g. older relatives) from
phishing, scams, and harmful actions on their computer. When the user feels unsafe,
they hit **"Check my screen"** — a pipeline of agents redacts sensitive info,
classifies the screen for scams, checks it against known scam patterns, and opens a
CopilotKit chat that explains what's happening and suggests safe actions.

Built for **WeaveHacks**.

## Architecture

```
┌─────────────────────────────────────────┐         ┌──────────────────────────────────────────┐
│            Electron App (frontend)        │         │              FastAPI (backend)             │
│                                           │         │                                            │
│  React + Vite renderer                    │         │  /scan        ─► Orchestrator pipeline      │
│  • "Check my screen" button               │  HTTP   │                  1. PrivacyRedactor agent   │
│  • desktopCapturer screenshot ───────────────────►  │                  2. ScamClassifier  (vision)│
│  • CopilotKit chat sidebar ──────────────────────►  │                  3. Redis vector search     │
│                                           │ /copilotkit│               4. Advisor agent (actions) │
│                                           │         │                                            │
│                                           │         │  OpenAI Agents SDK  ── traced by ──► Weave  │
└─────────────────────────────────────────┘         └──────────────────────────────────────────┘
                                                              │
                                                       Redis Stack (vector search + contacts + cache)
```

### The agents (OpenAI Agents SDK)
| Agent | Job |
|-------|-----|
| `PrivacyRedactor` | Detects sensitive info (passwords, SSNs, account numbers) on screen and decides what to censor **before** anything is classified. Privacy is a feature. |
| `ScamClassifier` | Vision agent. Looks at the (redacted) screenshot + context and returns a structured verdict: scam / safe, risk score, reasons. |
| `Advisor` | Powers the CopilotKit chat. Explains the verdict in plain language and proposes safe, concrete actions. |

All agent calls are traced in **Weave** (`weave.init`) so you get a full trace tree
per scan, plus an `Evaluation` harness for measuring scam recall / false positives.

## Sponsor tools
- **W&B Weave** — tracing of every agent op + an evaluation harness (`backend/eval/`).
- **Redis** — vector search over known scam messages, trusted/untrusted contacts, and verdict caching.
- **CopilotKit** — the in-app advisor chat + suggested actions UI.

## Repo layout
```
backend/                 FastAPI + OpenAI Agents SDK + Weave + Redis
  app/agents/            redactor, classifier, advisor, pipeline (orchestrator)
  app/services/          redis_store (vector search, contacts, cache)
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
python -m app.seed          # seed example scam vectors (needs Redis)
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
