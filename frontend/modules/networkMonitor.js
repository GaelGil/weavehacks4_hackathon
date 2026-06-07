const { session } = require('electron');
const { spawn, exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// 127.0.0.1, NOT localhost: on Windows, "localhost" resolves to the IPv6
// loopback ::1 first, and Docker Desktop/WSL2's port-forwarding for ::1 hangs
// indefinitely instead of refusing — every fetch() below would silently freeze.
const BACKEND_URL = process.env.SCAMGUARD_BACKEND_URL || 'http://127.0.0.1:8000';

// Local files are fallbacks when the backend is unreachable.
const localBankingDomains = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/banking-domains.json'), 'utf8')
);
const LOCAL_MALICIOUS_PATTERNS = [
  /\.(ru|cn)\/.*login/i,
  /paypal.*\.(?!paypal\.com)/i,
  /secure.*bank.*\.tk/i,
  /gift.?card/i,
  /microsoft.*support.*\d{10}/i,
  /apple.*security.*alert/i,
];

let bankingDomains = new Set(localBankingDomains);
let maliciousPatterns = LOCAL_MALICIOUS_PATTERNS;

async function initialize() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/scans/config/threat-rules`);
    if (!res.ok) return;
    const rules = await res.json();
    bankingDomains = new Set(rules.banking_domains);
    maliciousPatterns = rules.malicious_patterns.map((p) => new RegExp(p, 'i'));
    console.log('[networkMonitor] loaded threat rules from backend');
  } catch (_) {
    console.warn('[networkMonitor] backend unreachable — using local threat rules');
  }
}

async function reportNetworkEvent(event) {
  try {
    await fetch(`${BACKEND_URL}/api/v1/scans/detections/network`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event),
    });
  } catch (_) {
    // Fire-and-forget — never block the local alert dispatch
  }
}

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

  for (const pattern of maliciousPatterns) {
    if (pattern.test(rawUrl)) {
      return { type: 'MALICIOUS_URL', severity: 'critical', url: rawUrl };
    }
  }

  return null;
}

function startWebRequestMonitor(onAlert) {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const match = checkUrl(details.url);
    if (match) {
      reportNetworkEvent(match); // persist to backend
      onAlert(match);
    }
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
            const alert = { type: 'BANKING_SITE', severity: 'info', hostname, source: 'sidecar' };
            reportNetworkEvent(alert); // persist to backend
            onAlert(alert);
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

// ---------------------------------------------------------------------------
// Active TCP connection scan — find established external connections by process
// ---------------------------------------------------------------------------

// Strip IPv4-mapped IPv6 prefix (::ffff:1.2.3.4 → 1.2.3.4) then reject
// loopback, RFC-1918, link-local, and unspecified addresses.
function isExternalIp(addr) {
  if (!addr) return false;
  const ip = addr.replace(/^::ffff:/i, '');
  return !/^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.0\.0\.0$|::1$|fe80:)/i.test(ip);
}

// Returns every established TCP connection whose remote IP is external.
// Builds a PID→name map first (one Get-Process call) then joins — avoids
// the O(n) per-connection Get-Process call that makes this noticeably slow.
function scanActiveConnections() {
  return new Promise((resolve) => {
    const cmd =
      'powershell.exe -NoProfile -NonInteractive -Command "' +
      '$pm=@{};' +
      'Get-Process -EA SilentlyContinue|ForEach-Object{$pm[$_.Id]=$_.Name};' +
      'Get-NetTCPConnection -State Established -EA SilentlyContinue|' +
      'ForEach-Object{[PSCustomObject]@{r=$_.RemoteAddress;rp=$_.RemotePort;' +
      "pid=$_.OwningProcess;n=if($pm[$_.OwningProcess]){$pm[$_.OwningProcess]}else{'?'}}}|" +
      'ConvertTo-Json -Compress"';

    exec(cmd, { timeout: 15000 }, (err, stdout) => {
      if (err) { resolve([]); return; }
      let rows;
      try {
        rows = JSON.parse(stdout.trim());
        if (!Array.isArray(rows)) rows = rows ? [rows] : [];
      } catch (_) { resolve([]); return; }

      resolve(
        rows
          .filter((c) => c && isExternalIp(c.r))
          .map((c) => ({
            remoteAddress: c.r,
            remotePort: Number(c.rp),
            pid: Number(c.pid),
            processName: c.n || '?',
          }))
      );
    });
  });
}

module.exports = { initialize, startWebRequestMonitor, startSniffer, stopSniffer, checkUrl, scanActiveConnections };
