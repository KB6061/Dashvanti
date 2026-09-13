(() => {
 const host = document.querySelector('[data-order-alerts]');
 if (!host) return;
 const role = host.dataset.orderAlerts, seen = new Set();
 let audio, timer, busy=false, enabled=false, ringing, saving=false, storageKey, pending=false, activeTone;
 const noticeIds=new Set();
 let activeDriverOrders=new Set();
 let assignmentAlertUntil=0;
 const statuses=new Map(); let initialized=false;
 const soundLabel=document.createElement('label');soundLabel.className='order-sound-control';
 const sound=document.createElement('input');sound.type='checkbox';
 soundLabel.append(sound,document.createTextNode('Order sounds'));
 const nav=document.querySelector('[data-sidebar-sounds]') || document.querySelector('.customer-topbar nav') || document.querySelector('.site-header nav');
 (nav || host).append(soundLabel);
 const soundStatus=document.createElement('small');soundStatus.setAttribute('role','status');soundLabel.append(soundStatus);
 sound.disabled=true;
 const persistState=()=>{if(storageKey)try{sessionStorage.setItem(storageKey,JSON.stringify({statuses:[...statuses],seen:[...seen],pending}));}catch(_){}};
 async function unlock(){
  if(!enabled)return;
  const Audio=window.AudioContext||window.webkitAudioContext;
  if(!Audio){soundStatus.textContent='Audio unavailable in this browser';return;}
  audio=audio||new Audio();await audio.resume();
  soundStatus.textContent=audio.state==='running'?'':'Tap the page to activate sound';
  if(pending&&audio.state==='running')ring();
 }
 document.addEventListener('pointerdown',()=>unlock().catch(()=>{}));
 document.addEventListener('keydown',()=>unlock().catch(()=>{}));
 sound.addEventListener('change',async()=>{
  const next=sound.checked,previous=enabled;saving=true;sound.disabled=true;
  if(next){enabled=true;unlock().catch(()=>{});}
  try{
   const body=new FormData();body.set('csrfmiddlewaretoken',csrf());body.set('enabled',String(next));
   const response=await fetch('/'+role+'/order-sound',{method:'POST',body,credentials:'same-origin'});
   if(!response.ok||response.redirected)throw new Error('Could not save sound setting');
   const data=await response.json();enabled=data.enabled;sound.checked=enabled;
   if(enabled){await unlock();}
   else{stopAlert();audio?.suspend();}
  }catch(error){enabled=previous;sound.checked=previous;soundStatus.textContent=error.message;if(!enabled){stopAlert();audio?.suspend();}}
  finally{saving=false;sound.disabled=false;}
 });
 async function loadPreference(){
  if(saving)return;
  const response=await fetch('/'+role+'/order-sound',{credentials:'same-origin',cache:'no-store'});
  if(!response.ok||response.redirected)throw new Error('Sound preference unavailable');
  const data=await response.json();
  if(saving)return;
  if(!storageKey){
   storageKey='dashvanti-order-alerts-'+role+'-'+data.user_id;
   try{const saved=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(saved){(saved.statuses||[]).forEach(([id,status])=>statuses.set(id,status));(saved.seen||[]).forEach(id=>seen.add(id));pending=false;initialized=true;}}catch(_){}
  }
  enabled=data.enabled;sound.checked=enabled;sound.disabled=false;
  if(enabled)await unlock();
  else{stopAlert();audio?.suspend();}
 }
 const stopAlert=()=>{
  pending=false;assignmentAlertUntil=0;clearTimeout(ringing);ringing=null;
  if(activeTone){try{activeTone.stop();}catch(_){}activeTone=null;}
  soundStatus.textContent='';persistState();
 };
 const beep=()=>{
  if(!enabled||!audio||audio.state!=='running'||activeTone)return;
  const oscillator=audio.createOscillator(),gain=audio.createGain(),start=audio.currentTime;
  oscillator.connect(gain);gain.connect(audio.destination);oscillator.frequency.value=880;
  gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(.12,start+.03);
  gain.gain.setValueAtTime(.12,start+2.9);gain.gain.linearRampToValueAtTime(0,start+3);
  activeTone=oscillator;
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();if(activeTone===oscillator)activeTone=null;};
  oscillator.start(start);oscillator.stop(start+3);
 };
 const ring=()=>{
  if(!enabled)return;
  if(!audio||audio.state!=='running'){pending=true;persistState();soundStatus.textContent='New order update — tap the page to hear sound';return;}
  pending=false;persistState();beep();
 };
 const panel=document.createElement('section'); panel.className='live-order-popup'; panel.hidden=true;host.append(panel);
 const toggle=document.createElement('button');toggle.type='button';toggle.textContent='Order notifications';toggle.hidden=true;host.append(toggle);
 toggle.onclick=()=>{panel.hidden=!panel.hidden;};
 const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
 async function poll(){
  if(busy)return;busy=true;
  try{
   const statusResponse=await fetch('/'+role+'/live-alerts?statuses=1',{credentials:'same-origin',headers:{Accept:'application/json'}});
   if(statusResponse.ok && !statusResponse.redirected){
    const orders=await statusResponse.json();
    if(role==='driver'){
     activeDriverOrders=new Set(orders.filter(row=>!['DELIVERED','CANCELLED','CANCELED','REJECTED'].includes(row.status)).map(row=>String(row.id)));
     host.querySelectorAll('[data-assignment-order]').forEach(message=>{
      if(!activeDriverOrders.has(message.dataset.assignmentOrder))message.remove();
     });
    }

    let accepted=false;
    orders.forEach(row=>{
     if(role!=='customer'&&initialized&&statuses.has(row.id)&&statuses.get(row.id)!==row.status&&row.status==='ACCEPTED'){
      const key=storageKey+'-accepted-'+row.id;
      let played=false;try{played=localStorage.getItem(key)==='1';if(!played)localStorage.setItem(key,'1');}catch(_){}
      if(!played)accepted=true;
     }
     statuses.set(row.id,row.status);
    });
    initialized=true;persistState();
    if(accepted)ring();
   }
   if(role==='customer'){
    const response=await fetch('/customer/live-alerts?messages=1',{credentials:'same-origin',cache:'no-store'});
    if(response.ok&&!response.redirected){
     for(const notice of await response.json()){
      if(notice.kind!=='driver-arrived'||noticeIds.has(notice.id))continue;
      const key=storageKey+'-arrival-'+notice.id;
      let played=false;try{played=localStorage.getItem(key)==='1';}catch(_){}
      noticeIds.add(notice.id);
      if(played)continue;
      try{localStorage.setItem(key,'1');}catch(_){}
      const date=String(notice.created_at||'');
      const age=Date.now()-Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(date)?date:date+'Z');
      if(Number.isFinite(age)&&age>=-10000&&age<120000)ring();
     }
    }
   }
   if(role==='driver'){
    const notices=await fetch('/driver/live-alerts?messages=1',{credentials:'same-origin'});
    if(notices.ok&&!notices.redirected){
     for(const notice of await notices.json()){
      if(!['delivery-claimed','delivery-reassigned','delivery-assigned'].includes(notice.kind)||notice.read_at||noticeIds.has(notice.id))continue;
      if(!activeDriverOrders.has(String(notice.order_id)))continue;
      const dismissedKey=storageKey+'-dismissed-'+notice.id;
      let dismissed=false;try{dismissed=localStorage.getItem(dismissedKey)==='1';}catch(_){}
      noticeIds.add(notice.id);
      if(dismissed)continue;
      if(enabled && notice.kind==='delivery-assigned'){
       const key=storageKey+'-assigned-'+notice.id;
       const date=String(notice.created_at||'');
       const age=Date.now()-Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(date)?date:date+'Z');
       let played=false;try{played=localStorage.getItem(key)==='1';}catch(_){}
       if(!played && Number.isFinite(age) && age>=-10000 && age<120000){
        try{localStorage.setItem(key,'1');}catch(_){}
        assignmentAlertUntil=Date.now()+120000;ring();
       }
      }

     }
    }
   }
   if(role==='customer')return;
   const response=await fetch('/'+role+'/live-alerts',{credentials:'same-origin',headers:{Accept:'application/json'}});
   if(!response.ok || response.redirected)return;
   const rows=await response.json();const fresh=rows.some(r=>!seen.has(r.id));
   rows.forEach(r=>seen.add(r.id));panel.replaceChildren();toggle.hidden=!rows.length;
   if(!rows.length){if(!activeTone&&(role!=='driver'||Date.now()>assignmentAlertUntil))stopAlert();panel.hidden=true;return;}
   persistState();
   const title=document.createElement('h2');title.textContent=role==='restaurant'?'New customer orders':'Delivery offers';panel.append(title);
   rows.forEach(row=>{
    const article=document.createElement('article'),text=document.createElement('p');
    text.textContent='#'+row.id+' · '+(row.restaurant_name||row.customer_name||'Order')+' · '+(row.address||'');
    const button=document.createElement('button');button.textContent='Accept';button.type='button';
    button.onclick=async()=>{
      button.disabled=true;
      const body=new FormData();body.set('csrfmiddlewaretoken',csrf());body.set('status','ACCEPTED');
      try{
       const url=role==='driver'?'/driver/order/'+row.id+'/accept':'/restaurant/order/'+row.id;
       const res=await fetch(url,{method:'POST',body,credentials:'same-origin'});
       if(!res.ok)throw new Error('Order is no longer available');
       stopAlert();article.remove();if(role==='driver') location.assign('/driver/order/'+row.id);
      }catch(e){text.textContent=e.message;button.disabled=false;}
    };
    article.append(text,button);panel.append(article);
   });
   if(fresh){panel.hidden=false;ring();clearTimeout(timer);if(role==='restaurant')timer=setTimeout(()=>{panel.hidden=true;},10000);}
  }finally{busy=false;}
 }
 loadPreference().then(()=>poll()).catch(()=>{soundStatus.textContent='Reconnecting notification settings…';});
 setInterval(()=>{if(storageKey)poll().catch(()=>{soundStatus.textContent='Reconnecting order notifications…';});},3000);
 setInterval(()=>loadPreference().catch(()=>{soundStatus.textContent='Reconnecting notification settings…';}),15000);

})();
(() => {
 if(!document.querySelector('[data-order-alerts]') || document.querySelector('[data-order-alerts]').dataset.orderAlerts==='customer')return;
 let busy=false;
 setInterval(async()=>{
  if(busy || document.hidden || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName))return;
  busy=true;
  try{
   const res=await fetch(location.pathname,{credentials:'same-origin'});
   if(!res.ok || res.redirected)return;
   const page=new DOMParser().parseFromString(await res.text(),'text/html');
   for(const selector of ['.order-board','.driver-jobs-panel']){
    const old=document.querySelector(selector),fresh=page.querySelector(selector);
    if(old && fresh)old.replaceWith(fresh);
   }
   if(!document.querySelector('[data-live-tracking]') && location.pathname.match(/\/(driver|restaurant)\/order\/\d+$/)){
    const old=document.querySelector('main>.card'),fresh=page.querySelector('main>.card');
    if(old && fresh)old.replaceWith(fresh);
    const history=document.querySelector('#timeline'),updated=page.querySelector('#timeline');
    if(history&&updated)history.replaceWith(updated);
   }
  }catch(_){}finally{busy=false;}
 },5000);
})();
