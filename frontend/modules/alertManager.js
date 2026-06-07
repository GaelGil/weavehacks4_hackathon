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
  SCREEN_RECORDING_ACTIVE: {
    severity: 'warning',
    title: 'Screen Recording Software is Running',
    message: "A screen recording program is active. If you didn't start it, your screen may be visible to others.",
    messageBuilder: (data) => {
      const name = data?.process?.name || 'A screen recording program';
      return `${name} is running. If you didn't start it, or if someone asked you to open it, your screen may be visible to others.`;
    },
    dismissable: true,
    autoDismissMs: 20000,
  },
  BANKING_WITH_REMOTE_ACCESS: {
    severity: 'critical',
    title: 'DANGER: Remote Access Active While Banking',
    message: 'A remote access program is running while you are on a banking website. This is a common scam pattern. Stop — do not enter any information — and call a trusted family member.',
    messageBuilder: (data) => {
      const name = data?.process?.name || 'A remote access program';
      const liveNote = data?.activeConnection ? ' and is connected to the internet right now' : '';
      return `${name} is running${liveNote} while you are on your banking website. This is a common scam pattern — STOP. Do not enter any passwords or account numbers. Close ${name} and call a trusted family member before continuing.`;
    },
    dismissable: false,
    soundAlert: true,
  },
  REMOTE_ACCESS_CONNECTED: {
    severity: 'critical',
    title: 'DANGER: Remote Access Program Is Connected',
    message: 'A remote access program has an active internet connection. Someone may be watching your computer RIGHT NOW. Close it immediately and call a trusted family member.',
    messageBuilder: (data) => {
      const name = data?.process?.name || 'A remote access program';
      return `${name} has an active internet connection. Someone may be watching your computer RIGHT NOW. Close it immediately and call a trusted family member.`;
    },
    dismissable: false,
    soundAlert: true,
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
  const message = config.messageBuilder ? config.messageBuilder(data) : config.message;
  const alert = { ...config, message, type, timestamp: Date.now(), data };

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
