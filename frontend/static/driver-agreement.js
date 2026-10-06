(() => {
  const form = document.getElementById('driver-agreement-form');
  if (!form) return;
  const agreement = document.getElementById('driver-agreement-text');
  const button = document.getElementById('agreement-continue');
  const name = document.getElementById('agreement-legal-name');
  const checks = [...form.querySelectorAll('input[type="checkbox"]')];
  const status = document.getElementById('agreement-read-status');
  let read = false, pending = false;
  const validName = () => name.value.trim().length >= 2 && /\p{L}/u.test(name.value);
  const update = () => { button.disabled = !read || !validName() || !checks.every(check => check.checked); };
  async function recordScroll() {
    if (read || pending || agreement.scrollTop + agreement.clientHeight < agreement.scrollHeight - 4) return;
    pending = true;
    try {
      const response = await fetch('/driver/agreement/read', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
        body: JSON.stringify({agreement_version: form.elements.agreement_version.value, scroll_completed: true})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not record agreement scroll. Please try again.');
      read = data.scroll_completed === true;
      status.textContent = 'Agreement scroll complete. Confirm every acknowledgement and enter your full legal name.';
    } catch (error) { status.textContent = error.message; }
    finally { pending = false; update(); }
  }
  agreement.addEventListener('scroll', recordScroll, {passive: true});
  checks.forEach(check => check.addEventListener('change', update));
  name.addEventListener('input', update);
  form.addEventListener('submit', event => {
    if (event.submitter?.value === 'decline') return;
    update();
    if (button.disabled) { event.preventDefault(); status.textContent = 'Read the complete agreement, check every acknowledgement and enter your full legal name.'; }
  });
  window.addEventListener('pageshow', update);
  update();
})();
