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
const { scanProcesses } = require('./modules/processScanner');
const { startWebRequestMonitor, startSniffer, stopSniffer } = require('./modules/networkMonitor');
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

async function runProcessScan() {
  if (!detectorState.processScanner.enabled) return;
  try {
    const found = await scanProcesses();

    detectorState.processScanner.lastRun = Date.now();
    detectorState.processScanner.lastResult = found;

    for (const proc of found) {
      const type = proc.category === 'remote_access' ? 'REMOTE_ACCESS_TOOL' : 'SUSPICIOUS_PROCESS';
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
// Network monitor (Pillar 3 — Layer 1 webRequest + Layer 2 sidecar)
// ---------------------------------------------------------------------------

function startNetworkMonitor() {
  if (!detectorState.networkMonitor.enabled) return;

  startWebRequestMonitor((match) => {
    detectorState.networkMonitor.lastRun = Date.now();
    detectorState.networkMonitor.lastResult = match;
    dispatchAlert(match.type, match);
  });

  startSniffer((match) => {
    detectorState.networkMonitor.lastRun = Date.now();
    detectorState.networkMonitor.lastResult = match;
    dispatchAlert(match.type, match);
  });
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

app.whenReady().then(() => {
  createMainWindow();
  setupAutoUpdater();

  startNetworkMonitor();
  startScreenAnalysisLoop();
  startProcessScanLoop();

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
  stopSniffer();
  if (process.platform !== 'darwin') app.quit();
});
