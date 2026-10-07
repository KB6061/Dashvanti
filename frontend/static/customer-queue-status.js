window.addEventListener('dashvanti:order-update', ({detail}) => {
  document.querySelectorAll('[data-driver-queue-message]').forEach(element => {
    if (element.dataset.driverQueueMessage === String(detail.order_id) && Object.prototype.hasOwnProperty.call(detail, 'queue')) element.textContent = detail.queue?.message || 'Delivery order in progress';
  });
});
