(() => {
 if(!document.body.classList.contains('driver-portal')||!('Notification' in window)||!('serviceWorker' in navigator))return;
 let registration;
 const button=document.createElement('button');button.type='button';button.textContent='Enable background alerts';button.className='driver-background-alerts';
 (document.querySelector('[data-order-alerts]')||document.querySelector('main')).append(button);
 const ready=navigator.serviceWorker.register('/driver/notifications-worker.js',{scope:'/driver/'}).then(value=>{registration=value;return value;}).catch(()=>{button.textContent='Background alerts unavailable';button.disabled=true;});
 const sync=()=>{button.hidden=Notification.permission==='granted';if(Notification.permission==='denied'){button.textContent='Allow notifications in browser settings';button.disabled=true;}};sync();
 button.onclick=async()=>{await Notification.requestPermission();await ready;sync();};
 window.addEventListener('dashvanti:delivery-offers',async event=>{
  if(!document.hidden||Notification.permission!=='granted')return;await ready;if(!registration)return;
  for(const row of event.detail){await registration.showNotification('Dashvanti · Order -'+row.id,{body:[row.restaurant_name,row.restaurant_address,'Delivery: '+row.address,row.pickup_eta_minutes!=null?'Pickup ETA '+row.pickup_eta_minutes+' min':''].filter(Boolean).join('\n'),tag:'dashvanti-order-'+row.id,requireInteraction:true,data:{order_id:row.id},actions:[{action:'accept',title:'Accept'},{action:'reject',title:'Reject'}]});}
 });
 navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='offers-refresh')window.dispatchEvent(new Event('dashvanti:offers-refresh'));});
})();
