(() => {
 const role=['driver','restaurant','customer','admin'].find(role=>document.body.classList.contains(role+'-portal'));
 if(!role||!document.querySelector('form[action$="/logout"],.portal-logout-button,[data-order-alerts]'))return;
 let busy=false,queued=false;
 const selectors=['.tracking-panel','.order-board','.driver-live-status','.driver-requests-panel','.driver-upcoming-panel','main table tbody','.admin-kpis','.admin-volume-chart','.admin-rank-list','.restaurant-status','.driver-badges','[data-live-refresh]','.history-order summary','.customer-live-card:not([data-live-tracking])','[data-order-actions]','#order-status','#timeline','[data-delivery-rating]'];
 const statuses=new Map(),updatedAt=new Map();let statusBusy=false;
 const readStatus=node=>node.dataset.status||node.textContent.trim().toUpperCase().replaceAll(' ','_');
 document.querySelectorAll('[data-order-status]').forEach(node=>statuses.set(Number(node.dataset.orderStatus),readStatus(node)));
 const statusRefresh=async()=>{
  if(statusBusy||document.hidden)return;
  const ids=[...new Set(Array.from(document.querySelectorAll('[data-order-status],[data-live-order-id],[data-order-url]')).map(node=>Number(node.dataset.orderStatus||node.dataset.liveOrderId||node.dataset.orderUrl?.match(/\/order\/(\d+)/)?.[1])).filter(Number.isInteger).filter(id=>id>0))].slice(0,500);
  if(!ids.length)return;statusBusy=true;const started=Date.now();
  try{
   const response=await fetch('/'+role+'/live-status?'+new URLSearchParams({ids:ids.join(',')}),{credentials:'same-origin',cache:'no-store',signal:window.dashvantiTimeoutSignal(10000)});
   if(!response.ok||response.redirected)return;
   for(const row of await response.json()){
    if((updatedAt.get(row.id)||0)>started)continue;
    if(statuses.get(row.id)!==row.status)window.dispatchEvent(new CustomEvent('dashvanti:order-update',{detail:{order_id:row.id,status:row.status,canonical_status:row.status,driver_id:row.driver_id,source:'poll'}}));
   }
  }catch(_){}finally{statusBusy=false;}
 };
 const editing=element=>element.contains(document.activeElement)&&document.activeElement.matches('input,textarea,select,button,[contenteditable]')&&!(document.activeElement.matches('button')&&document.activeElement.closest('form')?.querySelector('[name=status]'));
 const patch=(old,fresh)=>{
  if(old.dataset.submitting==='true'||old.querySelector('[data-submitting="true"]'))return;
  if(editing(old))return;
  if(old.matches('input:not([type=hidden]),textarea,select,[data-google-map],dialog')||old.querySelector('[data-google-map]'))return;
  if(old.matches('form')&&old.querySelector('input:not([type=hidden]),textarea,select'))return;
  if(old.matches('input[type=hidden]')){old.value=fresh.value;return;}
  if(old.tagName!==fresh.tagName)return;
  const attributes=['class','aria-valuenow','hidden'];
  if(old.matches('button'))attributes.push('name','value','formaction','disabled');
  if(old.matches('form'))attributes.push('action','method');
  if(old.matches('a'))attributes.push('href');
  attributes.forEach(name=>{if(fresh.hasAttribute(name)){if(old.getAttribute(name)!==fresh.getAttribute(name))old.setAttribute(name,fresh.getAttribute(name));}else if(name!=='class' && old.hasAttribute(name))old.removeAttribute(name);});
  if(old.children.length!==fresh.children.length){
   if(old.tagName==='TBODY'){
    const key=row=>row.dataset.orderUrl||row.cells?.[0]?.textContent.trim();
    const rows=new Map(Array.from(old.children).map(row=>[key(row),row]));
    const incoming=new Set(Array.from(fresh.children).map(key));
    rows.forEach((row,id)=>{if(!incoming.has(id)&&!editing(row)&&!row.querySelector('details[open]'))row.remove();});
    Array.from(fresh.children).forEach(row=>{const existing=rows.get(key(row));if(existing)patch(existing,row);else old.append(row.cloneNode(true));});
    return;
   }
   const cards=Array.from(fresh.querySelectorAll(':scope > [data-live-order-id]'));
   if(cards.length){
    const ids=new Set(cards.map(card=>card.dataset.liveOrderId));
    old.querySelectorAll(':scope > [data-live-order-id]').forEach(card=>{if(!ids.has(card.dataset.liveOrderId)&&!editing(card))card.remove();});
    cards.forEach(card=>{const existing=Array.from(old.children).find(child=>child.dataset.liveOrderId===card.dataset.liveOrderId);if(existing)patch(existing,card);else old.append(card.cloneNode(true));});
    return;
   }
   if(!old.querySelector('input:not([type=hidden]),textarea,select'))old.replaceChildren(...Array.from(fresh.childNodes).map(node=>node.cloneNode(true)));
   return;
  }
  if(!old.children.length){if(old.textContent!==fresh.textContent)old.textContent=fresh.textContent;return;}
  Array.from(old.children).forEach((child,index)=>patch(child,fresh.children[index]));
 };
 const refresh=async()=>{
  if(busy){queued=true;return;}if(document.hidden)return;
  busy=true;
  try{
   void fetch('/'+role+'/navigation-state',{credentials:'same-origin',cache:'no-store',signal:window.dashvantiTimeoutSignal(6000)}).then(async response=>{
    if(!response.ok||response.redirected)return;
    const snapshot=await response.json();window.dashvantiNavigationActive=!!snapshot.navigation_active;
    window.dispatchEvent(new CustomEvent('dashvanti:portal-live',{detail:snapshot}));
   }).catch(()=>{});
   const pageResponse=await fetch(location.href,{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'fetch'},signal:window.dashvantiTimeoutSignal(6000)});
   if(!pageResponse.ok||pageResponse.redirected)return;
   const page=new DOMParser().parseFromString(await pageResponse.text(),'text/html');
   selectors.forEach(selector=>{
    const current=Array.from(document.querySelectorAll(selector)).filter(element=>!element.closest('[data-google-map]'));
    const incoming=Array.from(page.querySelectorAll(selector)).filter(element=>!element.closest('[data-google-map]'));
    current.forEach((old,index)=>{if(incoming[index])patch(old,incoming[index]);});
   });
  }catch(_){}finally{busy=false;if(queued){queued=false;void refresh();}}
 };
 window.addEventListener('dashvanti:order-update',event=>{
  const data=event.detail;
  const status=data.canonical_status||data.status;if(typeof status!=='string')return;
  statuses.set(Number(data.order_id),status);updatedAt.set(Number(data.order_id),Date.now());
  const display=(data.canonical_status || data.status).replaceAll('_',' ').toLowerCase().replace(/\b\w/g,value=>value.toUpperCase());
  document.querySelectorAll('[data-order-status="'+Number(data.order_id)+'"]').forEach(node=>{node.textContent=display;node.dataset.status=status;if(node.classList.contains('admin-status'))node.className='admin-status status-'+status.toLowerCase();});
  document.querySelectorAll('[data-history-status]').forEach(node=>{if(node.dataset.orderUrl?.endsWith('/order/'+data.order_id))node.dataset.historyStatus=status;});
  const detail=location.pathname.match(/\/order\/(\d+)/);
  if(detail && Number(detail[1])===data.order_id){const status=document.getElementById('order-status');if(status)status.textContent=display;}
  const row=document.querySelector('[data-order-url="/admin/order/'+data.order_id+'"]');
  const badge=row?.querySelector('.admin-status');if(badge){badge.textContent=display;badge.className='admin-status status-'+status.toLowerCase();}
  void refresh();
 });
 window.addEventListener('dashvanti:order-action',()=>{void refresh();});
 const resume=()=>{if(!document.hidden){void statusRefresh();void refresh();}};
 document.addEventListener('visibilitychange',resume);window.addEventListener('focus',resume);window.addEventListener('pageshow',resume);window.addEventListener('online',resume);window.addEventListener('dashvanti:gps-connected',resume);
 resume();setInterval(()=>{void statusRefresh();void refresh();},5000);
})();
