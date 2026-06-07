import { useState } from "react";
import { useCopilotAction } from "@copilotkit/react-core";
import type { ScanResult } from "../types";
import { scanScreen } from "../lib/api";

interface Props {
  scan: ScanResult | null;
  onScan: (r: ScanResult) => void;
}

const verdictMeta: Record<string, { label: string; cls: string; emoji: string }> = {
  safe: { label: "Looks safe", cls: "safe", emoji: "✅" },
  suspicious: { label: "Be careful", cls: "warn", emoji: "⚠️" },
  scam: { label: "Likely a scam", cls: "danger", emoji: "🚨" },
};

// "PhishingEmailSpecialist" -> "Phishing Email Specialist"
function formatSpecialist(name: string): string {
  return name.replace(/([a-z])([A-Z])/g, "$1 $2");
}

export default function ScanPanel({ scan, onScan }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runScan() {
    setLoading(true);
    setError(null);
    try {
      const imageB64 = await window.electronAPI.captureScreen();
      const result = await scanScreen(imageB64, "", "manual");
      onScan(result);
    } catch (e: any) {
      setError(e?.message ?? "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  // Let the CopilotKit chat trigger a scan too ("check my screen").
  useCopilotAction({
    name: "checkMyScreen",
    description: "Capture and scan the user's current screen for scams or harmful content.",
    parameters: [],
    handler: async () => {
      await runScan();
      return "Scan complete — see the results panel.";
    },
  });

  const meta = scan ? verdictMeta[scan.verdict] : null;

  return (
    <div className="panel">
      <button className="scan-btn" onClick={runScan} disabled={loading}>
        {loading ? "Scanning your screen…" : "🔍  Check my screen"}
      </button>
      {error && <div className="error">{error}</div>}

      {scan && meta && (
        <div className={`result ${meta.cls}`}>
          <div className="verdict">
            <span className="emoji">{meta.emoji}</span>
            <div>
              <div className="verdict-label">{meta.label}</div>
              <div className="risk">risk {Math.round(scan.risk_score * 100)}%</div>
            </div>
          </div>

          {scan.handled_by && (
            <div className="handled-by">🔎 Handled by {formatSpecialist(scan.handled_by)}</div>
          )}

          {scan.advice && <p className="advice">{scan.advice}</p>}

          {scan.reasons.length > 0 && (
            <ul className="reasons">
              {scan.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}

          {scan.suggested_actions.length > 0 && (
            <div className="actions">
              {scan.suggested_actions.map((a, i) => (
                <div key={i} className={`action ${a.severity}`}>
                  <strong>{a.label}</strong>
                  <span>{a.detail}</span>
                </div>
              ))}
            </div>
          )}

          {scan.similar_scams.length > 0 && (
            <div className="similar">
              <h4>Similar known scams</h4>
              {scan.similar_scams.map((s, i) => (
                <div key={i} className="similar-item">
                  <span className="score">{Math.round(s.score * 100)}%</span> {s.text}
                </div>
              ))}
            </div>
          )}

          {scan.redaction.contains_sensitive && (
            <div className="privacy-note">
              🔒 Sensitive info detected on screen ({scan.redaction.sensitive_kinds.join(", ")}) —
              handled privately.
            </div>
          )}
        </div>
      )}

      {!scan && !loading && (
        <p className="hint">
          Feeling unsure about something on your screen? Click the button and I'll check it for you.
        </p>
      )}
    </div>
  );
}
