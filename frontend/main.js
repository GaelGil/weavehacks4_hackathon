require('dotenv').config();
const { app, BrowserWindow, desktopCapturer, session, screen, ipcMain } = require('electron');
const { autoUpdater } = require('electron-updater');
const path = require('path');

const isDev = process.argv.includes('--dev');
const VITE_DEV_URL = 'http://localhost:5173';

// W&B Weave — initialize before any modules load so auto-instrumentation hooks in.
// Requires WANDB_API_KEY env var. Silently skipped if package not installed.
let weave;
try {
  weave = require('weave');
  weave.init('scamguard').catch(() => {});
} catch (_) {
  weave = null;
}

const { captureScreen } = require('./modules/screenCapture');
const { analyzeScreen } = require('./modules/llmAnalyzer');
const { initialize: initProcessScanner, scanProcesses, reportDetections, scanBrowserTitles, isSuspiciousProcess, getCategoryForProcess } = require('./modules/processScanner');
const { initialize: initNetworkMonitor, startWebRequestMonitor, startSniffer, stopSniffer, scanActiveConnections } = require('./modules/networkMonitor');
const { buildAlert, getAlertHistory } = require('./modules/alertManager');

// ---------------------------------------------------------------------------
// Detector state — tracks which pillars are active and their last-run timestamps
// ---------------------------------------------------------------------------
const detectorState = {
  screenAnalysis: { enabled: true, lastRun: null, lastResult: null },
  processScanner: { enabled: true, lastRun: null, lastResult: null },
  networkMonitor: { enabled: true, lastRun: null, lastResult: null },
};

let mainWindow;
let overlayWindow;
let screenPollTimer;
let processScanTimer;
let browserTitleScanTimer;
let connectionScanTimer;

// Suppress repeat banking alerts for the same domain within this window.
const bankingAlertCooldown = new Map();
// Suppress repeat connection alerts for the same process name.
const connectionAlertCooldown = new Map();
// Suppress repeat process alerts for the same process name.
const processAlertCooldown = new Map();
// Suppress repeat banking+remote-access correlation checks for the same site.
const bankingContextCooldown = new Map();

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    // React renderer served by Vite (npm run dev:vite).
    mainWindow.loadURL(VITE_DEV_URL);
    mainWindow.webContents.openDevTools();
  } else {
    // Production: load the built renderer bundle.
    mainWindow.loadFile(path.join(__dirname, 'renderer', 'dist', 'index.html'));
  }
}

// Capture the primary display and return a base64 PNG (no data: prefix).
// Used by the "Check my screen" button. The renderer never gets raw OS access.
//
// We hide ScamGuard's own window first so the screenshot captures what the user is
// actually looking at (the email/webpage behind us), not ScamGuard itself.
function createOverlayWindow() {
  overlayWindow = new BrowserWindow({
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    fullscreen: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  overlayWindow.loadFile(path.join(__dirname, 'renderer', 'overlay.html'));
  // Pass-through mouse events so the user can still use the desktop normally.
  // Temporarily lifted when an undismissable alert needs interaction.
  overlayWindow.setIgnoreMouseEvents(true, { forward: true });
}

// ---------------------------------------------------------------------------
// Alert routing — single path for all detection pillars
// ---------------------------------------------------------------------------

function dispatchAlert(type, data) {
  const alert = buildAlert(type, data);

  if (overlayWindow) {
    const needsClick = alert.dismissable !== false;
    overlayWindow.setIgnoreMouseEvents(!needsClick, { forward: true });
    overlayWindow.webContents.send('show-alert', alert);
  }

  // Mirror to the main dashboard so the React UI can update its status panel.
  if (mainWindow) {
    mainWindow.webContents.send('scamguard-alert', alert);
  }
}

// ---------------------------------------------------------------------------
// Screen capture + LLM polling (Pillar 1)
// ---------------------------------------------------------------------------

async function runScreenAnalysis() {
  if (!detectorState.screenAnalysis.enabled) return;
  try {
    const image = await captureScreen();
    const result = await analyzeScreen(image);

    detectorState.screenAnalysis.lastRun = Date.now();
    detectorState.screenAnalysis.lastResult = result;

    if (result.suspicious) {
      dispatchAlert('SCREEN_ANALYSIS', result);
    }
  } catch (err) {
    console.error('[screenAnalysis]', err.message);
  }
}

function startScreenAnalysisLoop() {
  const interval = parseInt(process.env.SCAMGUARD_POLL_INTERVAL) || 15000;
  screenPollTimer = setInterval(runScreenAnalysis, interval);
}

// ---------------------------------------------------------------------------
// Process scanner (Pillar 2)
// ---------------------------------------------------------------------------

const PROCESS_ALERT_COOLDOWN_MS = parseInt(process.env.SCAMGUARD_PROCESS_COOLDOWN) || 60_000;

async function runProcessScan() {
  if (process.platform !== 'win32') return;
  if (!detectorState.processScanner.enabled) return;
  try {
    const found = await scanProcesses();

    detectorState.processScanner.lastRun = Date.now();
    detectorState.processScanner.lastResult = found;

    if (found.length) reportDetections(found); // persist to backend, fire-and-forget

    for (const proc of found) {
      const key = proc.name.toLowerCase();
      const last = processAlertCooldown.get(key) || 0;
      if (Date.now() - last < PROCESS_ALERT_COOLDOWN_MS) continue;
      processAlertCooldown.set(key, Date.now());

      let type;
      if (proc.category === 'remote_access') type = 'REMOTE_ACCESS_TOOL';
      else if (proc.category === 'screen_capture') type = 'SCREEN_RECORDING_ACTIVE';
      else type = 'SUSPICIOUS_PROCESS';

      dispatchAlert(type, { process: proc });
    }
  } catch (err) {
    console.error('[processScanner]', err.message);
  }
}

function startProcessScanLoop() {
  const interval = parseInt(process.env.SCAMGUARD_PROCESS_INTERVAL) || 10000;
  processScanTimer = setInterval(runProcessScan, interval);
}

// ---------------------------------------------------------------------------
// Browser title scan (Pillar 2b — detect banking in the user's real browser)
// ---------------------------------------------------------------------------

const BANKING_ALERT_COOLDOWN_MS = parseInt(process.env.SCAMGUARD_BANKING_COOLDOWN) || 60_000;

async function runBrowserTitleScan() {
  if (!detectorState.networkMonitor.enabled) return;
  try {
    const match = await scanBrowserTitles();
    if (!match) return;

    const last = bankingAlertCooldown.get(match.domain) || 0;
    if (Date.now() - last < BANKING_ALERT_COOLDOWN_MS) return;
    bankingAlertCooldown.set(match.domain, Date.now());

    detectorState.networkMonitor.lastRun = Date.now();
    detectorState.networkMonitor.lastResult = match;
    dispatchAlert('BANKING_SITE', { ...match, source: 'browser_title' });
    checkBankingContext(match);
  } catch (err) {
    console.error('[browserTitleScan]', err.message);
  }
}

function startBrowserTitleScanLoop() {
  const interval = parseInt(process.env.SCAMGUARD_BROWSER_TITLE_INTERVAL) || 8000;
  browserTitleScanTimer = setInterval(runBrowserTitleScan, interval);
}

// ---------------------------------------------------------------------------
// Connection scan (Pillar 2c — active external TCP connections by process)
// ---------------------------------------------------------------------------

const CONNECTION_ALERT_COOLDOWN_MS = parseInt(process.env.SCAMGUARD_CONNECTION_COOLDOWN) || 120_000;

async function runConnectionScan() {
  if (process.platform !== 'win32') return;
  if (!detectorState.processScanner.enabled) return;
  try {
    const connections = await scanActiveConnections();

    detectorState.processScanner.lastRun = Date.now();

    for (const conn of connections) {
      if (!isSuspiciousProcess(conn.processName)) continue;

      const key = conn.processName.toLowerCase();
      const last = connectionAlertCooldown.get(key) || 0;
      if (Date.now() - last < CONNECTION_ALERT_COOLDOWN_MS) continue;
      connectionAlertCooldown.set(key, Date.now());

      dispatchAlert('REMOTE_ACCESS_CONNECTED', {
        process: {
          name: conn.processName,
          pid: conn.pid,
          category: getCategoryForProcess(key),
        },
        connection: {
          remoteAddress: conn.remoteAddress,
          remotePort: conn.remotePort,
        },
      });
    }
  } catch (err) {
    console.error('[connectionScan]', err.message);
  }
}

function startConnectionScanLoop() {
  const interval = parseInt(process.env.SCAMGUARD_CONNECTION_INTERVAL) || 15000;
  connectionScanTimer = setInterval(runConnectionScan, interval);
}

// ---------------------------------------------------------------------------
// Banking + remote-access correlation — the single highest-value alert.
// Visiting a bank is normal. A remote tool running is sometimes normal. The
// two together, at the same moment, is the textbook tech-support-scam pattern:
// "stay on the phone while I watch you log into your bank." Neither signal
// alone justifies a critical non-dismissable alert; together they do.
// ---------------------------------------------------------------------------

const BANKING_CONTEXT_COOLDOWN_MS = parseInt(process.env.SCAMGUARD_BANKING_CONTEXT_COOLDOWN) || 90_000;

function siteKeyFor(match) {
  return (match.hostname || match.domain || '').toLowerCase();
}

async function checkBankingContext(bankingMatch) {
  if (process.platform !== 'win32') return;
  if (!detectorState.networkMonitor.enabled || !detectorState.processScanner.enabled) return;

  const site = siteKeyFor(bankingMatch);
  if (!site) return;

  // One correlation check per site per 90s — this runs two fresh system scans,
  // so it's deliberately throttled independent of how often banking fires
  // (webRequest can fire many times per page load).
  const last = bankingContextCooldown.get(site) || 0;
  if (Date.now() - last < BANKING_CONTEXT_COOLDOWN_MS) return;
  bankingContextCooldown.set(site, Date.now());

  try {
    const [processes, connections] = await Promise.all([scanProcesses(), scanActiveConnections()]);

    const remoteProc = processes.find((p) => p.category === 'remote_access');
    const remoteConn = connections.find(
      (c) => isSuspiciousProcess(c.processName) && getCategoryForProcess(c.processName.toLowerCase()) === 'remote_access'
    );
    if (!remoteProc && !remoteConn) return;

    // Prefer the active-connection signal — "connected right now" is strictly
    // more alarming than "merely installed and running."
    const proc = remoteConn
      ? { name: remoteConn.processName, pid: remoteConn.pid, category: 'remote_access' }
      : remoteProc;

    dispatchAlert('BANKING_WITH_REMOTE_ACCESS', {
      site,
      process: proc,
      activeConnection: !!remoteConn,
    });
  } catch (err) {
    console.error('[bankingContext]', err.message);
  }
}

// ---------------------------------------------------------------------------
// Network monitor (Pillar 3 — Layer 1 webRequest + Layer 2 sidecar)
// ---------------------------------------------------------------------------

function startNetworkMonitor() {
  if (!detectorState.networkMonitor.enabled) return;

  const handleMatch = (match) => {
    detectorState.networkMonitor.lastRun = Date.now();
    detectorState.networkMonitor.lastResult = match;
    dispatchAlert(match.type, match);
    if (match.type === 'BANKING_SITE') checkBankingContext(match);
  };

  startWebRequestMonitor(handleMatch);
  startSniffer(handleMatch);
}

// ---------------------------------------------------------------------------
// IPC — on-demand screen capture for the React "Check my screen" button
// ---------------------------------------------------------------------------

ipcMain.handle('capture-screen', async () => {
  const wasVisible = mainWindow?.isVisible();
  if (wasVisible) {
    mainWindow.hide();
    // Give the compositor a moment to actually remove the window before capturing.
    await new Promise((r) => setTimeout(r, 250));
  }

  try {
    const { size, scaleFactor } = screen.getPrimaryDisplay();
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: {
        width: Math.round(size.width * scaleFactor),
        height: Math.round(size.height * scaleFactor),
      },
    });
    const primary = sources[0];
    if (!primary) throw new Error('No screen source available');
    return primary.thumbnail.toPNG().toString('base64');
  } finally {
    if (wasVisible) mainWindow.show();
  }
});

// ---------------------------------------------------------------------------
// IPC — renderer / agent control surface for the detection layer
// ---------------------------------------------------------------------------

ipcMain.handle('get-protection-status', () => ({
  detectors: detectorState,
  weaveEnabled: !!weave,
}));

ipcMain.handle('get-alert-history', () => getAlertHistory());

ipcMain.handle('toggle-detector', (_, { name, enabled }) => {
  if (!(name in detectorState)) return { success: false, error: `Unknown detector: ${name}` };
  detectorState[name].enabled = enabled;
  return { success: true, name, enabled };
});

ipcMain.on('dismiss-alert', () => {
  if (overlayWindow) {
    overlayWindow.setIgnoreMouseEvents(true, { forward: true });
  }
});

// ---------------------------------------------------------------------------
// Auto-updater
// ---------------------------------------------------------------------------

function setupAutoUpdater() {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  const fwd = (status, extra = {}) =>
    mainWindow?.webContents.send('update-status', { status, ...extra });

  autoUpdater.on('checking-for-update', () => fwd('checking'));
  autoUpdater.on('update-available', (i) => fwd('available', { version: i.version, releaseNotes: i.releaseNotes }));
  autoUpdater.on('update-not-available', (i) => fwd('not-available', { version: i.version }));
  autoUpdater.on('download-progress', (p) =>
    fwd('downloading', {
      percent: Math.round(p.percent),
      transferred: p.transferred,
      total: p.total,
      bytesPerSecond: p.bytesPerSecond,
    })
  );
  autoUpdater.on('update-downloaded', (i) => fwd('downloaded', { version: i.version }));
  autoUpdater.on('error', (err) => fwd('error', { message: err.message }));
}

ipcMain.handle('check-for-updates', async () => {
  try { await autoUpdater.checkForUpdates(); return { success: true }; }
  catch (err) { return { success: false, error: err.message }; }
});
ipcMain.handle('download-update', async () => {
  try { await autoUpdater.downloadUpdate(); return { success: true }; }
  catch (err) { return { success: false, error: err.message }; }
});
ipcMain.handle('install-update', () => autoUpdater.quitAndInstall(false, true));
ipcMain.handle('get-app-version', () => app.getVersion());

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(async () => {
  createMainWindow();
  setupAutoUpdater();

  // Fetch threat intel from backend before starting detectors so the live rules
  // are in effect from the very first scan/poll cycle.
  await Promise.all([initProcessScanner(), initNetworkMonitor()]);

  startNetworkMonitor();
  startScreenAnalysisLoop();
  startProcessScanLoop();
  startBrowserTitleScanLoop();
  startConnectionScanLoop();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });

  if (!isDev) {
    autoUpdater.checkForUpdatesAndNotify();
  }
});

app.on('window-all-closed', () => {
  clearInterval(screenPollTimer);
  clearInterval(processScanTimer);
  clearInterval(browserTitleScanTimer);
  clearInterval(connectionScanTimer);
  stopSniffer();
  if (process.platform !== 'darwin') app.quit();
});
