(() => {
 const portal=['admin','driver','restaurant'].find(role=>document.body.classList.contains(role+'-portal')) || 'customer';
 const entries=new Map();
 const icon=()=>{
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="52" height="52"><path d="M16 3H36L49 16V36L36 49H16L3 36V16Z" fill="#d82025" stroke="white" stroke-width="3"/><text x="26" y="32" text-anchor="middle" fill="white" font-family="Arial" font-size="14" font-weight="bold">STOP</text></svg>';
  return {url:'data:image/svg+xml,'+encodeURIComponent(svg),scaledSize:new google.maps.Size(34,34)};
 };
 async function refresh(element){
  const state=element.dashvantiMapState,entry=entries.get(element);
  if(!state || !entry || document.hidden || element.closest('[hidden]'))return;
  const zoom=state.map.getZoom();
  if(zoom<14){entry.markers.forEach(marker=>marker.setMap(null));return;}
  const center=state.map.getCenter();if(!center)return;
  const lat=center.lat(),lng=center.lng(),area=lat.toFixed(2)+':'+lng.toFixed(2);
  if(entry.area===area){entry.markers.forEach(marker=>marker.setMap(state.map));return;}
  if(entry.busy || Date.now()-entry.last<30000)return;
  entry.busy=true;entry.last=Date.now();clearTimeout(entry.retry);
  try{
   const response=await fetch('/'+portal+'/road-controls?'+new URLSearchParams({lat,lng}),{credentials:'same-origin',signal:window.dashvantiTimeoutSignal(18000)});
   if(!response.ok || response.redirected)return;
   const data=await response.json();
   if(!data.available){entry.retry=setTimeout(()=>refresh(element),60000);return;}
   const current=state.map.getCenter();
   if(current.lat().toFixed(2)+':'+current.lng().toFixed(2)!==area){entry.retry=setTimeout(()=>refresh(element),30000);return;}
   entry.markers.forEach(marker=>marker.setMap(null));entry.markers.clear();entry.area=area;
   for(const node of data.points){
    if(node.kind!=='stop')continue;
    entry.markers.set(node.id,new google.maps.Marker({map:state.map.getZoom()>=14?state.map:null,position:{lat:node.lat,lng:node.lng},icon:icon(),title:'Mapped stop sign',clickable:false,zIndex:1100}));
   }
   if(!state.roadAttribution && data.points.length){
    const label=document.createElement('a');label.href='https://www.openstreetmap.org/copyright';label.target='_blank';label.rel='noopener';label.textContent='Road signs © OpenStreetMap';label.style.cssText='background:white;color:#163e35;padding:3px;font-size:10px';
    state.map.controls[google.maps.ControlPosition.BOTTOM_RIGHT].push(label);state.roadAttribution=true;
   }
  }catch(_){entry.retry=setTimeout(()=>refresh(element),60000);}
  finally{entry.busy=false;}
 }
 function attach(element){
  if(entries.has(element) || !element?.dashvantiMapState)return;
  entries.set(element,{markers:new Map(),area:'',busy:false,last:0});
  element.dashvantiMapState.map.addListener('idle',()=>refresh(element));void refresh(element);
 }
 document.addEventListener('dashvanti:map-ready',event=>attach(event.detail.element));
 document.querySelectorAll('[data-google-map]').forEach(attach);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)entries.forEach((_,element)=>refresh(element));});
 window.addEventListener('pagehide',()=>entries.forEach(entry=>clearTimeout(entry.retry)));
})();
