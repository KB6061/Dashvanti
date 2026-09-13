(() => {
 const host=document.querySelector('[data-live-tracking][data-tracking-role="driver"]');
 if(!host)return;
 const dialog=document.createElement('dialog');
 dialog.className='driver-navigation-dialog';
 dialog.innerHTML='<button type="button" data-close aria-label="Close">×</button><h2></h2><p data-destination></p><div data-preview-map></div><p data-route-summary>Calculating distance and ETA…</p><p data-error role="status"></p><button type="button" class="driver-go" data-start>GO</button>';
 document.body.append(dialog);
 const map=host.querySelector('[data-google-map]');
 const placeholder=document.createComment('navigation-map');
 map.before(placeholder);
 const restore=()=>{placeholder.after(map);if(window.google?.maps)google.maps.event.trigger(map.dashvantiMapState?.map,'resize');};
 dialog.addEventListener('close',restore);
 const voice=document.createElement('a');voice.textContent='Google Maps voice navigation';voice.target='_blank';voice.rel='noopener';voice.className='driver-voice-link';host.append(voice);
 let phase='',current;
 const shown=new Set();
 dialog.querySelector('[data-close]').onclick=()=>dialog.close();
 window.addEventListener('dashvanti:tracking',event=>{
  const data=event.detail;
  if(!data.restaurant||!data.driver_status)return;
  current=data;
  const customerLeg=['PICKED_UP','ON_THE_WAY_TO_CUSTOMER','ARRIVED_AT_CUSTOMER','DELIVERED'].includes(data.driver_status);
  voice.href='https://www.google.com/maps/dir/?api=1&travelmode=driving&dir_action=navigate&destination='+encodeURIComponent(customerLeg?data.destination:data.restaurant.address);
  const next=data.driver_status==='DRIVER_ASSIGNED'?'pickup':data.driver_status==='PICKED_UP'?'delivery':'';
  if(!next){if(dialog.open)dialog.close();phase='';return;}
  if(phase!==next){
   phase=next;
   dialog.querySelector('h2').textContent=next==='pickup'?'Navigate to restaurant':'Navigate to customer';
   const address=next==='pickup'?data.restaurant.address:data.destination;
   dialog.querySelector('[data-destination]').textContent=(next==='pickup'?data.restaurant.name+' · ':'')+address;
   voice.href='https://www.google.com/maps/dir/?api=1&travelmode=driving&dir_action=navigate&destination='+encodeURIComponent(address);
   dialog.querySelector('[data-route-summary]').textContent='Calculating distance and ETA…';
  }
  if(!shown.has(next)){shown.add(next);dialog.querySelector('[data-preview-map]').append(map);dialog.showModal();if(window.google?.maps)google.maps.event.trigger(map.dashvantiMapState?.map,'resize');}
 });
 window.addEventListener('dashvanti:route-ready',event=>{
  const data=event.detail;
  if(String(data.orderId)!==host.dataset.orderId||data.status!==current?.driver_status)return;
  dialog.querySelector('[data-route-summary]').textContent=data.miles.toFixed(1)+' miles · ETA '+data.minutes+' min';
 });
 dialog.querySelector('[data-start]').onclick=()=>{
  const form=document.querySelector('[data-order-actions] form');
  const status=form?.elements.status?.value;
  if(status!==(phase==='pickup'?'ON_THE_WAY_TO_RESTAURANT':'ON_THE_WAY_TO_CUSTOMER')){
   dialog.querySelector('[data-error]').textContent='Waiting for the current order status. Try again shortly.';return;
  }
  dialog.close();
  form.requestSubmit();
  voice.click();
  host.classList.add('driver-navigation-active');
  window.dispatchEvent(new Event('dashvanti:navigation-start'));
  host.scrollIntoView({behavior:'smooth',block:'start'});
  const directions=host.querySelector('details');
  if(directions)directions.open=false;
 };

 window.addEventListener('dashvanti:navigation-route',event=>{
  if(dialog.open)dialog.querySelector('[data-destination]').textContent=event.detail.origin+' → '+event.detail.destination;
 });
})();