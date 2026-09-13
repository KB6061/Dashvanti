(() => {
 const host=document.querySelector('[data-live-tracking]');
 if(!host)return;
 const mapElement=host.querySelector('[data-google-map]'),role=host.dataset.trackingRole;
 const labels={CANCELLED:'Order cancelled',CANCELED:'Order cancelled',PLACED:'Order placed',ACCEPTED:'Order preparing',CONFIRMED:'Order preparing',PREPARING:'Order preparing',PACKING:'Order packing',WRAPPING_UP:'Order wrapping up',READY_FOR_PICKUP:'Order prepared and waiting for driver pickup',ARRIVED_AT_CUSTOMER:'Driver arrived at your address',DRIVER_ASSIGNED:'Driver assigned',ON_THE_WAY_TO_RESTAURANT:'Driver on the way to restaurant',ARRIVED_AT_RESTAURANT:'Driver arrived at restaurant',PICKED_UP:'Driver picked up order',ON_THE_WAY_TO_CUSTOMER:'Driver on the way to customer',DELIVERED:'Driver delivered order',REJECTED:'Order rejected'};
 const text=(selector,value)=>{const element=host.querySelector(selector);if(element)element.textContent=value;};
 let polling=false,failures=0,lastSuccess=0;
 let car,frame,state,pollTimer,routeTime=0,routeKey='',driverId,disposed=false,routeBusy=false,fitted=false,latest;
 const renderers=[];
 const carIcon=()=>({url:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"80\" viewBox=\"0 0 64 80\"><defs><linearGradient id=\"body\"><stop stop-color=\"#730d16\"/><stop offset=\".22\" stop-color=\"#ff6570\"/><stop offset=\".48\" stop-color=\"#ffb0b5\"/><stop offset=\".73\" stop-color=\"#c81e32\"/><stop offset=\"1\" stop-color=\"#680b17\"/></linearGradient><linearGradient id=\"glass\" x2=\".6\" y2=\"1\"><stop stop-color=\"#9ed8f0\"/><stop offset=\".4\" stop-color=\"#29495f\"/><stop offset=\"1\" stop-color=\"#101e30\"/></linearGradient><radialGradient id=\"shadow\"><stop stop-opacity=\".5\"/><stop offset=\"1\" stop-opacity=\"0\"/></radialGradient></defs><ellipse cx=\"34\" cy=\"43\" rx=\"27\" ry=\"37\" fill=\"url(#shadow)\"/><g fill=\"#151b24\"><rect x=\"12\" y=\"17\" width=\"8\" height=\"15\" rx=\"3\"/><rect x=\"44\" y=\"17\" width=\"8\" height=\"15\" rx=\"3\"/><rect x=\"12\" y=\"51\" width=\"8\" height=\"16\" rx=\"3\"/><rect x=\"44\" y=\"51\" width=\"8\" height=\"16\" rx=\"3\"/></g><path d=\"M20 7Q32 2 44 7Q49 11 49 24L48 64Q47 73 40 75H24Q17 73 16 64L15 24Q15 11 20 7Z\" fill=\"url(#body)\" stroke=\"#344454\" stroke-width=\"1.2\"/><path d=\"M21 11Q32 7 43 11L44 23Q32 19 20 23Z\" fill=\"#ff7882\" opacity=\".75\"/><path d=\"M20 26Q32 21 44 26L41 39H23Z\" fill=\"url(#glass)\" stroke=\"#526475\"/><path d=\"M24 40H40L42 54H22Z\" fill=\"url(#body)\" stroke=\"#9e1725\"/><path d=\"M22 56H42L44 65Q32 69 20 65Z\" fill=\"url(#glass)\" stroke=\"#526475\"/><path d=\"M18 30L21 40V52L18 57ZM46 30L43 40V52L46 57Z\" fill=\"#243e51\"/><path d=\"M22 27L40 25L25 36Z\" fill=\"#fff\" opacity=\".23\"/><g fill=\"#c9d6e0\" stroke=\"#405365\"><path d=\"M16 29L10 31V35L16 34Z\"/><path d=\"M48 29L54 31V35L48 34Z\"/></g><path d=\"M19 12L25 10M39 10L45 12\" stroke=\"#fffde0\" stroke-width=\"3.5\" stroke-linecap=\"round\"/><path d=\"M19 68L25 70M39 70L45 68\" stroke=\"#e53838\" stroke-width=\"3\" stroke-linecap=\"round\"/><path d=\"M25 7H39M24 73H40\" stroke=\"#273747\" stroke-width=\"2\"/><path d=\"M18 39V51M46 39V51\" stroke=\"#fff\" stroke-opacity=\".75\"/></svg>"),scaledSize:new google.maps.Size(48,60),anchor:new google.maps.Point(24,30)});
 function move(location){
  if(!location||!Number.isFinite(location.latitude)||!Number.isFinite(location.longitude))return;
  const target={lat:location.latitude,lng:location.longitude};
  if(!car){car=new google.maps.Marker({map:state.map,position:target,icon:role==='driver'?navigationIcon():window.dashvantiSilverCarIcon(),zIndex:999,title:'Delivery partner'});return;}
  cancelAnimationFrame(frame);
  const start=car.getPosition(),began=performance.now();
  const animate=now=>{
   const t=Math.min((now-began)/2000,1),ease=t*t*(3-2*t);
   car.setPosition({lat:start.lat()+(target.lat-start.lat())*ease,lng:start.lng()+(target.lng-start.lng())*ease});
   if(t<1&&!disposed)frame=requestAnimationFrame(animate);
  };
  frame=requestAnimationFrame(animate);
 }
 const navigationIcon=(heading=0)=>({url:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60" viewBox="0 0 60 60"><circle cx="30" cy="30" r="27" fill="white" stroke="#1565e8" stroke-width="4"/><path d="M30 9L46 45L30 36L14 45Z" fill="#1565e8" transform="rotate('+ (Number(heading)||0) +' 30 30)"/></svg>'),scaledSize:new google.maps.Size(52,52),anchor:new google.maps.Point(26,26)});
 window.addEventListener('dashvanti:driver-position',event=>{
  if(role!=='driver'||!state)return;
  move(event.detail);
  if(car){const icon=navigationIcon(event.detail.heading);car.setIcon(icon);state.map.panTo(car.getPosition());}
 });
 window.addEventListener('dashvanti:navigation-start',()=>{
  if(car)car.setIcon(navigationIcon());
  if(state){state.map.setZoom(17);if(car)state.map.panTo(car.getPosition());}
 });
 function route(origin,destination){
  return new google.maps.DirectionsService().route({origin,destination,travelMode:google.maps.TravelMode.DRIVING,drivingOptions:{departureTime:new Date()},unitSystem:google.maps.UnitSystem.IMPERIAL});
 }
 async function drawRoutes(data){
  const key=[data.driver_id,data.restaurant.address,data.destination,data.driver_status].join('|');
  if(routeBusy||(key===routeKey&&Date.now()-routeTime<30000))return;
  routeBusy=true;routeTime=Date.now();
  try{
   const afterPickup=['PICKED_UP','ON_THE_WAY_TO_CUSTOMER','DELIVERED'].includes(data.driver_status);
   const restaurantPoint=Number.isFinite(data.restaurant.lat)&&Number.isFinite(data.restaurant.lng)?{lat:data.restaurant.lat,lng:data.restaurant.lng}:data.restaurant.address;
   const customerPoint=data.customer_location||data.destination;
   const jobs=role==='driver'?[]:[route(restaurantPoint,customerPoint)];
   if(data.location&&!data.location.stale&&data.driver_status!=='DELIVERED'){
    jobs.push(route({lat:data.location.latitude,lng:data.location.longitude},afterPickup?customerPoint:restaurantPoint));
   }
   if(!jobs.length){text('[data-tracking-eta]','Waiting for current GPS to calculate route');return;}
   const results=await Promise.all(jobs);
   if(disposed||latest.driver_id!==data.driver_id||latest.driver_status!==data.driver_status)return;
   renderers.forEach(r=>r.setMap(null));renderers.length=0;
   results.forEach((result,index)=>{
    if(role==='driver'&&index!==results.length-1)return;
    const renderer=new google.maps.DirectionsRenderer({map:state.map,preserveViewport:true,suppressMarkers:role==="driver"||index===1,polylineOptions:{strokeColor:role==='driver'?'#1565e8':index===0?'#286b45':'#2374cf',strokeWeight:role==='driver'?7:5,strokeOpacity:.8}});
    renderer.setDirections(result);renderers.push(renderer);
   });
   const first=results[0].routes[0].legs[0];
   const active=results[results.length-1].routes[0].legs[0];
   const activeSeconds=(active.duration_in_traffic||active.duration).value;
   if(role==='driver')window.dispatchEvent(new CustomEvent('dashvanti:navigation-route',{detail:{steps:active.steps,origin:active.start_address,destination:active.end_address}}));
   window.dispatchEvent(new CustomEvent('dashvanti:route-ready',{detail:{orderId:host.dataset.orderId,status:data.driver_status,miles:active.distance.value/1609.344,minutes:Math.max(1,Math.ceil(activeSeconds/60))}}));
   text('[data-tracking-distance]',(active.distance.value/1609.344).toFixed(1)+' mi'+(role==='driver'?' to '+(afterPickup?'customer':'restaurant')+' · '+Math.max(1,Math.ceil(activeSeconds/60))+' min':''));

   if(!fitted){
    const bounds=results[0].routes[0].bounds;
    if(data.location)bounds.extend({lat:data.location.latitude,lng:data.location.longitude});
    state.map.fitBounds(bounds,40);fitted=true;
   }
   const panel=host.querySelector('[data-route-directions]');
   if(panel){panel.replaceChildren();renderers[renderers.length-1].setPanel(panel);}
   const seconds=leg=>(leg.duration_in_traffic||leg.duration).value;
   let eta=seconds(first);
   if(results[1])eta=seconds(results[1].routes[0].legs[0])+(afterPickup?0:seconds(first));
   text('[data-tracking-eta]',data.driver_status==='DELIVERED'?'Delivered':data.location?.stale?'ETA unavailable until GPS reconnects':(afterPickup?'Estimated arrival: ':'Estimated driving time: ')+Math.max(1,Math.ceil(eta/60))+' min'+(!afterPickup?' · preparation time additional':''));
   routeKey=key;
  }catch(error){text('[data-tracking-eta]','Route and ETA temporarily unavailable');}
  finally{routeBusy=false;}
 }
 async function poll(){
  if(disposed||polling)return;polling=true;clearTimeout(pollTimer);
  let received=false;
  try{
   const response=await fetch(host.dataset.trackingUrl,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000)});
   if(response.status===401||response.status===403||response.redirected){disposed=true;text('[data-tracking-health]','Sign in to resume tracking');return;}
   if(!response.ok)throw new Error('Tracking unavailable');
   const data=await response.json();
   if(!data||!data.restaurant||typeof data.status!=='string')throw new Error('Invalid tracking response');
   received=true;
   if(role==='driver'&&window.dashvantiDriverPosition&&Date.now()-window.dashvantiDriverPosition.timestamp<15000){const position=window.dashvantiDriverPosition;data.location={...data.location,...position,stale:false};}
   latest=data;
   window.dispatchEvent(new CustomEvent('dashvanti:tracking',{detail:data}));
   const rating=document.querySelector('[data-delivery-rating]');
   if(rating)rating.hidden=data.status!=='DELIVERED';
   text('[data-restaurant-activity]',labels[data.restaurant_status]||data.restaurant_status);
   text('[data-driver-activity]',labels[data.driver_status]||'Waiting for a delivery partner');
   const status=document.getElementById('order-status');if(status)status.textContent=labels[data.status]||data.status;
   text('[data-tracking-health]',data.location?(data.location.stale?'GPS signal delayed · showing last known location':'Live GPS · '+new Date(data.location.updated_at).toLocaleTimeString([],{hour:'numeric',minute:'2-digit',second:'2-digit',hour12:true})):'Waiting for driver GPS');
   const assignment=document.getElementById('driver-assignment-status');if(assignment)assignment.textContent=data.location?.driver?data.location.driver.name+' · '+data.location.driver.phone:(data.driver_id?'Driver assigned':'Waiting for a delivery partner');
   if(data.status==='DELIVERED')text('[data-tracking-eta]','Delivered');
   if(role==='driver'){
    const actionMap={DRIVER_ASSIGNED:['ON_THE_WAY_TO_RESTAURANT','Navigate'],ON_THE_WAY_TO_RESTAURANT:['ARRIVED_AT_RESTAURANT','Arrived at restaurant'],ARRIVED_AT_RESTAURANT:['PICKED_UP','Picked up order'],PICKED_UP:['ON_THE_WAY_TO_CUSTOMER','Navigate'],ON_THE_WAY_TO_CUSTOMER:['DELIVERED','Delivered']};
    const area=document.querySelector('[data-order-actions]'),next=actionMap[data.driver_status];
    if(area){
     const key=data.driver_status+'|'+data.restaurant_status;
     if(area.dataset.state!==key){
      area.dataset.state=key;area.replaceChildren();
      if(next&&!(data.driver_status==='ARRIVED_AT_RESTAURANT'&&data.restaurant_status!=='READY_FOR_PICKUP')){
       const form=document.createElement('form');form.method='post';
       for(const [name,value] of [['csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]')?.value||''],['status',next[0]]]){
        const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;form.append(input);
       }
       const button=document.createElement('button');button.type='submit';button.textContent=next[1];if(next[1]==='Navigate')button.className='driver-navigate';form.append(button);area.append(form);
       form.onsubmit=async event=>{
        event.preventDefault();button.disabled=true;
        try{
         const response=await fetch('/driver/status/update',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':form.elements.csrfmiddlewaretoken.value},body:JSON.stringify({order_id:Number(host.dataset.orderId),status:next[0]}),signal:AbortSignal.timeout(12000)});
         const result=await response.json();
         if(!response.ok)throw new Error(result.detail||'Could not update delivery status');
         window.dispatchEvent(new CustomEvent('dashvanti:tracking',{detail:result}));
         area.dataset.state='';routeTime=0;
         clearTimeout(pollTimer);void poll();
        }catch(error){text('[data-tracking-health]',error.message);button.disabled=false;}
       };
      }
     }
    }
   }
   const timeline=document.getElementById('timeline');
   if(timeline?.tagName==='OL')timeline.replaceChildren(...(Array.isArray(data.history)?data.history:[]).map(event=>{const li=document.createElement('li');li.textContent=(labels[event.status]||event.status.replaceAll('_',' '))+' · '+new Date(event.created_at).toLocaleString([],{hour12:true});return li;}));
   state=mapElement?.dashvantiMapState;
   if(state){
    const existing=state.markers.get('driver');if(existing){(existing.marker||existing).setMap(null);state.markers.delete('driver');}
    if(driverId!==data.driver_id){cancelAnimationFrame(frame);car?.setMap(null);car=null;driverId=data.driver_id;routeKey='';fitted=false;renderers.forEach(r=>r.setMap(null));renderers.length=0;}
    move(data.location);
    if(['CANCELLED','CANCELED','REJECTED'].includes(data.status)){car?.setMap(null);renderers.forEach(r=>r.setMap(null));text('[data-tracking-eta]','Order cancelled');document.querySelectorAll('[data-cancel-order]').forEach(button=>button.remove());}
    else if(data.mode==='delivery')void drawRoutes(data);
   }
   failures=0;lastSuccess=Date.now();
  }catch(error){
   failures++;
   if(received)text('[data-tracking-health]','Location received · retrying map update');
   else if(failures>=2||!lastSuccess)text('[data-tracking-health]',lastSuccess?'Connection interrupted · retaining last location and retrying':'Connecting to live tracking…');
  }
  finally{polling=false;if(!disposed)pollTimer=setTimeout(poll,Math.min(15000,3000*2**Math.min(failures,3)));}
 }
 window.addEventListener('online',()=>{if(!disposed){failures=0;clearTimeout(pollTimer);void poll();}});
 window.addEventListener('pageshow',event=>{if(event.persisted){disposed=false;void poll();}});
 window.addEventListener('pagehide',()=>{disposed=true;clearTimeout(pollTimer);cancelAnimationFrame(frame);renderers.forEach(r=>r.setMap(null));});
 poll();
})();