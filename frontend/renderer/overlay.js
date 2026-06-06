const alertEl = document.getElementById('alert');
const titleEl = document.getElementById('alert-title');
const messageEl = document.getElementById('alert-message');
const dismissBtn = document.getElementById('dismiss-btn');

let autoDismissTimer = null;

function showAlert(alert) {
  clearTimeout(autoDismissTimer);

  alertEl.className = alert.severity;
  alertEl.style.display = 'block';
  titleEl.textContent = alert.title;
  messageEl.textContent = alert.message;

  dismissBtn.style.display = alert.dismissable === false ? 'none' : 'inline-block';

  if (alert.autoDismissMs) {
    autoDismissTimer = setTimeout(dismiss, alert.autoDismissMs);
  }
}

function dismiss() {
  alertEl.style.display = 'none';
  clearTimeout(autoDismissTimer);
  window.scamGuard.dismissAlert();
}

dismissBtn.addEventListener('click', dismiss);

window.scamGuard.onAlert((alert) => showAlert(alert));
