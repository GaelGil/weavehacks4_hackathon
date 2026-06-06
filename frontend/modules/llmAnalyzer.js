const OpenAI = require('openai');

let weave;
try {
  weave = require('weave');
} catch (_) {
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
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) throw new Error('OPENAI_API_KEY is not set');
    client = new OpenAI({ apiKey });
  }
  return client;
}

async function _analyzeScreen(base64Image) {
  const response = await getClient().chat.completions.create({
    model: process.env.SCAMGUARD_LLM_MODEL || 'gpt-4o',
    max_tokens: 300,
    messages: [
      { role: 'system', content: SYSTEM_PROMPT },
      {
        role: 'user',
        content: [
          {
            type: 'image_url',
            image_url: { url: `data:image/png;base64,${base64Image}` },
          },
          { type: 'text', text: 'Analyze this screenshot for scam indicators.' },
        ],
      },
    ],
  });

  const text = response.choices[0].message.content.trim();
  return JSON.parse(text);
}

const analyzeScreen = weave
  ? weave.op(_analyzeScreen, { name: 'scamguard.analyzeScreen' })
  : _analyzeScreen;

module.exports = { analyzeScreen };
