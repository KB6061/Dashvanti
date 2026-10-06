(() => {
 const host=document.querySelector('[data-live-tracking][data-tracking-role="driver"]');if(!host)return;
 const markers=new Map();let busy=false,last=0,area='';
 const icon=kind=>{
  const svg=kind==='stop'?'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><path d="M15 3H33L45 15V33L33 45H15L3 33V15Z" fill="#d82025" stroke="white" stroke-width="3"/><text x="24" y="29" text-anchor="middle" fill="white" font-family="Arial" font-size="13" font-weight="bold">STOP</text></svg>':'<svg xmlns="http://www.w3.org/2000/svg" width="36" height="52"><rect x="5" y="2" width="26" height="47" rx="9" fill="#263238" stroke="white" stroke-width="3"/><circle cx="18" cy="12" r="5" fill="#b9c4ca"/><circle cx="18" cy="26" r="5" fill="#b9c4ca"/><circle cx="18" cy="40" r="5" fill="#b9c4ca"/></svg>';
  return {url:'data:image/svg+xml,'+encodeURIComponent(svg),scaledSize:new google.maps.Size(kind==='stop'?48:36,kind==='stop'?48:52)};
 };
 window.addEventListener('dashvanti:driver-position',async event=>{
  const state=host.querySelector('[data-google-map]')?.dashvantiMapState;if(!state?.map||busy||Date.now()-last<30000)return;
  const point=event.detail;const lat=Number(point.lat??point.latitude),lng=Number(point.lng??point.longitude);if(!Number.isFinite(lat)||!Number.isFinite(lng))return;
  const key=lat.toFixed(2)+':'+lng.toFixed(2);if(key===area)return;busy=true;last=Date.now();
  try{const response=await fetch('/driver/road-controls?'+new URLSearchParams({lat,lng}),{credentials:'same-origin'});if(!response.ok||response.redirected)return;const data=await response.json();if(!data.available)return;area=key;
   markers.forEach(marker=>marker.setMap(null));markers.clear();
   for(const node of data.points){markers.set(node.id,new google.maps.Marker({map:state.map,position:{lat:node.lat,lng:node.lng},icon:icon(node.kind),title:node.kind==='stop'?'Mapped stop sign':'Mapped traffic signals (live signal state unavailable)',zIndex:100}));}
   if(!state.roadAttribution){const label=document.createElement('a');label.href='https://www.openstreetmap.org/copyright';label.target='_blank';label.rel='noopener';label.textContent='Road signs © OpenStreetMap';label.style.cssText='background:white;color:#163e35;padding:3px;font-size:10px';state.map.controls[google.maps.ControlPosition.BOTTOM_RIGHT].push(label);state.roadAttribution=true;}
  }catch(_){}finally{busy=false;}
 });
})();
