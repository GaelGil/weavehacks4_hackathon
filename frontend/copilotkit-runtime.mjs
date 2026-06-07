// CopilotKit self-hosted runtime (Node).
//
// Architecture:  React (renderer) -> THIS runtime (:4000) -> OpenAI
//
// The renderer's <CopilotKit runtimeUrl="http://localhost:4000/copilotkit"> talks to this
// server, which uses an OpenAI adapter for the chat LLM. The chat gets scam-scan context
// and the "checkMyScreen" action from the React app (useCopilotReadable / useCopilotAction).
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

const app = express();

// Allow the Vite renderer (http://localhost:5173) to call this runtime cross-origin,
// including the browser's CORS preflight (OPTIONS).
app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "*");
  res.header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.header("Access-Control-Allow-Headers", "*");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

// Chat is powered directly by OpenAI. No backend remote endpoint — the scam-scan
// context and the "checkMyScreen" action come from the React app.
const serviceAdapter = new OpenAIAdapter({ model: "gpt-4o" });
const runtime = new CopilotRuntime();

// Mount at root so the request path "/copilotkit" actually reaches the runtime's
// GraphQL endpoint. Mounting under app.use("/copilotkit", ...) strips the path and 404s.
const handler = copilotRuntimeNodeHttpEndpoint({
  endpoint: "/copilotkit",
  runtime,
  serviceAdapter,
});
app.use(handler);

app.listen(PORT, () => {
  console.log(`CopilotKit runtime on http://localhost:${PORT}/copilotkit (OpenAI chat)`);
});
