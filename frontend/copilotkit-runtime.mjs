// CopilotKit self-hosted runtime (Node).
//
// Architecture:  React (renderer) -> THIS runtime (:4000) -> FastAPI /copilotkit -> OpenAI Agents SDK
//
// The renderer's <CopilotKit runtimeUrl="http://localhost:4000/copilotkit"> talks to this
// server. This server uses an OpenAI adapter for the chat LLM and registers the FastAPI
// backend as a remote endpoint so the `askScamAdvisor` action runs your Agents-SDK advisor.
//
//   npm run copilot:runtime
//
// Requires OPENAI_API_KEY in the environment.
import dotenv from "dotenv";
import express from "express";
import {
  CopilotRuntime,
  OpenAIAdapter,
  copilotRuntimeNodeHttpEndpoint,
} from "@copilotkit/runtime";

// Reuse the backend's .env so the key lives in one place.
dotenv.config({ path: new URL("../backend/.env", import.meta.url) });

if (!process.env.OPENAI_API_KEY) {
  console.error(
    "OPENAI_API_KEY not found. Put it in backend/.env, or `export OPENAI_API_KEY=sk-...` before running."
  );
  process.exit(1);
}

const PORT = 4000;
const FASTAPI_REMOTE = "http://127.0.0.1:8000/copilotkit";

const app = express();

// Was hardcoded to "gpt-4o" (the priciest chat model). Now driven by OPENAI_MODEL
// (loaded from backend/.env above) so cost/quality is tuned in one place — and
// defaults to the cheap gpt-4o-mini if the var is somehow missing.
const serviceAdapter = new OpenAIAdapter({ model: process.env.OPENAI_MODEL || "gpt-4o-mini" });

const runtime = new CopilotRuntime({
  // Register the FastAPI Python endpoint so its actions/agents are available to the chat.
  remoteEndpoints: [{ url: FASTAPI_REMOTE }],
});

app.use("/copilotkit", (req, res, next) => {
  const handler = copilotRuntimeNodeHttpEndpoint({
    endpoint: "/copilotkit",
    runtime,
    serviceAdapter,
  });
  return handler(req, res, next);
});

app.listen(PORT, () => {
  console.log(`CopilotKit runtime on http://localhost:${PORT}/copilotkit`);
  console.log(`  -> bridging to FastAPI remote endpoint: ${FASTAPI_REMOTE}`);
});
