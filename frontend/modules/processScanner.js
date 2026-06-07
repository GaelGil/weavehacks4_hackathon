const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const BACKEND_URL = process.env.SCAMGUARD_BACKEND_URL || 'http://localhost:8000';

// Local file is the fallback when the backend is unreachable.
const localBlocklist = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/blocklist.json'), 'utf8')
);

let remoteAccessLower = localBlocklist.remote_access.map((p) => p.toLowerCase());
let suspiciousToolsLower = localBlocklist.suspicious_tools.map((p) => p.toLowerCase());
let allBadProcesses = new Set([...remoteAccessLower, ...suspiciousToolsLower]);

async function initialize() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/scans/config/threat-rules`);
    if (!res.ok) return;
    const rules = await res.json();
    remoteAccessLower = rules.remote_access.map((p) => p.toLowerCase());
    suspiciousToolsLower = rules.suspicious_tools.map((p) => p.toLowerCase());
    allBadProcesses = new Set([...remoteAccessLower, ...suspiciousToolsLower]);
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
  return 'suspicious_tool';
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

module.exports = { initialize, scanProcesses, reportDetections };
