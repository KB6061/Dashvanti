(() => {
  const panel = document.querySelector('[data-payment-result]');
  if (!panel) return;
  const status = panel.querySelector('[data-payment-state]');
  const message = panel.querySelector('[data-payment-message]');
  const button = panel.querySelector('[data-payment-recheck]');
  const csrf = panel.querySelector('[name=csrfmiddlewaretoken]').value;
  let busy = false;
  let attempts = 0;
  let timer;
  const check = async () => {
    if (busy) return;
    busy = true;
    button.disabled = true;
    try {
      const response = await fetch('/customer/payments/status', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify({transaction_id: Number(panel.dataset.paymentResult)})});
      const payment = await response.json();
      if (!response.ok) throw new Error(payment.detail || 'Status check failed');
      status.textContent = payment.status;
      if (payment.status === 'COMPLETED') {
        message.textContent = payment.environment === 'sandbox' ? 'Sandbox payment completed. This test order will not be delivered.' : 'Payment confirmed. Your order has been sent to the restaurant.';
        panel.querySelector('[data-payment-order]').hidden = payment.environment !== 'production';
        clearTimeout(timer);
      } else if (payment.status === 'FAILED') {
        message.textContent = 'Payment failed. Your order was not sent to the restaurant.';
        clearTimeout(timer);
      } else {
        message.textContent = 'Waiting for PhonePe confirmation. You can re-check without paying again.';
        if (++attempts < 20) timer = setTimeout(check, 5000);
      }
    } catch (error) {
      message.textContent = error.message;
    } finally {
      busy = false;
      button.disabled = false;
    }
  };
  button.addEventListener('click', () => {clearTimeout(timer); check();});
  check();
})();
