(() => {
 const host=document.querySelector('[data-tracking-preview]');if(!host)return;
 const waiting=host.querySelector('[data-preview-waiting]');
 window.addEventListener('dashvanti:tracking',({detail})=>{if(String(detail.order_id)!==host.dataset.orderId)return;waiting.hidden=false;waiting.classList.toggle('has-live-gps',!!detail.location);waiting.textContent=detail.location?(detail.location.stale?'Last known driver location':'Live driver GPS'):detail.queue?.queued?'Driver completing another order':detail.driver_id?'Waiting for live driver GPS':'Waiting for a delivery partner';});
 window.addEventListener('dashvanti:gps-stream',({detail})=>{if(detail.type==='driver_location'&&String(detail.order_id)===host.dataset.orderId){waiting.hidden=false;waiting.classList.add('has-live-gps');waiting.textContent='Live driver GPS';}});
})();
