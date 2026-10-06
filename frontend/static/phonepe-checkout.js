(() => {
  const form = document.querySelector('[data-checkout-form]');
  if (!form) return;
  const option = form.querySelector('[data-phonepe-option]');
  const currency = form.dataset.currency || 'USD';
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const status = form.querySelector('[data-phonepe-error]');
  fetch('/customer/payments/methods', {credentials: 'same-origin', cache: 'no-store'})
    .then(response => response.ok ? response.json() : {methods: []})
    .then(data => {
      const available = currency === 'INR' && data.country === 'IN' && data.methods.some(method => method.id === 'phonepe');
      option.hidden = !available;
      option.querySelector('input').disabled = !available;
      const method = data.methods.find(method => method.id === 'phonepe');
      if (available && method.environment === 'sandbox') option.querySelector('small').textContent = 'Sandbox test payment — no delivery will be dispatched';
    }).catch(() => {});
  form.addEventListener('submit', async event => {
    if (new FormData(form).get('payment_mode') !== 'PhonePe') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const submit = form.querySelector('[type=submit]');
    if (submit.disabled) return;
    submit.disabled = true;
    status.textContent = 'Opening secure payment…';
    const values = new FormData(form);
    if (values.get('mode') === 'delivery' && !values.get('address_id')) {
      status.textContent = 'Choose a delivery address before paying.';
      submit.disabled = false;
      return;
    }
    const checkout = {mode: values.get('mode'), address_id: Number(values.get('address_id')) || null,
      tip: values.get('tip') || '0', promo_code: values.get('promo_code') || null, request_key: values.get('request_key')};
    try {
      const response = await fetch('/customer/payments/pay', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({checkout, instrument: 'UPI'})});
      const payment = await response.json();
      if (!response.ok) throw new Error(payment.detail || 'Payment could not start');
      if (payment.redirect_url && payment.status === 'PENDING') window.location.assign(payment.redirect_url);
      else window.location.assign('/customer/payment/' + payment.id);
    } catch (error) {
      status.textContent = error.message;
      submit.disabled = false;
    }
  }, true);
})();
