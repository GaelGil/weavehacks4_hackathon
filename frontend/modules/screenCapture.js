const { desktopCapturer } = require('electron');

async function captureScreen() {
  const sources = await desktopCapturer.getSources({
    types: ['screen'],
    thumbnailSize: {
      width: parseInt(process.env.SCAMGUARD_CAPTURE_WIDTH) || 1920,
      height: parseInt(process.env.SCAMGUARD_CAPTURE_HEIGHT) || 1080,
    },
  });
  if (!sources.length) throw new Error('No screen sources found');
  const dataUrl = sources[0].thumbnail.toDataURL();
  return dataUrl.split(',')[1]; // raw base64, never written to disk
}

module.exports = { captureScreen };
