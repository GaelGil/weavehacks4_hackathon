const BACKEND_URL = process.env.SCAMGUARD_BACKEND_URL || 'http://localhost:8000';

const ALERT_CONFIG = {
  REMOTE_ACCESS_TOOL: {
    severity: 'critical',
    title: 'DANGER: Remote Control Detected',
    message: 'A remote control program is running. Hang up the phone NOW and do not let anyone control your computer.',
    dismissable: false,
    soundAlert: true,
  },
  BANKING_SITE: {
    severity: 'info',
    title: 'You are on your bank website',
    message: 'Your bank will NEVER ask for your password by phone. If someone told you to go here, hang up first.',
    dismissable: true,
    autoDismissMs: 8000,
  },
  MALICIOUS_URL: {
    severity: 'critical',
    title: 'Dangerous Website Detected',
    message: 'This website may be a scam. Do not enter any passwords or personal information.',
    dismissable: false,
    soundAlert: true,
  },
  SCREEN_ANALYSIS: {
    severity: 'warning',
    title: 'Suspicious Activity Detected',
    message: 'Something on your screen looks unusual. Call a trusted family member before continuing.',
    dismissable: true,
    autoDismissMs: 30000,
  },
  SUSPICIOUS_PROCESS: {
    severity: 'warning',
    title: 'Unusual Software Running',
    message: 'Unexpected software was detected on your computer. Consider closing all programs and restarting.',
    dismissable: true,
    autoDismissMs: 15000,
  },
};

// In-memory ring buffer for immediate UI queries
const MAX_HISTORY = 100;
const alertHistory = [];

async function persistAlert(alert) {
  try {
    await fetch(`${BACKEND_URL}/api/v1/scans/alerts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: alert.type,
        severity: alert.severity,
        title: alert.title,
        message: alert.message,
        timestamp: alert.timestamp,
        data: alert.data || {},
      }),
    });
  } catch (_) {
    // Fire-and-forget — local history still works even if backend is down
  }
}

function buildAlert(type, data) {
  const config = ALERT_CONFIG[type] || ALERT_CONFIG.SCREEN_ANALYSIS;
  const alert = { ...config, type, timestamp: Date.now(), data };

  alertHistory.push(alert);
  if (alertHistory.length > MAX_HISTORY) alertHistory.shift();

  persistAlert(alert); // async, non-blocking

  return alert;
}

function getAlertHistory() {
  return [...alertHistory];
}

function clearAlertHistory() {
  alertHistory.length = 0;
}

module.exports = { buildAlert, getAlertHistory, clearAlertHistory, ALERT_CONFIG };
