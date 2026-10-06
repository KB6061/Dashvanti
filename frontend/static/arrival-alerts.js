(() => {
 const host=document.querySelector('[data-order-alerts="customer"]');if(!host)return;
 const audio=new Audio('/sounds/arrival.mp3');audio.preload='auto';audio.volume=0.65;
 const pending=new Map(),playedIds=new Set();const prefix='dashvanti-arrival-played-';let soundEnabled=true,blocked=false,busy=false,priming=null;
 try{soundEnabled=localStorage.getItem('dashvanti-arrival-sound')!=='muted';}catch(_){}
 const toggle=document.createElement('button');toggle.type='button';toggle.className='arrival-sound-toggle';
 const notice=document.createElement('small');notice.setAttribute('role','status');notice.hidden=true;
 (document.querySelector('[data-sidebar-sounds]')||document.querySelector('.customer-topbar nav')||host).append(toggle,notice);
 const sync=()=>{toggle.textContent=blocked&&soundEnabled?'Enable arrival sound':soundEnabled?'Arrival sound on':'Arrival sound off';toggle.setAttribute('aria-label',blocked&&soundEnabled?'Enable arrival sound':soundEnabled?'Mute arrival sound':'Unmute arrival sound');toggle.setAttribute('aria-pressed',String(!soundEnabled));};
 const played=id=>{if(playedIds.has(id))return true;try{return Date.now()-Number(localStorage.getItem(prefix+id)||0)<7*86400000;}catch(_){return false;}};
 const mark=id=>{playedIds.add(id);try{localStorage.setItem(prefix+id,String(Date.now()));}catch(_){}pending.delete(id);};
 function playArrivalSound(){
  if(!soundEnabled)return Promise.resolve(false);
  audio.muted=false;audio.currentTime=0;return audio.play().then(()=>true);
 }
 const flush=async()=>{
  if(busy||!soundEnabled)return;busy=true;
  try{
   if(priming)await priming;
   for(const [id,data] of pending){
    if(played(id)){pending.delete(id);continue;}
    if(data.timestamp&&Date.now()-data.timestamp>120000){pending.delete(id);continue;}
    const attempt=async()=>{if(played(id)){pending.delete(id);return;}if(!soundEnabled)return;
     try{if(await playArrivalSound()){mark(id);blocked=false;notice.hidden=true;}}
     catch(error){if(!soundEnabled)return;blocked=error.name==='NotAllowedError';notice.textContent=blocked?'Tap Enable arrival sound to hear the alert.':'Arrival sound is temporarily unavailable.';notice.hidden=false;}
    };
    if(navigator.locks)await navigator.locks.request(prefix+id,attempt);else await attempt();
    if(blocked)break;
   }
  }finally{busy=false;sync();}
 };
 const unlock=()=>{
  if(!soundEnabled||priming||!audio.paused)return;
  audio.muted=true;
  priming=audio.play().then(()=>{audio.pause();audio.currentTime=0;blocked=false;notice.hidden=true;}).catch(()=>{}).finally(()=>{audio.muted=false;priming=null;sync();void flush();});
 };
 function toggleSound(){
  soundEnabled=!soundEnabled;try{localStorage.setItem('dashvanti-arrival-sound',soundEnabled?'enabled':'muted');}catch(_){}
  if(!soundEnabled){audio.pause();pending.forEach((_,id)=>mark(id));notice.hidden=true;}else unlock();sync();
 }
 toggle.onclick=()=>{if(blocked&&soundEnabled){unlock();void flush();}else toggleSound();};
 document.addEventListener('pointerdown',unlock);document.addEventListener('keydown',unlock);
 window.addEventListener('storage',event=>{if(event.key==='dashvanti-arrival-sound'){soundEnabled=event.newValue!=='muted';if(!soundEnabled)audio.pause();sync();}});
 window.addEventListener('dashvanti:driver-arriving',event=>{
  const data=event.detail;const id=data.event_id||'arrival:'+data.order_id+':'+data.driver_id;
  if(data.event!=='driver_arriving'||!Number.isInteger(data.order_id)||data.order_id<=0||played(id))return;
  if(!soundEnabled){mark(id);return;}pending.set(id,data);void flush();
 });
 window.addEventListener('pagehide',()=>audio.pause());
 window.playArrivalSound=playArrivalSound;window.toggleArrivalSound=toggleSound;sync();
})();
