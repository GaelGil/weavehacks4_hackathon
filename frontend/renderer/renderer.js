const statusEl = document.getElementById('update-status');
const progressContainer = document.getElementById('progress-bar-container');
const progressBar = document.getElementById('progress-bar');
const btnCheck = document.getElementById('btn-check');
const btnDownload = document.getElementById('btn-download');
const btnInstall = document.getElementById('btn-install');
const versionEl = document.getElementById('version');

window.electronAPI.getAppVersion().then((v) => {
  versionEl.textContent = `v${v}`;
});

const removeListener = window.electronAPI.onUpdateStatus((data) => {
  switch (data.status) {
    case 'checking':
      statusEl.textContent = 'Checking for updates...';
      btnCheck.disabled = true;
      break;

    case 'available':
      statusEl.textContent = `Update available: v${data.version}. Ready to download.`;
      btnCheck.disabled = false;
      btnDownload.style.display = 'inline-block';
      break;

    case 'not-available':
      statusEl.textContent = `You are on the latest version (v${data.version}).`;
      btnCheck.disabled = false;
      break;

    case 'downloading': {
      progressContainer.style.display = 'block';
      progressBar.style.width = `${data.percent}%`;
      const speed = (data.bytesPerSecond / 1024).toFixed(1);
      statusEl.textContent = `Downloading... ${data.percent}% (${speed} KB/s)`;
      btnDownload.disabled = true;
      break;
    }

    case 'downloaded':
      progressContainer.style.display = 'none';
      progressBar.style.width = '0%';
      statusEl.textContent = `v${data.version} downloaded. Restart to apply the update.`;
      btnDownload.style.display = 'none';
      btnInstall.style.display = 'inline-block';
      break;

    case 'error':
      statusEl.textContent = `Update error: ${data.message}`;
      btnCheck.disabled = false;
      btnDownload.disabled = false;
      break;
  }
});

btnCheck.addEventListener('click', async () => {
  const result = await window.electronAPI.checkForUpdates();
  if (!result.success) {
    statusEl.textContent = `Error checking for updates: ${result.error}`;
  }
});

btnDownload.addEventListener('click', async () => {
  const result = await window.electronAPI.downloadUpdate();
  if (!result.success) {
    statusEl.textContent = `Download failed: ${result.error}`;
  }
});

btnInstall.addEventListener('click', () => {
  window.electronAPI.installUpdate();
});
