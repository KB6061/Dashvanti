(() => {
 if(!document.querySelector('[data-order-alerts="driver"]'))return;
 let watch=null,timer=null,position,busy=false,lastSent=0,lastSaved=null;
 const report=status=>window.dispatchEvent(new CustomEvent('dashvanti:gps-status',{detail:{status}}));
 function moved(value){
  if(!lastSaved)return true;
  const radians=Math.PI/180;
  const a=value.latitude*radians,b=lastSaved.latitude*radians;
  const dlat=a-b,dlng=(value.longitude-lastSaved.longitude)*radians;
  const h=Math.sin(dlat/2)**2+Math.cos(a)*Math.cos(b)*Math.sin(dlng/2)**2;
  const distance=6371000*2*Math.asin(Math.min(1,Math.sqrt(h)));
  return distance>=Math.max(10,Math.min(25,Number(value.accuracy)||10));
 }
 function stop(){if(watch!==null)navigator.geolocation?.clearWatch(watch);watch=null;clearInterval(timer);timer=null;position=null;}
 async function save(){
  if(!(window.dashvantiPresence?.online||window.dashvantiPresence?.active_delivery)||busy||!position||!moved(position.coords)||Date.now()-position.timestamp>15000||Date.now()-lastSent<2900)return;
  busy=true;lastSent=Date.now();
  const sample=position.coords;
  const tracking=document.querySelector('[data-live-tracking]');
  const orderId=Number(tracking?.dataset.orderId)||undefined;
  const csrf=document.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
  const body={lat:sample.latitude,lng:sample.longitude,heading:sample.heading,order_id:orderId};
  try{
   const response=await fetch('/driver/location/update',{method:'POST',body:JSON.stringify(body),credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},signal:AbortSignal.timeout(12000)});
   if(response.redirected||response.status===401||response.status===403){stop();report('Sign in again to share GPS');return;}
   if(!response.ok){report(response.status===409?'Go online to save your GPS location':'GPS save failed · retrying');return;}
   lastSaved={latitude:sample.latitude,longitude:sample.longitude};
   report('live');
  }catch(_){report('GPS connection lost · retrying');}finally{busy=false;}
 }
 const options={enableHighAccuracy:true,maximumAge:0,timeout:10000};
 function received(value){
  position=value;
  const detail={latitude:value.coords.latitude,longitude:value.coords.longitude,heading:value.coords.heading,timestamp:value.timestamp};
  window.dashvantiDriverPosition=detail;
  window.dispatchEvent(new CustomEvent('dashvanti:driver-position',{detail}));
  void save();
 }
 function failed(error){
  if(error.code===1){stop();report('Location blocked. Allow location in browser site settings, then retry.');}
  else report('Waiting for GPS signal · keep location services on');
 }
 function start(){
  if(!window.isSecureContext||!navigator.geolocation){report('GPS requires an HTTPS connection. Open the secure driver portal to enable location.');return;}
  if(watch!==null)return;
  report('Waiting for location permission…');
  watch=navigator.geolocation.watchPosition(received,failed,options);
  timer=setInterval(save,3000);
 }
 async function initialize(){
  await window.dashvantiDriverPresence;
  const state=window.dashvantiPresence;
  if(state?.location){
   window.dashvantiDriverPosition=state.location;
   window.dispatchEvent(new CustomEvent('dashvanti:driver-position',{detail:state.location}));
  }
  if(!window.isSecureContext||!navigator.geolocation){report('Open secure GPS portal');return;}
  try{
   const permission=await navigator.permissions.query({name:'geolocation'});
   const resume=()=>{
    if(permission.state==='granted'){
     if(window.dashvantiPresence?.online||window.dashvantiPresence?.active_delivery)start();
     else navigator.geolocation.getCurrentPosition(received,failed,options);
    }else{
     stop();report(permission.state==='denied'?'Allow location in browser settings':'Enable GPS');
    }
   };
   resume();
   permission.onchange=resume;
  }catch(_){report('Enable GPS');}
 }
 window.addEventListener('dashvanti:driver-presence',event=>{
  if(event.detail.online||event.detail.active_delivery)start();
  else{stop();report(event.detail.mode==='BREAK'?'On break':'Off duty');}
 });
 window.addEventListener('dashvanti:tracking',event=>{
  if(['DELIVERED','CANCELLED','CANCELED','REJECTED'].includes(event.detail.status)){
   const tracking=document.querySelector('[data-live-tracking]');
   if(tracking)delete tracking.dataset.orderId;
  }
 });
 window.addEventListener('pagehide',stop);
 window.addEventListener('pageshow',event=>{if(event.persisted)initialize();});
 initialize();
})();