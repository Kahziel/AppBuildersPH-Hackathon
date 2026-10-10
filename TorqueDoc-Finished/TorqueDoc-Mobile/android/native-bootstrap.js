// This file is injected only into APK assets. No Internet or desktop backend is needed.
window.TorqueDocAndroid = {
  version: '1.4.1',
  async saveFile(name, text) {
    return new Promise((resolve, reject) => {
      const done = event => {
        window.removeEventListener('torquedoc-export-result', done);
        if (event.detail === 'saved') resolve(true);
        else reject(new Error(event.detail === 'cancelled' ? 'Export cancelled. Your logs are still saved in TorqueDoc.' : 'Could not save the export.'));
      };
      window.addEventListener('torquedoc-export-result', done);
      const result = prompt('TorqueDoc.export', JSON.stringify({name, text}));
      if (result !== 'pending') {
        window.removeEventListener('torquedoc-export-result', done);
        reject(new Error('Android file export is unavailable.'));
      }
    });
  },
};
document.documentElement.classList.add('is-android');
