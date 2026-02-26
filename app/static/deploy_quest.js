/**
 * Deploy Quest — trigger Jenkins deploy from the portal.
 */

// eslint-disable-next-line no-unused-vars
async function deployToQuest(gcsPath, channel, variantName, btnEl) {
  if (!confirm(`Deploy "${variantName}" to AppLab channel "${channel}"?`)) {
    return;
  }

  // Disable button + show spinner
  const buttons = btnEl
    ? [btnEl]
    : document.querySelectorAll('.deploy-btn');
  buttons.forEach(b => {
    b.disabled = true;
    b.dataset.origHtml = b.innerHTML;
    b.innerHTML =
      '<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">' +
      '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
      '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>' +
      '</svg> Deploying\u2026';
  });

  try {
    const resp = await fetch('/deploy-quest/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gcs_path: gcsPath,
        channel: channel,
        variant_name: variantName,
      }),
    });
    const data = await resp.json();

    if (resp.ok && data.success) {
      Toast.success('Deployment triggered! Check Jenkins for progress.');
    } else {
      Toast.error(data.error || 'Failed to trigger deployment');
    }
  } catch (err) {
    Toast.error('Network error: ' + err.message);
  } finally {
    buttons.forEach(b => {
      b.disabled = false;
      if (b.dataset.origHtml) {
        b.innerHTML = b.dataset.origHtml;
        delete b.dataset.origHtml;
      }
    });
  }
}
