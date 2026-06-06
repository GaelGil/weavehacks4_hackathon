import React from "react";
import ReactDOM from "react-dom/client";
import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-ui/styles.css";
import App from "./App";
import "./styles.css";

// The CopilotKit runtime (Node) bridges to the FastAPI /copilotkit endpoint.
// See frontend/copilotkit-runtime.mjs.
const COPILOT_RUNTIME_URL = "http://localhost:4000/copilotkit";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <CopilotKit runtimeUrl={COPILOT_RUNTIME_URL}>
      <App />
    </CopilotKit>
  </React.StrictMode>
);
