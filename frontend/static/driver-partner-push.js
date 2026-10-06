(() => {
 const button=document.querySelector('[data-driver-push]');if(!button)return;
 button.addEventListener('click',async()=>{
  button.disabled=true;
  try{
   const response=await fetch('/driver/partner/push-config',{credentials:'same-origin'});
   if(!response.ok)throw Error('Push settings unavailable');
   const cfg=await response.json();
   if(!cfg.firebase?.apiKey||!cfg.vapid_key)throw Error('Push notifications are not configured yet');
   const app=await import('https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js');
   const messaging=await import('https://www.gstatic.com/firebasejs/10.12.5/firebase-messaging.js');
   if(!await messaging.isSupported())throw Error('Push is not supported on this browser');
   if(await Notification.requestPermission()!=='granted')throw Error('Allow notifications in browser settings');
   const worker=await navigator.serviceWorker.register('/driver/notifications-worker.js',{scope:'/driver/'});
   const client=messaging.getMessaging(app.getApps().find(a=>a.name==='dashvanti-driver')||app.initializeApp(cfg.firebase,'dashvanti-driver'));
   const token=await messaging.getToken(client,{vapidKey:cfg.vapid_key,serviceWorkerRegistration:worker});
   let id=localStorage.getItem('dashvanti-driver-installation');
   if(!id){id=crypto.randomUUID();localStorage.setItem('dashvanti-driver-installation',id);}
   const saved=await fetch('/driver/partner/devices',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({installation_id:id,token})});
   if(!saved.ok)throw Error('Could not register notification device');
   messaging.onMessage(client,message=>{window.dispatchEvent(new Event('dashvanti:offers-refresh'));button.textContent=message.notification?.title||'New driver update';});
   button.textContent='Push notifications enabled';
  }catch(e){button.textContent=e.message;}finally{button.disabled=false;}
 });
})();
