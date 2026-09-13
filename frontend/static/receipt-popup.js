(() => {
  let dialog, frame, status, download, opener, blobUrl, request;
  function close() {
    request?.abort();
    frame.src = 'about:blank';
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = null;
    opener?.focus();
  }
  function create() {
    dialog = document.createElement('dialog');
    dialog.className = 'receipt-popup';
    dialog.setAttribute('aria-label', 'PDF receipt');
    dialog.innerHTML = '<button type="button" class="receipt-close" aria-label="Close receipt">&times;</button><p role="status" class="receipt-status"></p><iframe title="PDF receipt"></iframe><footer><a class="button" download>Download</a><button type="button" class="receipt-print">Print</button></footer>';
    document.body.append(dialog);
    frame = dialog.querySelector('iframe');
    status = dialog.querySelector('[role=status]');
    download = dialog.querySelector('a');
    dialog.querySelector('.receipt-close').onclick = () => dialog.close();
    dialog.addEventListener('close', close);
    dialog.addEventListener('click', event => { if (event.target === dialog) {
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
    }});
    dialog.querySelector('.receipt-print').onclick = () => {
      if (!blobUrl) return;
      try { frame.contentWindow.focus(); frame.contentWindow.print(); }
      catch (_) { status.textContent = 'Use Download to open the receipt in your PDF reader and print.'; }
    };
  }
  document.addEventListener('click', async event => {
    const link = event.target.closest('[data-report-popup]');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!dialog) create();
    opener = link;
    request?.abort();
    request = new AbortController();
    const active = request;
    const url = new URL(link.href);
    url.searchParams.set('tz', Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Chicago');
    url.searchParams.set('format', 'download');
    download.href = url.href;
    url.searchParams.set('format', 'inline');
    status.textContent = 'Loading receipt…';
    frame.hidden = true;
    dialog.querySelector('.receipt-print').disabled = true;
    dialog.showModal();
    try {
      const response = await fetch(url, {credentials: 'same-origin', signal: active.signal});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/pdf')) throw new Error('Unable to load this receipt. Please try again.');
      const blob = await response.blob();
      if (active.signal.aborted) return;
      blobUrl = URL.createObjectURL(blob);
      frame.src = blobUrl + '#toolbar=0&navpanes=0&view=FitH';
      frame.hidden = false;
      status.textContent = '';
      frame.onload = () => { dialog.querySelector('.receipt-print').disabled = false; };
    } catch (error) {
      if (error.name !== 'AbortError') status.textContent = error.message;
    }
  }, true);
})();