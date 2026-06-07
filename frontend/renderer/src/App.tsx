import { useEffect, useState } from "react";
import { CopilotSidebar } from "@copilotkit/react-ui";
import { useCopilotReadable } from "@copilotkit/react-core";
import ScanPanel from "./components/ScanPanel";
import type { ScamGuardAlert, ScanResult } from "./types";
import { health } from "./lib/api";

const MAX_VISIBLE_ALERTS = 5;

export default function App() {
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [version, setVersion] = useState("--");
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [alerts, setAlerts] = useState<(ScamGuardAlert & { id: string })[]>([]);

  useEffect(() => {
    window.electronAPI?.getAppVersion().then(setVersion).catch(() => {});
    health()
      .then((h) => setBackendOk(h.ok))
      .catch(() => setBackendOk(false));
  }, []);

  // Mirror live detector alerts (scam screens, remote-access tools, banking sites...)
  // into the dashboard as dismissible toasts — the same events the full-screen overlay
  // shows, but visible here too when the overlay isn't focused or has been dismissed.
  useEffect(() => {
    const dismissAfter = (id: string, ms: number) =>
      setTimeout(() => setAlerts((prev) => prev.filter((a) => a.id !== id)), ms);

    const unsubscribe = window.scamGuard?.onDashboardAlert((alert) => {
      const id = `${alert.type}-${alert.timestamp}`;
      setAlerts((prev) => [{ ...alert, id }, ...prev].slice(0, MAX_VISIBLE_ALERTS));
      if (alert.autoDismissMs) dismissAfter(id, alert.autoDismissMs);
    });

    return unsubscribe;
  }, []);

  const dismissAlert = (id: string) =>
    setAlerts((prev) => prev.filter((a) => a.id !== id));

  // Make the latest scan visible to the CopilotKit advisor chat.
  useCopilotReadable({
    description: "The latest ScamGuard screen-scan result for the user's computer.",
    value: scan ?? "No scan has been run yet.",
  });

  return (
    <div className="layout">
      {alerts.length > 0 && (
        <div className="alert-stack">
          {alerts.map((alert) => (
            <div key={alert.id} className={`toast-alert ${alert.severity}`}>
              <div className="toast-alert-body">
                <strong>{alert.title}</strong>
                <span>{alert.message}</span>
              </div>
              {alert.dismissable !== false && (
                <button
                  className="toast-dismiss"
                  aria-label="Dismiss alert"
                  onClick={() => dismissAlert(alert.id)}
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <header>
        <div className="brand">
          <span className="logo">🛡️</span>
          <h1>ScamGuard</h1>
        </div>
        <div className="status">
          <span className={`dot ${backendOk ? "ok" : backendOk === false ? "bad" : ""}`} />
          {backendOk === null ? "connecting…" : backendOk ? "protected" : "backend offline"}
          <span className="version">v{version}</span>
        </div>
      </header>

      <main>
        <ScanPanel scan={scan} onScan={setScan} />
      </main>

      <CopilotSidebar
        labels={{
          title: "Ask ScamGuard",
          initial:
            "Hi! I can check your screen for scams. Click \"Check my screen\", or ask me a question like \"Is this email safe?\"",
        }}
      />
    </div>
  );
}
