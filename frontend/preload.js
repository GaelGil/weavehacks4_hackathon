const { contextBridge, ipcRenderer } = require('electron');

// ---------------------------------------------------------------------------
// electronAPI — existing update surface (unchanged)
// ---------------------------------------------------------------------------
contextBridge.exposeInMainWorld('electronAPI', {
  // ScamGuard: capture the screen for a scan (returns base64 PNG, no data: prefix).
  captureScreen: () => ipcRenderer.invoke('capture-screen'),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  onUpdateStatus: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('update-status', listener);
    return () => ipcRenderer.removeListener('update-status', listener);
  },
});

// ---------------------------------------------------------------------------
// scamGuard — detection layer API for renderer windows and the agent
// ---------------------------------------------------------------------------
contextBridge.exposeInMainWorld('scamGuard', {
  // Subscribe to incoming alert events (used by overlay.js and the dashboard)
  onAlert: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('show-alert', listener);
    return () => ipcRenderer.removeListener('show-alert', listener);
  },

  // Subscribe to alerts mirrored to the main dashboard window
  onDashboardAlert: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('scamguard-alert', listener);
    return () => ipcRenderer.removeListener('scamguard-alert', listener);
  },

  // Signal that the user has dismissed the current alert
  dismissAlert: () => ipcRenderer.send('dismiss-alert'),

  // Query the live state of all four detection pillars + Weave status
  getProtectionStatus: () => ipcRenderer.invoke('get-protection-status'),

  // Retrieve the in-memory ring buffer of recent alerts (up to 100)
  getAlertHistory: () => ipcRenderer.invoke('get-alert-history'),

  // Enable or disable a named detector at runtime
  // name: 'screenAnalysis' | 'processScanner' | 'networkMonitor'
  toggleDetector: (name, enabled) => ipcRenderer.invoke('toggle-detector', { name, enabled }),
});
