// legacy_upload.js - Legacy Unreal upload handler with drag-and-drop, progress tracking
(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // State management
  const states = ['idle', 'selected', 'uploading', 'success', 'error'];
  let currentFile = null;
  let uploadStartTime = null;

  function setState(state) {
    const zone = $('#upload-zone');
    if (!zone) return;

    zone.dataset.state = state;

    states.forEach(s => {
      const el = $(`#state-${s}`);
      if (el) {
        el.classList.toggle('hidden', s !== state);
      }
    });

    // Update zone styles based on state
    zone.classList.remove('border-blue-500', 'bg-blue-50', 'border-green-500', 'bg-green-50', 'border-red-500', 'bg-red-50');

    if (state === 'uploading') {
      zone.classList.add('border-blue-500', 'bg-blue-50');
    } else if (state === 'success') {
      zone.classList.add('border-green-500', 'bg-green-50');
    } else if (state === 'error') {
      zone.classList.add('border-red-500', 'bg-red-50');
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  function formatSpeed(bytesPerSecond) {
    if (bytesPerSecond === 0) return '0 B/s';
    const k = 1024;
    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
    const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k));
    return parseFloat((bytesPerSecond / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function selectFile(file) {
    if (!file) return;

    // Validate .zip extension
    if (!file.name.toLowerCase().endsWith('.zip')) {
      showError('Only .zip files are allowed');
      return;
    }

    currentFile = file;
    $('#selected-filename').textContent = file.name;
    $('#selected-filesize').textContent = formatBytes(file.size);
    setState('selected');
  }

  function showError(message) {
    $('#error-message').textContent = message;
    setState('error');
  }

  async function startUpload() {
    if (!currentFile) return;

    setState('uploading');
    $('#uploading-filename').textContent = currentFile.name;
    $('#uploading-status').textContent = 'Getting upload URL...';
    $('#progress-bar').style.width = '0%';
    $('#progress-percent').textContent = '0%';
    $('#progress-speed').textContent = '';

    try {
      // 1. Get presigned URL from server
      const presignRes = await fetch('/unreal-builds/presign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: currentFile.name,
          content_type: currentFile.type || 'application/zip'
        })
      });

      if (!presignRes.ok) {
        const err = await presignRes.json();
        throw new Error(err.error || 'Failed to get upload URL');
      }

      const { presigned_url, public_url, key } = await presignRes.json();

      // 2. Upload file directly to S3 with progress tracking
      $('#uploading-status').textContent = 'Uploading to S3...';
      uploadStartTime = Date.now();

      await uploadWithProgress(presigned_url, currentFile, public_url);

    } catch (err) {
      console.error('Upload error:', err);
      showError(err.message || 'Upload failed');
    }
  }

  function uploadWithProgress(url, file, publicUrl) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percent = Math.round((e.loaded / e.total) * 100);
          $('#progress-bar').style.width = percent + '%';
          $('#progress-percent').textContent = percent + '%';

          // Calculate speed
          const elapsed = (Date.now() - uploadStartTime) / 1000;
          if (elapsed > 0) {
            const speed = e.loaded / elapsed;
            $('#progress-speed').textContent = formatSpeed(speed);
          }

          // Update status
          const uploaded = formatBytes(e.loaded);
          const total = formatBytes(e.total);
          $('#uploading-status').textContent = `${uploaded} / ${total}`;
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          // Success!
          $('#success-filename').textContent = file.name;
          $('#success-url').value = publicUrl;
          setState('success');

          // Refresh file list
          const refreshBtn = $('#btn-refresh');
          if (refreshBtn) {
            refreshBtn.click();
          }

          if (window.Toast) {
            Toast.success('File uploaded successfully!');
          }

          resolve();
        } else {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'));
      });

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload cancelled'));
      });

      xhr.open('PUT', url);
      xhr.setRequestHeader('Content-Type', file.type || 'application/zip');
      xhr.send(file);
    });
  }

  function reset() {
    currentFile = null;
    uploadStartTime = null;
    $('#file-input').value = '';
    setState('idle');
  }

  function init() {
    const zone = $('#upload-zone');
    const fileInput = $('#file-input');

    if (!zone || !fileInput) return;

    // Click to open file dialog
    zone.addEventListener('click', (e) => {
      if (zone.dataset.state === 'idle') {
        fileInput.click();
      }
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        selectFile(e.target.files[0]);
      }
    });

    // Drag and drop
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (zone.dataset.state === 'idle') {
        zone.classList.add('border-blue-500', 'bg-blue-50');
      }
    });

    zone.addEventListener('dragleave', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (zone.dataset.state === 'idle') {
        zone.classList.remove('border-blue-500', 'bg-blue-50');
      }
    });

    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove('border-blue-500', 'bg-blue-50');

      if (zone.dataset.state !== 'idle') return;

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        selectFile(files[0]);
      }
    });

    // Button handlers
    const btnUpload = $('#btn-upload');
    const btnCancel = $('#btn-cancel');
    const btnRetry = $('#btn-retry');
    const btnUploadAnother = $('#btn-upload-another');
    const btnCopyUrl = $('#btn-copy-url');

    if (btnUpload) {
      btnUpload.addEventListener('click', (e) => {
        e.stopPropagation();
        startUpload();
      });
    }

    if (btnCancel) {
      btnCancel.addEventListener('click', (e) => {
        e.stopPropagation();
        reset();
      });
    }

    if (btnRetry) {
      btnRetry.addEventListener('click', (e) => {
        e.stopPropagation();
        reset();
      });
    }

    if (btnUploadAnother) {
      btnUploadAnother.addEventListener('click', (e) => {
        e.stopPropagation();
        reset();
      });
    }

    if (btnCopyUrl) {
      btnCopyUrl.addEventListener('click', (e) => {
        e.stopPropagation();
        const urlInput = $('#success-url');
        if (urlInput) {
          navigator.clipboard.writeText(urlInput.value).then(() => {
            if (window.Toast) {
              Toast.success('URL copied to clipboard');
            }
            // Visual feedback
            btnCopyUrl.innerHTML = `
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
              </svg>
              Copied!
            `;
            setTimeout(() => {
              btnCopyUrl.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path>
                </svg>
                Copy
              `;
            }, 2000);
          });
        }
      });
    }

    // Set initial state
    setState('idle');
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
