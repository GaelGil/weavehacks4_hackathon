// Screen analysis delegated entirely to the backend pipeline.
// The frontend captures the screenshot; all LLM reasoning runs server-side.

const BACKEND_URL = process.env.SCAMGUARD_BACKEND_URL || 'http://localhost:8000';

async function analyzeScreen(base64Image) {
  const res = await fetch(`${BACKEND_URL}/api/v1/scans/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image_b64: base64Image, context_text: '', source: 'interval' }),
  });

  if (!res.ok) throw new Error(`Backend scan failed: ${res.status}`);

  const data = await res.json();

  // Normalize the rich ScanResult to the shape callers expect
  return {
    suspicious: data.verdict !== 'safe',
    severity: data.risk_score > 0.7 ? 'critical' : data.risk_score > 0.4 ? 'medium' : 'low',
    reason: data.advice || (data.reasons && data.reasons[0]) || '',
    detected: data.reasons || [],
    verdict: data.verdict,
    risk_score: data.risk_score,
  };
}

module.exports = { analyzeScreen };
