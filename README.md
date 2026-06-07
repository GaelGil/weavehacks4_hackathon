# ScamGuard 🛡️

An AI desktop guardian that protects vulnerable users (e.g. older relatives) from
phishing, scams, and harmful actions on their computer. When the user feels unsafe they
hit **"Check my screen"** — a pipeline of agents redacts sensitive info, extracts the
facts, researches the sender (web + a Redis scam corpus), then a **triage agent routes to
a scam specialist** that delivers a plain-language verdict and safe next steps. A
CopilotKit chat answers follow-up questions.

Built for **WeaveHacks 4 — the Multi-Agent Orchestration Hackathon with Weights & Biases.**

## Architecture

```
┌──────────────────────────────────────────┐        ┌────────────────────────────────────────────────┐
│            Electron App (frontend)         │        │                 FastAPI (backend)                │
│                                            │        │                                                  │
│  React + Vite renderer                     │  HTTP  │  POST /api/v1/scans/scan  ─► Agent pipeline:     │
│  • "Check my screen" ─────────────────────────────►│      redact ∥ collect → research → triage ─┐     │
│  • CopilotKit chat sidebar ──┐             │        │                                    ┌───────┘     │
│                              │             │        │                                    ▼             │
│  Background detector pillars:│             │        │              ┌─ PhishingEmailSpecialist          │
│  • screen poll (OpenAI)      │             │        │  TriageAgent ┼─ TechSupportScamSpecialist ...    │
│  • process scanner           │             │        │   (handoff)  └─ GeneralAdvisor  → verdict        │
│  • network monitor (observe) │             │        │                                                  │
└──────────────────────────────┼────────────┘        │  OpenAI Agents SDK  ── traced by ──► W&B Weave   │
                               │                      │  Postgres (scan history)  ·  WebSocket (live)    │
                               ▼                      └────────────────────────────────────────────────┘
                  CopilotKit Node runtime (:4000) ─► OpenAI            │
                                                              Redis (scam+legit vector corpus,
                                                                     contacts, verdict cache)
```

### The agent pipeline (OpenAI Agents SDK)
Design principle: **observe → research → route → judge**, instead of one agent guessing from
raw pixels (which over-flagged legitimate transactional email). Each stage feeds the next
context, and the final decision is made by a *specialist* for the detected scam type.

| Agent | Stage | Job |
|-------|-------|-----|
| `PrivacyRedactor` | guard | Flags sensitive info (passwords, SSNs, account numbers) so it never flows through logs/traces. Runs in parallel with collection. |
| `CollectDataAgent` | observe | Vision agent. Extracts **structured facts** (sender, subject, links, CTAs, urgency) — no judgment. |
| `ResearchAgent` | research | **Web search** to vet the sender/brand/domain, plus **Redis** KNN to pull similar known *scams* and *legit* messages as comparison evidence. |
| `TriageAgent` | route | Reads facts + research and **hands off** (Agents SDK handoffs) to the single best specialist. |
| Specialists ×8 | judge | Phishing, TechSupport, Crypto, MaliciousDownload, AdvanceFee, Lottery, FakeEmployment, + GeneralAdvisor. Each makes the final verdict + tailored advice/actions for its scam type. |
| `AdvisorChat` | chat | Free-form Q&A persona (also exposed via the `/advisor` REST endpoint). |

Every op is traced in **Weave**, so each scan is one trace tree showing
`collect → research → TriageAgent ─handoff→ <Specialist>`. The UI shows which specialist
handled it ("🔎 Handled by Phishing Email Specialist").

## Sponsor tools
- **W&B Weave** — tracing of every agent op + an `Evaluation` harness (`backend/eval/`).
- **Redis** — vector (KNN) similarity search over a seeded scam + legit corpus, trusted/untrusted contacts, and a verdict cache. *(On Redis 8 the client forces RESP2 — see note below.)*
- **CopilotKit** — the in-app chat sidebar (plain-language, scan-aware), powered by a self-hosted Node runtime → OpenAI.

## Repo layout
```
backend/                   FastAPI (full-stack template) + OpenAI Agents SDK + Weave + Redis + Postgres
  app/agents/              redactor, collector, researcher, specialists (triage + 8), advisor, pipeline
  app/services/            redis_store — scam+legit vector corpus, contacts, verdict cache
  app/api/scamdetect/      DB-backed scan controller, ScanService, redis_vector_store, openai_service
  app/api/websocket/       live scan-event streaming
  app/database/            SQLModel models + Alembic migrations (Postgres scan history)
  app/core/config.py       backend settings (reads the repo-root ../.env)
  app/config.py            agent-pipeline settings (reads backend/.env)
  eval/                    Weave Evaluation harness + labeled dataset
frontend/                  Electron app
  main.js / preload.js     Electron main: screenshot IPC, detector pillars, auto-update
  modules/                 screenCapture, llmAnalyzer, processScanner, networkMonitor, alertManager
  renderer/                React + Vite renderer (scan panel + CopilotKit sidebar)
  copilotkit-runtime.mjs   Node CopilotKit runtime → OpenAI (the chat)
```

## Quickstart

Three processes: **backend**, the **CopilotKit runtime**, and the **Electron app**.

> ⚠️ Two `.env` files. Keys must be in **both**: the repo-root `../.env` (read by
> `app/core/config.py`) and `backend/.env` (read by the agent pipeline's `app/config.py`).

### 1. Backend (uv-managed)
```bash
cd backend
uv sync                                  # installs deps from pyproject.toml / uv.lock

# Postgres + Redis (or point REDIS_URL at Redis Cloud instead of the local container)
docker run -d --name sg-postgres -p 5432:5432 -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=scamguard postgres:16
docker run -d --name sg-redis    -p 6379:6379 redis/redis-stack-server:latest

# repo-root ../.env  (PROJECT_NAME, POSTGRES_*, OPENAI_API_KEY, WANDB_API_KEY, WANDB_WEAVE_PROJECT, REDIS_URL)
# backend/.env       (OPENAI_API_KEY, WANDB_API_KEY, WEAVE_PROJECT, REDIS_URL)

uv run alembic upgrade head              # create the DB tables
uv run python -m app.seed                # seed the scam + legit comparison corpus (needs Redis)
uv run uvicorn app.main:app --reload --port 8000
```

### 2. CopilotKit runtime (new terminal)
```bash
cd frontend
npm install --legacy-peer-deps           # resolves the @anthropic-ai/sdk peer conflict
npm run copilot:runtime                  # http://localhost:4000 → OpenAI (reads OPENAI_API_KEY from backend/.env)
```

### 3. Electron app (new terminal)
```bash
cd frontend
npm run dev                              # Vite (:5173) + Electron together
```

### Run the Weave evaluation
```bash
cd backend && uv run python -m eval.eval_classifier
```

## Notes
- **CopilotKit runs on OpenAI, not the backend.** The chat is served entirely by the Node
  runtime (`frontend/copilotkit-runtime.mjs`) using the OpenAI adapter; it gets the latest
  scan via `useCopilotReadable` and can trigger a scan via the `checkMyScreen` frontend
  action. (The dead Python remote-endpoint path in `backend/app/copilot.py` is unused.)
- **Redis 8 / RESP2.** `redis-py`'s `FT.SEARCH` parser returns 0 results under RESP3 on
  Redis 8, so both vector stores create their client with `protocol=2`. Don't remove that.
- **The "Check my screen" flow** hits `POST /api/v1/scans/scan` → the agent pipeline above.
  There is also a DB-backed multipart upload flow (`POST /api/v1/scans/` + WebSocket) used
  for persisted scan history.

## Demo script (2 min)
1. Open a fake phishing email on screen.
2. Click **Check my screen** in ScamGuard.
3. Watch the verdict, the **"Handled by … Specialist"** badge, reasons + safe actions.
4. Open the chat: "Is this a scam? What do I do?" (plain-language, scan-aware).
5. Show the **Weave** trace tree: `collect → research → TriageAgent → Specialist`.
6. Show the **Weave Evaluation** scorecard.

## Status / TODO
- [x] Multi-agent pipeline: redact ∥ collect → research → **triage → specialist**
- [x] Redis vector similarity search over a seeded scam + legit corpus (RESP2-fixed)
- [x] Web-search grounding in the research agent
- [x] Weave tracing + eval harness
- [x] CopilotKit chat (OpenAI runtime, plain-language / scan-aware)
- [x] Electron screenshot capture + scan UI + background detector pillars
- [ ] **True pixel redaction** (OCR + blur regions) — the redactor currently *describes* what to censor
- [ ] Wire the agent pipeline into the DB-backed `/scans/` flow (currently a one-shot classifier)
- [ ] Executable remediation actions, e.g. "block sender" via Composio (stretch)
- [ ] Cross-platform process scanner (the current one is Windows-only)
```
