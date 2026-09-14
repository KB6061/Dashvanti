(() => {
 const header=document.querySelector('.customer-topbar'),panel=document.querySelector('.customer-notification-panel');
 if(!header||!panel)return;
 const updateHeight=()=>document.body.style.setProperty('--customer-nav-height',header.getBoundingClientRect().height+'px');
 new ResizeObserver(updateHeight).observe(header);updateHeight();
 const modeForm=document.querySelector('[data-header-mode-form]');
 function showMode(mode){document.querySelectorAll('[data-header-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.headerMode===mode)));}
 showMode(modeForm.elements.mode.value);
 let modeBusy=false;
 document.querySelectorAll('[data-header-mode]').forEach(button=>button.onclick=async()=>{
  if(modeBusy)return;modeBusy=true;
  const buttons=document.querySelectorAll('[data-header-mode]');buttons.forEach(b=>b.disabled=true);
  const data=new FormData(modeForm);data.set('mode',button.dataset.headerMode);
  try{
   const response=await fetch(modeForm.action,{method:'POST',body:data,credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});
   if(!response.ok||response.redirected)throw new Error();
   modeForm.elements.mode.value=button.dataset.headerMode;showMode(button.dataset.headerMode);
   document.querySelectorAll('[data-order-mode]').forEach(b=>b.classList.toggle('active',b.dataset.orderMode===button.dataset.headerMode));
   if(typeof setCustomerOrderMode==='function')setCustomerOrderMode(button.dataset.headerMode);
  }catch(_){button.title='Could not update order type. Please try again.';}
  finally{modeBusy=false;buttons.forEach(b=>b.disabled=false);}
 });
 const list=panel.querySelector('[data-notification-list]'),status=panel.querySelector('[data-notification-status]'),dot=document.querySelector('[data-notification-dot]');
 let loading=false,rows=[],loadedAt=0,selection=0;
 const cache=new Map(),reading=new Set(),readIds=new Set();
 const details=document.createElement('section');details.hidden=true;details.className='notification-details';list.after(details);
 const dateText=value=>{if(!value)return '';const utc=/Z$|[+-]\d\d:\d\d$/.test(value)?value:value+'Z';return new Date(utc).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short',hour12:true});};
 const updateDot=()=>{if(dot)dot.hidden=!rows.some(row=>!row.read_at&&!readIds.has(row.id));};
 const label=value=>(value||'').replaceAll('_',' ').replaceAll('-',' ');
 function showOrder(area,data){
  area.replaceChildren();
  const table=document.createElement('table');table.className='order-data-table';
  const values=[['Order','#'+data.order_id],['Restaurant',data.restaurant.name],['Restaurant activity',label(data.restaurant_status)],['Driver status',label(data.driver_status)||'Waiting for assignment'],['Delivery address',data.destination]];
  for(const [name,value] of values){const tr=document.createElement('tr'),th=document.createElement('th'),td=document.createElement('td');th.textContent=name;td.textContent=value;tr.append(th,td);table.append(tr);}
  area.append(table);
  const link=document.createElement('a');link.href='/customer/order/'+data.order_id+'/track';link.textContent='Open live tracking';area.append(link);
 }
 async function markRead(row,entry){
  if(row.read_at||readIds.has(row.id)||reading.has(row.id))return;
  reading.add(row.id);readIds.add(row.id);entry.classList.remove('unread');updateDot();
  try{
   const data=new FormData(modeForm);data.set('id',row.id);
   const response=await fetch('/customer/notification-panel',{method:'POST',body:data,credentials:'same-origin',signal:AbortSignal.timeout(10000)});
   if(!response.ok||response.redirected)throw new Error();
   row.read_at=true;
  }catch(_){readIds.delete(row.id);entry.classList.add('unread');updateDot();status.textContent='Details opened. Could not save read status; reopen to retry.';}
  finally{reading.delete(row.id);}
 }
 function openDetails(row,entry){
  const version=++selection;list.hidden=true;details.hidden=false;details.replaceChildren();
  const back=document.createElement('button');back.type='button';back.textContent='← Notifications';
  back.onclick=()=>{selection++;details.hidden=true;list.hidden=false;};
  const title=document.createElement('h2'),body=document.createElement('p'),date=document.createElement('small'),area=document.createElement('div');
  title.textContent=label(row.kind)||'Notification';body.textContent=row.body;date.textContent=dateText(row.created_at);
  area.setAttribute('aria-live','polite');details.append(back,title,body,date,area);
  void markRead(row,entry);
  if(!row.order_id)return;
  const cached=cache.get(row.order_id);
  if(cached)showOrder(area,cached.data);else area.textContent='Loading order details…';
  if(cached&&Date.now()-cached.at<15000)return;
  fetch('/customer/order/'+row.order_id+'/tracking',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)})
   .then(response=>{if(!response.ok||response.redirected)throw new Error();return response.json();})
   .then(data=>{if(cache.size>=100)cache.delete(cache.keys().next().value);cache.set(row.order_id,{data,at:Date.now()});if(version===selection)showOrder(area,data);})
   .catch(()=>{if(version===selection&&!cached){area.textContent='Order details unavailable. ';const retry=document.createElement('button');retry.type='button';retry.textContent='Retry';retry.onclick=()=>openDetails(row,entry);area.append(retry);}});
 }
 async function load(){
  if(loading)return;loading=true;
  try{
   const response=await fetch('/customer/notification-panel',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)});
   if(!response.ok||response.redirected)throw new Error('Unable to load notifications.');
   rows=await response.json();loadedAt=Date.now();updateDot();
   const fragment=document.createDocumentFragment();
   rows.forEach(row=>{
    const entry=document.createElement('button');entry.type='button';entry.className='notification-entry'+(row.read_at||readIds.has(row.id)?'':' unread');
    const title=document.createElement('strong'),body=document.createElement('p'),date=document.createElement('small');
    title.textContent=label(row.kind)||'Update';body.textContent=row.body;date.textContent=dateText(row.created_at);
    entry.append(title,body,date);entry.onclick=()=>openDetails(row,entry);fragment.append(entry);
   });
   list.replaceChildren(fragment);
   status.textContent=rows.length?'You’re all caught up.':'No notifications yet.';
  }catch(error){status.textContent=error.message;}finally{loading=false;}
 }
 document.querySelector('[data-notifications-open]').onclick=()=>{selection++;details.hidden=true;list.hidden=false;if(!panel.open)panel.showModal();if(Date.now()-loadedAt>15000)void load();};
 panel.querySelector('[data-notifications-close]').onclick=()=>{selection++;panel.close();};
 panel.addEventListener('click',event=>{
  if(event.target!==panel)return;
  const rect=panel.getBoundingClientRect();
  if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)panel.close();
 });
 panel.addEventListener('close',()=>selection++);
 load();setInterval(()=>{if(!document.hidden)load();},60000);
})();