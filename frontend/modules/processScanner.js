const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const blocklist = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/blocklist.json'), 'utf8')
);
const remoteAccessLower = blocklist.remote_access.map((p) => p.toLowerCase());
const suspiciousToolsLower = blocklist.suspicious_tools.map((p) => p.toLowerCase());
const allBadProcesses = new Set([...remoteAccessLower, ...suspiciousToolsLower]);

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

module.exports = { scanProcesses };
