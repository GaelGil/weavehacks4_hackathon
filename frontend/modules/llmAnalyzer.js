const Anthropic = require('@anthropic-ai/sdk');

// W&B Weave: auto-instruments Anthropic SDK when initialized — init is called
// from main.js before this module is first used.
let weave;
try {
  weave = require('weave');
} catch (_) {
  // weave not installed yet — tracing disabled, detection still works
  weave = null;
}

const SYSTEM_PROMPT = `You are a scam detection assistant protecting elderly users.
Analyze the screenshot and respond ONLY with a JSON object (no markdown fences):
{
  "suspicious": true | false,
  "severity": "low" | "medium" | "critical",
  "reason": "brief one-sentence explanation",
  "detected": ["list", "of", "matched", "threat", "types"]
}
Threat types to detect:
- remote_desktop_software
- fake_tech_support_popup
- gift_card_request
- unusual_urgency_language
- password_request
- unfamiliar_remote_cursor
- suspicious_browser_warning
- fake_virus_alert
- cryptocurrency_scam
If nothing suspicious is found, return suspicious: false with an empty detected array.`;

let client;

function getClient() {
  if (!client) {
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) throw new Error('ANTHROPIC_API_KEY is not set');
    client = new Anthropic({ apiKey });
  }
  return client;
}

async function _analyzeScreen(base64Image) {
  const response = await getClient().messages.create({
    model: process.env.SCAMGUARD_LLM_MODEL || 'claude-opus-4-5',
    max_tokens: 300,
    system: SYSTEM_PROMPT,
    messages: [
      {
        role: 'user',
        content: [
          {
            type: 'image',
            source: { type: 'base64', media_type: 'image/png', data: base64Image },
          },
          { type: 'text', text: 'Analyze this screenshot for scam indicators.' },
        ],
      },
    ],
  });

  const text = response.content[0].text.trim();
  return JSON.parse(text);
}

// Wrap with weave.op if available so every call is traced in the W&B dashboard.
// weave.op captures: prompt, response JSON, model, token counts, latency.
const analyzeScreen = weave
  ? weave.op(_analyzeScreen, { name: 'scamguard.analyzeScreen' })
  : _analyzeScreen;

module.exports = { analyzeScreen };
