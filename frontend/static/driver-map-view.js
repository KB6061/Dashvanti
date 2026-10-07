(() => {
 const host=document.querySelector('[data-live-tracking][data-tracking-role="driver"]');if(!host)return;
 const map=host.querySelector('[data-google-map]'),wrap=map.parentElement;
 host.classList.add('driver-navigation-shell');wrap.classList.add('driver-map-window');
 const toolbar=document.createElement('div');toolbar.className='driver-map-toolbar';
 toolbar.innerHTML='<button type="button" data-expand-map aria-label="Open full map">Full map ⛶</button><button type="button" data-close-map aria-label="Close full map" hidden>✕</button>';
 wrap.append(toolbar);
 const speed=document.createElement('div');speed.className='driver-navigation-speed';speed.innerHTML='<strong data-live-speed>—</strong><span>mph</span>';speed.setAttribute('aria-label','Current GPS speed');
 const placeSpeed=()=>{const dock=host.querySelector('.navigation-bottom-controls'),navigate=dock?.querySelector('.driver-floating-navigate');if(dock){dock.insertBefore(speed,navigate || null);}};
 window.addEventListener('dashvanti:navigation-controls-ready',placeSpeed);placeSpeed();
 const footer=document.createElement('div');footer.className='driver-navigation-arrival';footer.innerHTML='<div><strong data-arrival-clock>—</strong><span>arrival</span></div><div><strong data-arrival-minutes>—</strong><span>min</span></div><div><strong data-arrival-miles>—</strong><span>mi</span></div>';host.append(footer);
 const expand=toolbar.querySelector('[data-expand-map]'),close=toolbar.querySelector('[data-close-map]');
 let full=false,previousFocus;
 const resize=()=>{const state=map.dashvantiMapState;if(state&&window.google?.maps){google.maps.event.trigger(state.map,'resize');window.dispatchEvent(new Event('dashvanti:map-resize'));}};
 const setFull=value=>{
  full=value;if(value)previousFocus=document.activeElement;
  host.classList.toggle('driver-navigation-full',value);document.body.classList.toggle('driver-map-open',value);
  expand.hidden=value;close.hidden=!value;
  document.querySelector('.driver-floating-navigate')?.classList.toggle('navigation-hidden-in-full-map',value);
  requestAnimationFrame(()=>{resize();if(value)close.focus();else previousFocus?.focus?.({preventScroll:true});});
 };
 expand.onclick=()=>setFull(true);close.onclick=()=>setFull(false);
 document.addEventListener('keydown',event=>{if(full&&event.key==='Escape'){event.preventDefault();setFull(false);}});
 window.addEventListener('dashvanti:eta',event=>{
  if(String(event.detail.orderId)!==host.dataset.orderId)return;
  const minutes=Number(event.detail.minutes),miles=Number(event.detail.miles);
  if(Number.isFinite(minutes)){footer.querySelector('[data-arrival-minutes]').textContent=minutes;footer.querySelector('[data-arrival-clock]').textContent=new Date(Date.now()+minutes*60000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'});}
  if(Number.isFinite(miles))footer.querySelector('[data-arrival-miles]').textContent=miles.toFixed(1);
 });
 window.addEventListener('dashvanti:driver-position',event=>{
  const value=event.detail.speed;speed.querySelector('[data-live-speed]').textContent=value!=null&&Number.isFinite(Number(value))&&value>=0?Math.round(value*2.236936):'—';
 });
 window.addEventListener('dashvanti:order-update',event=>{if(String(event.detail.order_id)===host.dataset.orderId&&['DELIVERED','CANCELLED','REJECTED'].includes(event.detail.canonical_status||event.detail.status))setFull(false);});
 window.addEventListener('pagehide',()=>document.body.classList.remove('driver-map-open'));
})();
