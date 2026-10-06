self.addEventListener('install',event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 event.waitUntil((async()=>{
  const id=Number(event.notification.data?.order_id);if(!Number.isInteger(id)||id<=0)return;
  let destination='/driver/dashboard';
  if(['accept','reject'].includes(event.action)){
   try{
    const page=await fetch('/driver/dashboard',{credentials:'same-origin',cache:'no-store'});if(!page.ok||page.redirected)throw Error('Login required');
    const html=await page.text();const token=html.match(/name=["']csrfmiddlewaretoken["'][^>]*value=["']([^"']+)/)?.[1];if(!token)throw Error('Session expired');
    const body=new URLSearchParams({csrfmiddlewaretoken:token});
    const response=await fetch('/driver/order/'+id+'/'+event.action,{method:'POST',body,credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});if(!response.ok)throw Error('Order unavailable');
    if(event.action==='accept'){const result=await response.json();destination=result.queued?'/driver/dashboard':result.redirect_url||'/driver/order/'+id;}
   }catch(_){destination='/driver/dashboard';}
  }
  const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
  windows.forEach(client=>client.postMessage({type:'offers-refresh'}));
  const existing=windows.find(client=>new URL(client.url).pathname===destination);
  if(existing)await existing.focus();else await self.clients.openWindow(destination);
 })());
});
