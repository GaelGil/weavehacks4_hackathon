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
  handled_by?: string; // which specialist agent the triage routed to
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

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
