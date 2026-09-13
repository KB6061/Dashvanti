(() => {
 if(!document.querySelector('[data-order-alerts="driver"]'))return;
 const buttons=[...document.querySelectorAll('[data-driver-presence]')];
 const labels={ONLINE:'Online',BREAK:'On break',HOME:'Off duty'};
 function apply(state){
  window.dashvantiPresence=state;
  document.querySelectorAll('[data-driver-online-label]').forEach(el=>el.textContent=labels[state.mode]||'');
  document.querySelectorAll('form[action$="/accept"] button').forEach(el=>el.disabled=!state.online);
  buttons.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.driverPresence===state.mode)));
  document.querySelectorAll('[data-presence-status]').forEach(el=>el.textContent=labels[state.mode]||'');
  window.dispatchEvent(new CustomEvent('dashvanti:driver-presence',{detail:state}));
  return state;
 }
 async function load(){
  const response=await fetch('/driver/presence',{credentials:'same-origin',headers:{Accept:'application/json'}});
  if(!response.ok||response.redirected)throw new Error('Availability unavailable');
  return apply(await response.json());
 }
 window.dashvantiDriverPresence=load().catch(()=>null);
 buttons.forEach(button=>button.addEventListener('click',async()=>{
  buttons.forEach(el=>el.disabled=true);
  try{
   const response=await fetch('/driver/presence',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value||''},body:JSON.stringify({mode:button.dataset.driverPresence})});
   const data=await response.json();
   if(!response.ok)throw new Error(data.detail||'Unable to change availability');
   apply(data);
  }catch(error){document.querySelectorAll('[data-presence-status]').forEach(el=>el.textContent=error.message);}
  finally{buttons.forEach(el=>el.disabled=false);}
 }));
 window.addEventListener('pageshow',event=>{if(event.persisted)window.dashvantiDriverPresence=load().catch(()=>null);});
})();
