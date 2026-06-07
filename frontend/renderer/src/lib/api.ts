import type { ScanResult } from "../types";

const BACKEND = "http://127.0.0.1:8000/api/v1/scans";

export async function scanScreen(
  imageB64: string | null,
  contextText = "",
  source: "manual" | "interval" = "manual"
): Promise<ScanResult> {
  const res = await fetch(`${BACKEND}/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image_b64: imageB64, context_text: contextText, source }),
  });
  if (!res.ok) throw new Error(`Scan failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function askAdvisor(question: string, scan: ScanResult | null): Promise<string> {
  const res = await fetch(`${BACKEND}/advisor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, scan }),
  });
  if (!res.ok) throw new Error(`Advisor failed: ${res.status}`);
  const data = await res.json();
  return data.answer as string;
}

export async function health(): Promise<{ ok: boolean; redis: boolean }> {
  const res = await fetch(`${BACKEND}/health`);
  return res.json();
}
