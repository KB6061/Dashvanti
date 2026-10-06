(() => {
 if(!location.pathname.startsWith('/customer/'))return;
 let dialog;
 function create(){
  if(dialog)return;
  dialog=document.createElement('dialog');dialog.className='closed-store-popup';dialog.setAttribute('aria-labelledby','closed-store-title');
  dialog.innerHTML='<button type="button" data-close aria-label="Close">×</button><h2 id="closed-store-title">This store is currently closed</h2><div class="closed-store-heading"><div><strong>Hungry now?</strong><p>View other restaurants that are open</p></div><div><button type="button" data-all>See All</button><button type="button" data-left aria-label="Previous restaurants">‹</button><button type="button" data-right aria-label="Next restaurants">›</button></div></div><div class="closed-store-list"></div><footer><span>You can still browse this restaurant’s menu.</span><button type="button" data-browse>Browse menu</button></footer>';
  document.body.append(dialog);dialog.querySelector('[data-close]').onclick=()=>dialog.close();
  const list=dialog.querySelector('.closed-store-list');
  dialog.querySelector('[data-left]').onclick=()=>list.scrollBy({left:-list.clientWidth*.8,behavior:'smooth'});
  dialog.querySelector('[data-right]').onclick=()=>list.scrollBy({left:list.clientWidth*.8,behavior:'smooth'});
  dialog.querySelector('[data-all]').onclick=()=>{list.classList.toggle('expanded');};
 }
 function show(data){
  create();dialog.querySelector('h2').textContent='This store is currently closed';
  const list=dialog.querySelector('.closed-store-list');list.replaceChildren();list.classList.remove('expanded');
  for(const store of data.alternatives){
   const link=document.createElement('a');link.href='/customer/restaurant/'+store.id;
   if(store.photo_id){const img=document.createElement('img');img.src='/customer/files/'+store.photo_id+'?size=menu';img.alt=store.name;img.loading='lazy';link.append(img);}
   else{const fallback=document.createElement('div');fallback.className='closed-store-placeholder';fallback.textContent=store.name.slice(0,1);link.append(fallback);}
   const name=document.createElement('strong'),cuisine=document.createElement('span'),open=document.createElement('small');
   name.textContent=store.name;cuisine.textContent=store.cuisine;open.textContent='Open for orders';link.append(name,cuisine,open);list.append(link);
  }
  if(!data.alternatives.length)list.textContent='No other open restaurants are available right now.';
  dialog.querySelector('[data-all]').hidden=!data.alternatives.length;
  dialog.querySelector('[data-browse]').onclick=()=>{dialog.close();if(location.pathname!=='/customer/restaurant/'+data.restaurant_id)location.assign('/customer/restaurant/'+data.restaurant_id+'?browse=1');};
  if(!dialog.open)dialog.showModal();
 }
 window.dashvantiStoreAvailable=async(entity,id)=>{
  try{
   const response=await fetch('/customer/'+entity+'/'+id+'/order-availability',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)});
   if(!response.ok||response.redirected)throw new Error();
   const data=await response.json();if(!data.is_open)show(data);return data.is_open;
  }catch(error){
   create();dialog.querySelector('h2').textContent='Unable to check restaurant availability';
   dialog.querySelector('.closed-store-list').textContent='Please close this window and try again.';
   dialog.querySelector('[data-browse]').onclick=()=>dialog.close();
   if(!dialog.open)dialog.showModal();throw error;
  }
 };
 const restaurant=location.pathname.match(/^\/customer\/restaurant\/(\d+)$/);
 if(restaurant&&!new URLSearchParams(location.search).has('browse'))window.dashvantiStoreAvailable('restaurant',restaurant[1]).catch(()=>{});
 const form=document.querySelector('[data-checkout-form]');
 if(form)form.addEventListener('submit',async event=>{
  if(form.dataset.availabilityChecked==='1'){delete form.dataset.availabilityChecked;return;}
  event.preventDefault();event.stopImmediatePropagation();if(form.dataset.checking==='1')return;
  form.dataset.checking='1';
  try{
   const markers=JSON.parse(document.getElementById('checkout-restaurant-markers')?.textContent||'[]');
   for(const marker of markers){if(!await window.dashvantiStoreAvailable('restaurant',marker.id.replace('restaurant-','')))return;}
   form.dataset.availabilityChecked='1';form.requestSubmit(event.submitter||undefined);delete form.dataset.availabilityChecked;
  }catch(_){}finally{delete form.dataset.checking;}
 },true);
})();