# ScamGuard — Windows Observability Layer
## Systems Architecture & Implementation Guide
*Electron + Node.js | Windows Platform | v1.0*

---

# 1. Overview

ScamGuard is an Electron-based desktop application that provides real-time protection for elderly users by running a continuous observability layer on their Windows PC. The system uses four detection pillars: LLM-powered screen analysis, process scanning, network traffic monitoring, and banking site detection. Alerts are surfaced as non-intrusive overlays designed for clarity at large font sizes.

## 1.1 System Architecture

The application is structured around Electron's two-process model:

| Component | Responsibility |
|---|---|
| **Main Process (Node.js)** | Screen capture, process scanning, network sniffing, LLM API calls, alert logic, sidecar management |
| **Renderer Process (Chromium)** | Alert overlay UI, settings panel, status dashboard, IPC message handling |
| **Native Sidecar (Go binary)** | System-wide packet capture via WinPcap/Npcap, DNS monitoring, runs with elevated privileges |
| **LLM API (Claude / GPT-4o)** | Vision analysis of screen snapshots, classification of suspicious UI patterns |

## 1.2 Prerequisites

| Requirement | Notes |
|---|---|
| **Node.js** | v18 or later (LTS recommended) |
| **Electron** | v28 or later |
| **Npcap** | Required for system-wide packet capture on Windows — install with WinPcap compatibility mode enabled |
| **Go** | v1.21+ if building the sniffer sidecar from source |
| **Visual Studio Build Tools** | Required by native npm modules on Windows (node-gyp) |
| **Anthropic / OpenAI API Key** | For LLM screen analysis |

> **⚠️ Elevated Privileges Required**
> The network sniffer sidecar must run as Administrator to capture raw packets on Windows. Request elevation at install time via the NSIS/WiX installer script, not at runtime, to avoid repeated UAC prompts.

---

# 2. Project Setup

## 2.1 Initialize the Electron Project

Run the following commands in your development terminal to scaffold the project:

```bash
mkdir scamguard && cd scamguard
npm init -y
npm install electron electron-builder
npm install node-fetch @anthropic-ai/sdk
```

Install native dependencies for Windows process listing:

```bash
npm install windows-process-list
# Requires Visual Studio Build Tools — run in a VS Developer Command Prompt
```

## 2.2 Project Structure

```
scamguard/
  main.js                   ← Electron main process entry point
  preload.js                ← Context bridge for IPC
  renderer/
    overlay.html            ← Alert overlay window
    dashboard.html          ← Status/settings UI
  modules/
    screenCapture.js        ← Screen snapshot logic
    processScanner.js       ← Task manager scanning
    networkMonitor.js       ← webRequest + sidecar bridge
    llmAnalyzer.js          ← LLM API integration
    alertManager.js         ← Alert routing and severity
  sidecar/
    sniffer.go              ← Go packet capture binary source
    sniffer.exe             ← Pre-built for distribution
  resources/
    blocklist.json          ← Known-bad process names
    banking-domains.json    ← Banking site list
```

## 2.3 Electron Main Process Boilerplate

The `main.js` file bootstraps the app and creates the always-on-top overlay window:

```javascript
// main.js
const { app, BrowserWindow, desktopCapturer, session, ipcMain } = require('electron');
const path = require('path');

// Always-on-top transparent alert overlay
function createOverlayWindow() {
  const overlay = new BrowserWindow({
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    fullscreen: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true
    }
  });
  overlay.loadFile('renderer/overlay.html');
  overlay.setIgnoreMouseEvents(true, { forward: true });
  return overlay;
}
```

> **ℹ️ setIgnoreMouseEvents**
> Passing `{ forward: true }` allows mouse events to pass through the overlay to the underlying application, so the user can still interact with their desktop normally. Remove this flag only when you need the user to interact with an alert.

---

# 3. Screen Snapshot & LLM Vision Analysis

## 3.1 How It Works

Electron's `desktopCapturer` API captures a PNG thumbnail of the primary display. The image is base64-encoded and sent to an LLM vision endpoint (Claude or GPT-4o) along with a structured system prompt. The model returns a JSON verdict classifying whether anything suspicious is visible.

## 3.2 Capturing the Screen

```javascript
// modules/screenCapture.js
const { desktopCapturer } = require('electron');

async function captureScreen() {
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: { width: 1920, height: 1080 }
  });
  if (!sources.length) throw new Error('No screen sources found');
  // Returns base64 PNG — strip the data URI prefix for API upload
  const dataUrl = sources[0].thumbnail.toDataURL();
  return dataUrl.split(',')[1]; // raw base64
}

module.exports = { captureScreen };
```

## 3.3 LLM Analysis Module

The analyzer sends the screenshot to Claude with a system prompt tuned for scam detection:

```javascript
// modules/llmAnalyzer.js
const Anthropic = require('@anthropic-ai/sdk');
const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const SYSTEM_PROMPT = `You are a scam detection assistant. Analyze the
screenshot and respond ONLY with a JSON object:
{
  "suspicious": true | false,
  "severity": "low" | "medium" | "critical",
  "reason": "brief explanation",
  "detected": ["list", "of", "threat", "types"]
}
Threat types to detect: remote_desktop_software, fake_tech_support_popup,
gift_card_request, unusual_urgency_language, password_request,
unfamiliar_remote_cursor, suspicious_browser_warning.`;

async function analyzeScreen(base64Image) {
  const response = await client.messages.create({
    model: 'claude-opus-4-5',
    max_tokens: 300,
    system: SYSTEM_PROMPT,
    messages: [{
      role: 'user',
      content: [{
        type: 'image',
        source: { type: 'base64', media_type: 'image/png', data: base64Image }
      }, {
        type: 'text', text: 'Analyze this screenshot for scam indicators.'
      }]
    }]
  });
  return JSON.parse(response.content[0].text);
}

module.exports = { analyzeScreen };
```

## 3.4 Polling Interval

Schedule screen captures at a configurable interval. 15 seconds is a good default — frequent enough to catch evolving scam screens, infrequent enough to keep API costs low.

```javascript
// In main.js — start the polling loop
const { captureScreen } = require('./modules/screenCapture');
const { analyzeScreen } = require('./modules/llmAnalyzer');

setInterval(async () => {
  try {
    const image = await captureScreen();
    const result = await analyzeScreen(image);
    if (result.suspicious) {
      overlayWindow.webContents.send('show-alert', {
        type: 'SCREEN_ANALYSIS',
        ...result
      });
    }
  } catch (err) {
    console.error('Screen analysis error:', err.message);
  }
}, 15000); // 15 seconds
```

> **⚠️ Privacy Consideration**
> Screenshots are sent to a third-party API. Clearly disclose this in your onboarding flow and privacy policy. For higher-privacy deployments, consider running a local vision model via llama.cpp or Ollama as a sidecar instead.

## 3.5 Tuning Parameters

| Parameter | Default | Notes |
|---|---|---|
| **Polling interval** | 15 seconds | Balance between responsiveness and API cost |
| **Image resolution** | 1920×1080 | Sufficient for text detection; reduce to 1280×720 to lower token count |
| **Max tokens** | 300 | JSON responses are short; keeps latency under 1.5s |
| **Model** | claude-opus-4-5 | Best vision accuracy; swap to haiku for cost savings |

---

# 4. Process Scanner (Task Manager)

## 4.1 How It Works

The process scanner enumerates all running Windows processes every 10 seconds and compares them against a blocklist of known-bad applications commonly used in tech support scams. It uses WMIC via `child_process` for structured output, with a PowerShell fallback for Windows 11 24H2+.

## 4.2 Blocklist

Maintain a JSON file of known-bad process names at `resources/blocklist.json`:

```json
{
  "remote_access": [
    "AnyDesk.exe", "TeamViewer.exe", "ScreenConnect.exe",
    "LogMeIn.exe", "Supremo.exe", "RemotePC.exe",
    "UltraVNC.exe", "RealVNC.exe", "TightVNC.exe",
    "GoToMeeting.exe", "ShowMyPC.exe", "Ammyy.exe"
  ],
  "suspicious_tools": [
    "ProcessHacker.exe", "autoruns.exe", "procexp.exe"
  ]
}
```

## 4.3 Scanner Implementation

```javascript
// modules/processScanner.js
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const blocklist = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/blocklist.json'))
);
const allBadProcesses = [
  ...blocklist.remote_access,
  ...blocklist.suspicious_tools
].map(p => p.toLowerCase());

function scanProcesses() {
  return new Promise((resolve, reject) => {
    // Use WMIC for reliable structured output on all Windows versions
    exec('wmic process get Name,ProcessId /FORMAT:CSV', (err, stdout) => {
      if (err) return reject(err);
      const lines = stdout.trim().split('\n').slice(2);
      const found = [];
      for (const line of lines) {
        const parts = line.trim().split(',');
        if (parts.length < 3) continue;
        const name = parts[1].toLowerCase().trim();
        const pid = parts[2].trim();
        if (allBadProcesses.includes(name)) {
          found.push({ name: parts[1], pid,
            category: getCategoryForProcess(name) });
        }
      }
      resolve(found);
    });
  });
}

function getCategoryForProcess(name) {
  if (blocklist.remote_access.map(p => p.toLowerCase()).includes(name))
    return 'remote_access';
  return 'suspicious_tool';
}

module.exports = { scanProcesses };
```

> **ℹ️ WMIC Deprecation**
> WMIC is deprecated in Windows 11 24H2+. Add a fallback using PowerShell: `powershell.exe -Command "Get-Process | Select-Object Name,Id | ConvertTo-Json"` for forward compatibility.

## 4.4 Wiring up the Scan Loop

```javascript
// In main.js
const { scanProcesses } = require('./modules/processScanner');

setInterval(async () => {
  const found = await scanProcesses();
  for (const proc of found) {
    overlayWindow.webContents.send('show-alert', {
      type: 'REMOTE_ACCESS_TOOL',
      severity: 'critical',
      process: proc
    });
  }
}, 10000); // 10 seconds
```

---

# 5. Network Monitoring

## 5.1 Two-Layer Approach

Network monitoring operates at two levels:

- **Layer 1 — Electron `webRequest`**: Intercepts HTTP/S requests made within Electron's own browser windows. Zero configuration, works immediately.
- **Layer 2 — Go sidecar with Npcap**: Captures system-wide DNS queries and TCP connections from any app on the machine, including Chrome, Edge, and native applications.

## 5.2 Layer 1 — Electron webRequest Interceptor

```javascript
// modules/networkMonitor.js
const { session } = require('electron');
const fs = require('fs');
const path = require('path');

const bankingDomains = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../resources/banking-domains.json'))
);

const MALICIOUS_PATTERNS = [
  /\.(ru|cn)\/.*login/i,
  /paypal.*\.(?!paypal\.com)/i,
  /secure.*bank.*\.tk/i,
  /gift.?card/i,
];

function startWebRequestMonitor(overlayWindow) {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    try {
      const url = new URL(details.url);
      const hostname = url.hostname.replace(/^www\./, '');

      // Banking site detection
      if (bankingDomains.includes(hostname)) {
        overlayWindow.webContents.send('show-alert', {
          type: 'BANKING_SITE',
          severity: 'info',
          hostname
        });
      }

      // Malicious URL pattern detection
      for (const pattern of MALICIOUS_PATTERNS) {
        if (pattern.test(details.url)) {
          overlayWindow.webContents.send('show-alert', {
            type: 'MALICIOUS_URL',
            severity: 'critical',
            url: details.url
          });
          break;
        }
      }
    } catch (_) {}
    callback({ cancel: false }); // never block — only alert
  });
}

module.exports = { startWebRequestMonitor };
```

## 5.3 Banking Domains List

Maintain `resources/banking-domains.json` as a flat array of hostnames:

```json
[
  "chase.com", "bankofamerica.com", "wellsfargo.com",
  "citibank.com", "usbank.com", "capitalone.com",
  "tdbank.com", "pnc.com", "schwab.com",
  "fidelity.com", "vanguard.com", "etrade.com",
  "paypal.com", "venmo.com", "zelle.com"
]
```

## 5.4 Layer 2 — Go Sniffer Sidecar

The Go sidecar uses `gopacket` with Npcap to capture system-wide DNS traffic. It streams JSON events to stdout, which the Electron main process reads via `child_process`.

First, initialize the Go module:

```bash
cd sidecar
go mod init scamguard/sniffer
go get github.com/google/gopacket
go get github.com/google/gopacket/pcap
```

Then write the sniffer:

```go
// sidecar/sniffer.go
package main

import (
  "encoding/json"
  "fmt"
  "log"
  "github.com/google/gopacket"
  "github.com/google/gopacket/layers"
  "github.com/google/gopacket/pcap"
)

type NetworkEvent struct {
  Type     string `json:"type"`
  Hostname string `json:"hostname"`
  SrcIP    string `json:"src_ip"`
}

func main() {
  // List available devices: pcap.FindAllDevs()
  // Replace ADAPTER with the device name from FindAllDevs
  handle, err := pcap.OpenLive(`\Device\NPF_{ADAPTER}`, 1600, true, pcap.BlockForever)
  if err != nil { log.Fatal(err) }
  defer handle.Close()

  handle.SetBPFFilter("udp port 53") // DNS queries only

  src := gopacket.NewPacketSource(handle, handle.LinkType())
  for packet := range src.Packets() {
    dnsLayer := packet.Layer(layers.LayerTypeDNS)
    if dnsLayer == nil { continue }
    dns := dnsLayer.(*layers.DNS)
    for _, q := range dns.Questions {
      event := NetworkEvent{
        Type:     "dns_query",
        Hostname: string(q.Name),
      }
      out, _ := json.Marshal(event)
      fmt.Println(string(out)) // Electron reads line-by-line from stdout
    }
  }
}
```

Build for Windows:

```bash
GOOS=windows GOARCH=amd64 go build -o sniffer.exe sniffer.go
```

## 5.5 Spawning the Sidecar from Electron

```javascript
// In main.js — spawn and supervise the Go sniffer sidecar
const { spawn } = require('child_process');
const snifferPath = path.join(process.resourcesPath, 'sniffer.exe');

let snifferProcess;

function startSniffer() {
  snifferProcess = spawn(snifferPath, [], {
    stdio: ['ignore', 'pipe', 'pipe']
  });

  let buffer = '';
  snifferProcess.stdout.on('data', (data) => {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep any incomplete line
    for (const line of lines) {
      try {
        const event = JSON.parse(line);
        handleNetworkEvent(event);
      } catch (_) {}
    }
  });

  snifferProcess.on('exit', (code) => {
    console.warn(`Sniffer exited (code ${code}) — restarting in 5s...`);
    setTimeout(startSniffer, 5000); // simple restart with backoff
  });
}

function handleNetworkEvent(event) {
  if (event.type === 'dns_query') {
    const hostname = event.hostname.replace(/^www\./, '');
    if (bankingDomains.includes(hostname)) {
      overlayWindow.webContents.send('show-alert', {
        type: 'BANKING_SITE', severity: 'info', hostname
      });
    }
  }
}

startSniffer();
```

---

# 6. Alert Overlay System

## 6.1 Alert Types & Severity

| Alert Type | Severity | User-Facing Message |
|---|---|---|
| `REMOTE_ACCESS_TOOL` | CRITICAL | A remote control app is running. Hang up any phone calls immediately and do not let anyone control your computer. |
| `SCREEN_ANALYSIS` | CRITICAL / WARNING | Something suspicious was detected on your screen. Please call a trusted family member before continuing. |
| `MALICIOUS_URL` | CRITICAL | This website may be dangerous. Do not enter any passwords or personal information. |
| `BANKING_SITE` | INFO | You are visiting your bank's website. Remember: your bank will never call you and ask for your password. |
| `SUSPICIOUS_PROCESS` | WARNING | Unusual software was detected on your computer. You may want to close all programs and restart. |

## 6.2 Alert Manager

```javascript
// modules/alertManager.js
const ALERT_CONFIG = {
  REMOTE_ACCESS_TOOL: {
    severity: 'critical',
    title: '⚠️ DANGER: Remote Control Detected',
    message: 'A remote control program is running. Hang up the phone NOW.',
    dismissable: false,  // require explicit confirmation
    soundAlert: true
  },
  BANKING_SITE: {
    severity: 'info',
    title: '🔒 You are on your bank website',
    message: 'Your bank will NEVER ask for your password by phone.',
    dismissable: true,
    autoDismissMs: 8000
  },
  MALICIOUS_URL: {
    severity: 'critical',
    title: '🚫 Dangerous Website Blocked',
    message: 'This website may be a scam. Do not enter any information.',
    dismissable: false,
    soundAlert: true
  },
  SCREEN_ANALYSIS: {
    severity: 'warning',
    title: '👁️ Suspicious Activity Detected',
    message: 'Something on your screen looks unusual. Call a family member before continuing.',
    dismissable: true,
    autoDismissMs: 30000
  },
  SUSPICIOUS_PROCESS: {
    severity: 'warning',
    title: '⚠️ Unusual Software Running',
    message: 'Unexpected software was detected. Consider restarting your computer.',
    dismissable: true,
    autoDismissMs: 15000
  }
};

function buildAlert(type, data) {
  const config = ALERT_CONFIG[type] || ALERT_CONFIG.SCREEN_ANALYSIS;
  return { ...config, type, timestamp: Date.now(), data };
}

module.exports = { buildAlert, ALERT_CONFIG };
```

## 6.3 Overlay HTML

The overlay window loads a full-screen transparent HTML file. Critical alerts use a large red banner; info alerts use a smaller blue strip. Font sizes must be large enough for users with poor vision — minimum 22px body, 28px+ headings.

```html
<!-- renderer/overlay.html -->
<!DOCTYPE html>
<html>
<head>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: transparent; font-family: Arial, sans-serif; }

    #alert {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0;
      padding: 24px 40px;
      color: white;
      animation: slideDown 0.3s ease;
    }
    @keyframes slideDown {
      from { transform: translateY(-100%); }
      to   { transform: translateY(0); }
    }
    #alert.critical { background: rgba(176, 0, 0, 0.96); }
    #alert.warning  { background: rgba(180, 90, 0, 0.94); }
    #alert.info     { background: rgba(20, 80, 160, 0.92); }

    .alert-title   { font-size: 28px; font-weight: bold; margin-bottom: 8px; }
    .alert-message { font-size: 22px; line-height: 1.4; }
    .alert-dismiss {
      float: right;
      cursor: pointer;
      font-size: 18px;
      padding: 4px 12px;
      border: 2px solid rgba(255,255,255,0.6);
      border-radius: 4px;
      margin-left: 20px;
    }
    .alert-dismiss:hover { background: rgba(255,255,255,0.2); }
  </style>
</head>
<body>
  <div id="alert">
    <span class="alert-dismiss" onclick="dismiss()">✕ Dismiss</span>
    <div class="alert-title" id="alert-title"></div>
    <div class="alert-message" id="alert-message"></div>
  </div>

  <script>
    const { ipcRenderer } = require('electron');
    let autoDismissTimer;

    ipcRenderer.on('show-alert', (_, alert) => {
      clearTimeout(autoDismissTimer);
      const el = document.getElementById('alert');
      el.className = alert.severity;
      el.style.display = 'block';
      document.getElementById('alert-title').textContent = alert.title;
      document.getElementById('alert-message').textContent = alert.message;

      if (alert.autoDismissMs) {
        autoDismissTimer = setTimeout(dismiss, alert.autoDismissMs);
      }
    });

    function dismiss() {
      document.getElementById('alert').style.display = 'none';
      clearTimeout(autoDismissTimer);
    }
  </script>
</body>
</html>
```

---

# 7. Packaging & Distribution

## 7.1 electron-builder Configuration

Configure `electron-builder` in `package.json` to bundle the Go sidecar alongside the app:

```json
{
  "scripts": {
    "build": "electron-builder --win",
    "dev": "electron ."
  },
  "build": {
    "appId": "com.yourorg.scamguard",
    "productName": "ScamGuard",
    "win": {
      "target": "nsis",
      "requestedExecutionLevel": "requireAdministrator"
    },
    "extraResources": [
      { "from": "sidecar/sniffer.exe", "to": "sniffer.exe" },
      { "from": "resources/", "to": "resources/" }
    ],
    "nsis": {
      "installerLanguages": ["English"],
      "perMachine": true,
      "include": "installer/npcap-install.nsh"
    }
  }
}
```

## 7.2 Npcap Silent Install

Bundle the Npcap installer and run it silently as part of your NSIS installer script. Download `npcap-1.79.exe` from npcap.com and place it in `installer/`:

```nsis
; installer/npcap-install.nsh
Section "Install Npcap"
  File "npcap-1.79.exe"
  ; /winpcap_mode=yes enables WinPcap compatibility — required by gopacket
  ExecWait '"$INSTDIR\npcap-1.79.exe" /S /winpcap_mode=yes'
SectionEnd
```

## 7.3 Auto-Update

Use `electron-updater` (included with `electron-builder`) to push blocklist and prompt updates without a full reinstall:

```javascript
// In main.js — after app.whenReady()
const { autoUpdater } = require('electron-updater');

app.whenReady().then(() => {
  autoUpdater.checkForUpdatesAndNotify();
  // Point to your update server in electron-builder.yml:
  // publish: { provider: 'github', owner: 'yourorg', repo: 'scamguard' }
});
```

> **⚠️ Code Signing Required**
> Windows SmartScreen will block unsigned executables. Sign both the Electron app and the Go sidecar with an EV certificate. Use electron-builder's built-in signing: set `WIN_CSC_LINK` (path to PFX) and `WIN_CSC_KEY_PASSWORD` environment variables in your CI pipeline.

---

# 8. Security & Privacy

## 8.1 Security Checklist

- Disable `nodeIntegration` in all renderer processes — use `contextIsolation: true` with a `preload.js` and `contextBridge`
- Keep `webSecurity: true` (the default) — never disable this
- Store API keys in the OS credential manager via `keytar`, not in plain-text config files
- Screen captures must not be written to disk — process in memory and discard after the LLM call
- Display a clear privacy disclosure during first-run onboarding explaining what data is transmitted
- The Go sidecar should run as a limited service account, not SYSTEM
- Sign all distributed binaries with a valid EV code signing certificate
- Submit the sidecar binary to major AV vendors for whitelisting before launch (Windows Defender, Malwarebytes, etc.)

## 8.2 Storing API Keys Securely

```javascript
const keytar = require('keytar');

// Store (e.g. during first-run onboarding)
await keytar.setPassword('ScamGuard', 'anthropic_api_key', apiKey);

// Retrieve at runtime
const apiKey = await keytar.getPassword('ScamGuard', 'anthropic_api_key');
process.env.ANTHROPIC_API_KEY = apiKey; // or pass directly to SDK
```

## 8.3 contextBridge / Preload Pattern

Never expose raw `ipcRenderer` to renderer processes. Define a narrow API in the preload script:

```javascript
// preload.js
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('scamGuard', {
  onAlert: (cb) => ipcRenderer.on('show-alert', (_, data) => cb(data)),
  dismissAlert: () => ipcRenderer.send('dismiss-alert'),
  onStatusUpdate: (cb) => ipcRenderer.on('status-update', (_, data) => cb(data))
});
```

In the renderer, access it as:

```javascript
window.scamGuard.onAlert((alert) => {
  showAlertBanner(alert);
});
```

---

# 9. Quick Reference

## 9.1 Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (use keytar in production — env only for dev) |
| `SCAMGUARD_POLL_INTERVAL` | Screen capture interval in ms (default: `15000`) |
| `SCAMGUARD_PROCESS_INTERVAL` | Process scan interval in ms (default: `10000`) |
| `SCAMGUARD_LOG_LEVEL` | `debug` \| `info` \| `warn` \| `error` |
| `SCAMGUARD_SIDECAR_PATH` | Override path to `sniffer.exe` (default: `process.resourcesPath`) |

## 9.2 Key npm Packages

| Package | Purpose |
|---|---|
| `electron` | App shell, `desktopCapturer`, `session.webRequest`, `BrowserWindow` |
| `electron-builder` | Packaging and NSIS installer generation |
| `electron-updater` | Auto-update support |
| `@anthropic-ai/sdk` | LLM vision API calls |
| `keytar` | OS-level credential storage (Windows Credential Manager) |
| `windows-process-list` | Structured process enumeration (fallback to WMIC) |
| `node-fetch` | HTTP client (Node 18+ has built-in fetch as alternative) |

## 9.3 Detection Flow

```
┌─────────────────────────────────────────────────────────┐
│                  MAIN PROCESS (Node.js)                 │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │ Screen      │  │ Process     │  │ Network      │   │
│  │ Capture     │  │ Scanner     │  │ Monitor      │   │
│  │ [15s poll]  │  │ [10s poll]  │  │ [realtime]   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │
│         │ base64          │ process list    │ URL/DNS    │
│         ▼                 ▼                 ▼            │
│  ┌──────────────┐   ┌─────────────────────────────┐    │
│  │ LLM Analyzer │   │      Alert Manager          │    │
│  │ (Claude API) │──▶│  severity routing + queue   │    │
│  └──────────────┘   └──────────────┬──────────────┘    │
│                                     │ ipcMain.send       │
└─────────────────────────────────────│───────────────────┘
                                       ▼
              ┌───────────────────────────────────────┐
              │     OVERLAY WINDOW (Renderer)         │
              │  always-on-top · transparent · HTML   │
              └───────────────────────────────────────┘
```

## 9.4 Common Gotchas

- **macOS is different**: `desktopCapturer` requires explicit Screen Recording permission via `systemPreferences.askForMediaAccess('screen')`. This doc covers Windows only.
- **Npcap adapter name**: Use `pcap.FindAllDevs()` in Go to enumerate adapters at runtime rather than hardcoding the `NPF_{}` GUID.
- **WMIC on Windows 11 24H2+**: Deprecated — implement the PowerShell fallback before shipping.
- **LLM latency**: Vision API calls take 1–3s. Run all analysis async; never `await` them on the main thread in a way that blocks IPC.
- **False positives**: Tune the banking alert to be *reassuring* not alarming — a blue info banner, not a red danger banner. Trust erosion from false alarms is the primary adoption risk with elderly users.
- **AV whitelisting**: Packet capture binaries are frequently flagged. Submit to Microsoft's ISV partner program and major AV vendors *before* public release.
