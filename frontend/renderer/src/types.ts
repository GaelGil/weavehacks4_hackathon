export type Verdict = "safe" | "suspicious" | "scam";

export interface RedactionResult {
  contains_sensitive: boolean;
  sensitive_kinds: string[];
  redaction_note: string;
}

export interface SimilarScam {
  text: string;
  score: number;
  category: string;
}

export interface SuggestedAction {
  label: string;
  detail: string;
  severity: "info" | "warn" | "danger";
}

export interface ScanResult {
  verdict: Verdict;
  risk_score: number;
  reasons: string[];
  redaction: RedactionResult;
  similar_scams: SimilarScam[];
  suggested_actions: SuggestedAction[];
  advice: string;
}

// Exposed from preload.js via contextBridge.
export interface ElectronAPI {
  getAppVersion: () => Promise<string>;
  captureScreen: () => Promise<string>; // base64 PNG (no data: prefix)
  checkForUpdates: () => Promise<{ success: boolean; error?: string }>;
  downloadUpdate: () => Promise<{ success: boolean; error?: string }>;
  installUpdate: () => void;
  onUpdateStatus: (cb: (data: any) => void) => () => void;
}

// Mirrors the alerts built by frontend/modules/alertManager.js (buildAlert).
export interface ScamGuardAlert {
  type: string;
  severity: "critical" | "warning" | "info";
  title: string;
  message: string;
  timestamp: number;
  dismissable?: boolean;
  autoDismissMs?: number;
  data?: unknown;
}

// Exposed from preload.js via contextBridge (the detection-layer API).
export interface ScamGuardAPI {
  onAlert: (cb: (alert: ScamGuardAlert) => void) => () => void;
  onDashboardAlert: (cb: (alert: ScamGuardAlert) => void) => () => void;
  dismissAlert: () => void;
  getProtectionStatus: () => Promise<unknown>;
  getAlertHistory: () => Promise<ScamGuardAlert[]>;
  toggleDetector: (name: string, enabled: boolean) => Promise<unknown>;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
    scamGuard: ScamGuardAPI;
  }
}
