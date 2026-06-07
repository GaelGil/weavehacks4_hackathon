const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// 127.0.0.1, NOT localhost: on Windows, "localhost" resolves to the IPv6
// loopback ::1 first, and Docker Desktop/WSL2's port-forwarding for ::1 hangs
// indefinitely instead of refusing — every fetch() below would silently freeze.
const BACKEND_URL = process.env.SCAMGUARD_BACKEND_URL || 'http://127.0.0.1:8000';

// Local file is the fallback when the backend is unreachable.
const localBlocklist = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/blocklist.json'), 'utf8')
);

const bankingDomains = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/banking-domains.json'), 'utf8')
);

let remoteAccessLower = localBlocklist.remote_access.map((p) => p.toLowerCase());
let suspiciousToolsLower = localBlocklist.suspicious_tools.map((p) => p.toLowerCase());
let screenCaptureLower = localBlocklist.screen_capture.map((p) => p.toLowerCase());
let allBadProcesses = new Set([...remoteAccessLower, ...suspiciousToolsLower, ...screenCaptureLower]);

async function initialize() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/scans/config/threat-rules`);
    if (!res.ok) return;
    const rules = await res.json();
    remoteAccessLower = rules.remote_access.map((p) => p.toLowerCase());
    suspiciousToolsLower = rules.suspicious_tools.map((p) => p.toLowerCase());
    screenCaptureLower = (rules.screen_capture || []).map((p) => p.toLowerCase());
    allBadProcesses = new Set([...remoteAccessLower, ...suspiciousToolsLower, ...screenCaptureLower]);
    console.log('[processScanner] loaded threat rules from backend');
  } catch (_) {
    console.warn('[processScanner] backend unreachable — using local blocklist');
  }
}

async function reportDetections(detections) {
  if (!detections.length) return;
  try {
    await fetch(`${BACKEND_URL}/api/v1/scans/detections/processes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ processes: detections }),
    });
  } catch (_) {
    // Fire-and-forget — never block the local detection loop
  }
}

function getCategoryForProcess(nameLower) {
  if (remoteAccessLower.includes(nameLower)) return 'remote_access';
  if (screenCaptureLower.includes(nameLower)) return 'screen_capture';
  return 'suspicious_tool';
}

function isSuspiciousProcess(name) {
  return allBadProcesses.has(name.toLowerCase());
}

function parseWmicOutput(stdout) {
  const found = [];
  const lines = stdout.trim().split('\n').slice(2); // skip header rows
  for (const line of lines) {
    const parts = line.trim().split(',');
    if (parts.length < 3) continue;
    const name = parts[1].trim();
    const pid = parts[2].trim();
    if (allBadProcesses.has(name.toLowerCase())) {
      found.push({ name, pid, category: getCategoryForProcess(name.toLowerCase()) });
    }
  }
  return found;
}

function parsePowerShellOutput(stdout) {
  const found = [];
  let procs;
  try {
    procs = JSON.parse(stdout);
    if (!Array.isArray(procs)) procs = [procs];
  } catch (_) {
    return found;
  }
  for (const proc of procs) {
    const name = (proc.Name || '').trim();
    const pid = String(proc.Id || proc.PID || '');
    if (allBadProcesses.has(name.toLowerCase())) {
      found.push({ name, pid, category: getCategoryForProcess(name.toLowerCase()) });
    }
  }
  return found;
}

function scanWithWmic() {
  return new Promise((resolve, reject) => {
    exec('wmic process get Name,ProcessId /FORMAT:CSV', { timeout: 8000 }, (err, stdout) => {
      if (err) return reject(err);
      resolve(parseWmicOutput(stdout));
    });
  });
}

// PowerShell fallback for Windows 11 24H2+ where WMIC is removed
function scanWithPowerShell() {
  return new Promise((resolve, reject) => {
    const cmd =
      'powershell.exe -NoProfile -NonInteractive -Command "Get-Process | Select-Object Name,Id | ConvertTo-Json -Compress"';
    exec(cmd, { timeout: 10000 }, (err, stdout) => {
      if (err) return reject(err);
      resolve(parsePowerShellOutput(stdout));
    });
  });
}

async function scanProcesses() {
  try {
    return await scanWithWmic();
  } catch (_) {
    // WMIC unavailable (Win11 24H2+) — fall back to PowerShell
    return await scanWithPowerShell();
  }
}

// ---------------------------------------------------------------------------
// Browser window title scanning — detect banking sites open in any browser
// ---------------------------------------------------------------------------

// Returns the first banking match found across all open browser windows, or null.
// Match strategy: check the lowercased window title for the full domain (e.g.
// "chase.com") OR the brand name as a whole word (e.g. \bchase\b). The brand
// approach catches "Chase Online Banking - Google Chrome"; the full-domain
// approach catches tabs where Chrome shows "chase.com" in the title.
function matchesBankingTitle(title, domain) {
  const lower = title.toLowerCase();
  if (lower.includes(domain)) return true;
  const brand = domain.split('.')[0];
  return new RegExp(`\\b${brand}\\b`).test(lower);
}

function scanBrowserTitles() {
  return new Promise((resolve) => {
    const cmd =
      'powershell.exe -NoProfile -NonInteractive -Command ' +
      '"Get-Process | Where-Object MainWindowTitle | Select-Object Name,MainWindowTitle | ConvertTo-Json -Compress"';
    exec(cmd, { timeout: 8000 }, (err, stdout) => {
      if (err) { resolve(null); return; }
      let procs;
      try {
        procs = JSON.parse(stdout.trim());
        if (!Array.isArray(procs)) procs = procs ? [procs] : [];
      } catch (_) { resolve(null); return; }

      for (const proc of procs) {
        const title = proc.MainWindowTitle || '';
        for (const domain of bankingDomains) {
          if (matchesBankingTitle(title, domain)) {
            return resolve({ domain, windowTitle: title, browser: proc.Name });
          }
        }
      }
      resolve(null);
    });
  });
}

module.exports = { initialize, scanProcesses, reportDetections, scanBrowserTitles, isSuspiciousProcess, getCategoryForProcess };
