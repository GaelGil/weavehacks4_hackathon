const { session } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const bankingDomains = new Set(
  JSON.parse(fs.readFileSync(path.join(__dirname, '../resources/banking-domains.json'), 'utf8'))
);

const MALICIOUS_PATTERNS = [
  /\.(ru|cn)\/.*login/i,
  /paypal.*\.(?!paypal\.com)/i,
  /secure.*bank.*\.tk/i,
  /gift.?card/i,
  /microsoft.*support.*\d{10}/i,
  /apple.*security.*alert/i,
];

function normalizeHostname(hostname) {
  return hostname.replace(/^www\./, '').toLowerCase();
}

function checkUrl(rawUrl) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch (_) {
    return null;
  }

  const hostname = normalizeHostname(url.hostname);

  if (bankingDomains.has(hostname)) {
    return { type: 'BANKING_SITE', severity: 'info', hostname };
  }

  for (const pattern of MALICIOUS_PATTERNS) {
    if (pattern.test(rawUrl)) {
      return { type: 'MALICIOUS_URL', severity: 'critical', url: rawUrl };
    }
  }

  return null;
}

function startWebRequestMonitor(onAlert) {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const match = checkUrl(details.url);
    if (match) onAlert(match);
    callback({ cancel: false }); // alert-only, never block
  });
}

// ---------------------------------------------------------------------------
// Go sidecar bridge — system-wide DNS via Npcap (optional, requires sniffer.exe)
// ---------------------------------------------------------------------------

let snifferProcess = null;
let snifferRestartTimer = null;

function startSniffer(onAlert) {
  const snifferPath = process.env.SCAMGUARD_SIDECAR_PATH
    || path.join(process.resourcesPath || path.join(__dirname, '../sidecar'), 'sniffer.exe');

  if (!fs.existsSync(snifferPath)) return; // sidecar not bundled in dev — skip silently

  snifferProcess = spawn(snifferPath, [], { stdio: ['ignore', 'pipe', 'pipe'] });

  let buffer = '';
  snifferProcess.stdout.on('data', (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      try {
        const event = JSON.parse(line);
        if (event.type === 'dns_query') {
          const hostname = normalizeHostname(event.hostname);
          if (bankingDomains.has(hostname)) {
            onAlert({ type: 'BANKING_SITE', severity: 'info', hostname, source: 'sidecar' });
          }
        }
      } catch (_) {}
    }
  });

  snifferProcess.on('exit', (code) => {
    console.warn(`[networkMonitor] sniffer exited (code ${code}) — restarting in 5s`);
    snifferRestartTimer = setTimeout(() => startSniffer(onAlert), 5000);
  });
}

function stopSniffer() {
  clearTimeout(snifferRestartTimer);
  if (snifferProcess) {
    snifferProcess.removeAllListeners();
    snifferProcess.kill();
    snifferProcess = null;
  }
}

module.exports = { startWebRequestMonitor, startSniffer, stopSniffer, checkUrl };
