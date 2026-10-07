(() => {
 const host=document.querySelector('[data-live-tracking][data-tracking-role="driver"]');
 if(!host)return;

 const dialog=document.createElement('dialog');
 dialog.className='driver-navigation-dialog';
 dialog.innerHTML='<button type="button" data-close aria-label="Close">×</button><h2>Navigation</h2><p data-destination></p><p data-route-summary>Start navigation for spoken directions.</p><p data-error role="status"></p><a class="driver-go" data-google-navigation target="_blank" rel="noopener">Open navigation app</a><button type="button" data-start>Start navigation in portal</button>';
 document.body.append(dialog);

 const map=host.querySelector('[data-google-map]');
 const navButton=document.createElement('button');
 navButton.type='button';
 navButton.className='driver-floating-navigate';
 navButton.textContent='Navigate';
 navButton.hidden=true;
 document.body.append(navButton);
 const activate=()=>{host.classList.add('driver-navigation-active');window.dispatchEvent(new Event('dashvanti:navigation-start'));host.scrollIntoView({behavior:'smooth',block:'start'});const directions=host.querySelector('details');if(directions)directions.open=true;if(window.google?.maps&&map?.dashvantiMapState)google.maps.event.trigger(map.dashvantiMapState.map,'resize');};
 navButton.onclick=()=>{updateGoogleNavigation();if(!dialog.open)dialog.showModal();};
 dialog.addEventListener('close',()=>{navButton.hidden=false;});

 let phase='',current;
 const googleNavigation=dialog.querySelector('[data-google-navigation]');
 const updateGoogleNavigation=()=>{
  const customerLeg=['PICKED_UP','ON_THE_WAY_TO_CUSTOMER','ARRIVED_AT_CUSTOMER'].includes(current?.driver_status);
  const destination=(customerLeg?current?.destination:current?.restaurant?.address)?.trim();
  if(!destination){
   googleNavigation.removeAttribute('href');
   dialog.querySelector('[data-error]').textContent='Destination address is unavailable.';
   return;
  }
  const url=new URL('https://www.google.com/maps/dir/');
  url.search=new URLSearchParams({api:'1',destination,travelmode:'driving',dir_action:'navigate'}).toString();
  googleNavigation.href=url.href;
  dialog.querySelector('[data-error]').textContent='';
 };
 googleNavigation.addEventListener('click',event=>{
  if(!googleNavigation.hasAttribute('href')){event.preventDefault();return;}
  activate();
  voiceEnabled=false;syncVoice();
  window.speechSynthesis?.cancel();
  dialog.close();
 });
 const shown=new Set();

 let voiceEnabled=false,lastSpoken='';
 let voiceButton,voiceStatus,lastGuidance=null,spokenGuidance='',lastBrowserGuidance=0;
 const femaleVoice=()=>window.speechSynthesis?.getVoices().find(voice=>/^en/i.test(voice.lang)&&/female|samantha|victoria|zira|hazel|susan|karen|moira|tessa|aria|jenny|sonia|salli|joanna|google uk english female/i.test(voice.name));
 const syncVoice=()=>{if(voiceButton){voiceButton.textContent=voiceEnabled?'Mute voice':'Unmute voice';voiceButton.setAttribute('aria-pressed',String(!voiceEnabled));}};
 const voiceControl=()=>{
  if(voiceButton||!window.google?.maps||!map?.dashvantiMapState)return;
  voiceButton=document.createElement('button');voiceButton.type='button';voiceButton.className='navigation-voice-toggle';
  const dock=document.createElement('div');dock.className='navigation-bottom-controls';dock.setAttribute('aria-label','Navigation controls');
  ['car','arrow'].forEach(kind=>{const button=document.createElement('button');button.type='button';button.className='navigation-avatar-toggle';button.setAttribute('aria-label',kind==='car'?'Use car icon':'Use arrow icon');button.innerHTML=kind==='car'?'<img src="/static/navigation-car.png?v=1" alt="" width="34" height="34">':'<span aria-hidden="true">➤</span>';const sync=()=>button.setAttribute('aria-pressed',String(window.dashvantiNavigationAvatar?.()===kind));button.onclick=()=>window.dashvantiSetNavigationAvatar?.(kind);window.addEventListener('dashvanti:avatar-change',sync);sync();dock.append(button);});
  dock.append(voiceButton,navButton);
  voiceButton.onclick=()=>{voiceEnabled=!voiceEnabled;window.speechSynthesis?.cancel();lastSpoken='';spokenGuidance='';syncVoice();if(voiceEnabled)speak(lastGuidance?.instruction || 'Navigation voice on');};
  const footer=host.querySelector('.driver-navigation-arrival');if(footer)host.insertBefore(dock,footer);else host.append(dock);syncVoice();
  voiceStatus=document.createElement('small');voiceStatus.hidden=true;voiceStatus.setAttribute('role','status');
  voiceStatus.style.cssText='max-width:180px;padding:8px;background:white;border-radius:8px;margin:8px';
  dock.append(voiceStatus);
 };
 window.addEventListener('dashvanti:navigation-start',voiceControl);
 window.speechSynthesis?.addEventListener('voiceschanged',()=>{if(voiceEnabled && !lastSpoken && lastGuidance)speak(lastGuidance.instruction);});
 const speak=(message)=>{
  if(!voiceEnabled||!message||!('speechSynthesis' in window))return;
  if(message===lastSpoken)return;
  lastSpoken=message;
  window.speechSynthesis.cancel();
  const utterance=new SpeechSynthesisUtterance(message);
  const voice=femaleVoice();
  if(!voice){lastSpoken='';const message='Install an English female speech voice in device settings to hear directions.';dialog.querySelector('[data-error]').textContent=message;if(voiceStatus){voiceStatus.textContent=message;voiceStatus.hidden=false;}return;}
  if(voiceStatus)voiceStatus.hidden=true;
  utterance.voice=voice;utterance.lang=voice.lang;
  utterance.rate=0.95;
  utterance.pitch=1;
  utterance.volume=1;
  window.speechSynthesis.speak(utterance);
 };
 dialog.querySelector('[data-close]').onclick=()=>dialog.close();

 window.addEventListener('dashvanti:tracking',event=>{
  const data=event.detail;
  voiceControl();
  if(!data.restaurant||!data.driver_status)return;
  current=data;
  updateGoogleNavigation();
  if(['DELIVERED','CANCELLED','CANCELED','REJECTED'].includes(data.driver_status)){
   if(dialog.open)dialog.close();
   navButton.hidden=true;
   voiceEnabled=false;
   window.speechSynthesis?.cancel();
   return;
  }
  const customerLeg=['PICKED_UP','ON_THE_WAY_TO_CUSTOMER','ARRIVED_AT_CUSTOMER','DELIVERED'].includes(data.driver_status);
  const next=data.driver_status==='DRIVER_ASSIGNED'?'pickup':data.driver_status==='PICKED_UP'?'delivery':'';
  if(!next){if(dialog.open)dialog.close();phase='';navButton.hidden=false;return;}
  if(phase!==next){
   phase=next;
   dialog.querySelector('h2').textContent=next==='pickup'?'Navigate to Restaurant':'Navigate to Customer';
   const address=next==='pickup'?data.restaurant.address:data.destination;
   dialog.querySelector('[data-destination]').textContent=(next==='pickup'?data.restaurant.name+' · ':data.destination_name || '')+address;
   dialog.querySelector('[data-route-summary]').textContent='Calculating distance and ETA…';
  }
  if(!shown.has(next)){
    shown.add(next);
    navButton.hidden=false;
    dialog.showModal();
    if(window.google?.maps&&map?.dashvantiMapState)google.maps.event.trigger(map.dashvantiMapState.map,'resize');
  }
 });

 window.addEventListener('dashvanti:route-ready',event=>{
  const data=event.detail;
  if(String(data.orderId)!==host.dataset.orderId||data.status!==current?.driver_status)return;
  dialog.querySelector('[data-route-summary]').textContent=data.miles.toFixed(1)+' miles · ETA '+data.minutes+' min';
 });

 dialog.querySelector('[data-start]').onclick=()=>{
  dialog.close();
  voiceEnabled=true;lastSpoken='';spokenGuidance='';syncVoice();
  window.speechSynthesis?.cancel();
  activate();
  navButton.hidden=false;
  speak(lastGuidance?.instruction || 'Navigation started. Follow the route on the map.');
 };

 window.addEventListener('dashvanti:navigation-route',event=>{
  if(dialog.open)dialog.querySelector('[data-destination]').textContent=event.detail.origin+' → '+event.detail.destination;
 });

 const guidance=data=>{
  lastGuidance=data;voiceControl();
  const distance=data.distanceToTurn ?? data.distance_to_turn;
  const id=(data.instructionId || data.instruction_id || data.instruction)+':'+(distance<35?'turn':'approach');
  if(!voiceEnabled || !data.instruction || distance>250 || id===spokenGuidance)return;
  spokenGuidance=id;
  speak((distance>=35?'In '+Math.round(distance/10)*10+' meters, ':'')+data.instruction);
 };
 window.addEventListener('dashvanti:navigation-guidance',event=>{lastBrowserGuidance=Date.now();guidance(event.detail);});
 window.addEventListener('dashvanti:navigation-update',event=>{if(Date.now()-lastBrowserGuidance>10000 && String(event.detail.order_id)===host.dataset.orderId)guidance(event.detail);});
 window.addEventListener('pagehide',()=>{voiceEnabled=false;window.speechSynthesis?.cancel();});
})();
