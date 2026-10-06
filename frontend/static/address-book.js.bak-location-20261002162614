(() => {
 const popup=document.getElementById('address-book-popup');if(!popup)return;
 const anchor=document.querySelector('[data-address-book-open]');
 const positionPopup=()=>{
  if(!popup.open||!anchor)return;
  const rect=anchor.getBoundingClientRect(),viewport=window.visualViewport;
  const width=viewport?.width||window.innerWidth,height=viewport?.height||window.innerHeight;
  const top=Math.min(rect.bottom+8,height-100);
  popup.style.setProperty('--address-popup-left',Math.max(8,Math.min(rect.left,width-Math.min(440,width-16)-8))+'px');
  popup.style.setProperty('--address-popup-top',Math.max(8,top)+'px');
  popup.style.setProperty('--address-popup-height',Math.max(80,height-top-8)+'px');
 };
 window.addEventListener('resize',positionPopup);
 window.addEventListener('scroll',positionPopup,{passive:true});
 window.visualViewport?.addEventListener('resize',positionPopup);
 const form=popup.querySelector('form'),status=popup.querySelector('[data-address-book-status]'),save=form.querySelector('[type=submit]');
 const header=document.querySelector('[data-customer-header-address]');
 let busy=false;
 popup.querySelector('gmp-place-autocomplete').addEventListener('input',()=>{
  document.dispatchEvent(new Event('dashvanti:cancel-address-lookup'));
  status.textContent='';save.disabled=true;form.elements.latitude.value='';form.elements.longitude.value='';
 });
 function showAddress(address){if(address){header.textContent=address;header.parentElement.title=address;}}
 async function load(){
  const response=await fetch('/customer/address-book',{credentials:'same-origin'});
  if(!response.ok||response.redirected)throw new Error('Unable to load addresses.');
  const data=await response.json();showAddress(data.location?.address || data.addresses.find(a=>a.is_default)?.details);
  const list=popup.querySelector('[data-address-book-list]');list.replaceChildren();
  data.addresses.forEach(address=>{
   const button=document.createElement('button');button.type='button';
   const radio=document.createElement('span');radio.className='address-book-radio'+(address.details===data.location?.address?' selected':'');
   const text=document.createElement('span');text.className='address-book-row-text';
   const name=document.createElement('strong');name.textContent=address.label+(address.is_default?' (Default)':'');
   const details=document.createElement('small');details.textContent=address.details;
   text.append(name,details);const edit=document.createElement('span');edit.textContent='✎';edit.setAttribute('aria-hidden','true');button.append(radio,text,edit);
   button.onclick=()=>{
    form.hidden=false;form.reset();form.elements.id.value=address.id;form.elements.label.value=address.label;
    form.elements.address.value=address.details;form.elements.is_default.checked=address.is_default;
    popup.querySelector('gmp-place-autocomplete').value='';
    form.elements.latitude.value='';form.elements.longitude.value='';
    save.disabled=true;status.textContent='Locating address…';
    document.dispatchEvent(new CustomEvent('dashvanti:address-geocode',{detail:{address:address.details}}));
   };list.append(button);
  });
 }
 document.querySelector('[data-address-book-open]').onclick=()=>{
  form.reset();form.elements.id.value='';save.disabled=true;status.textContent='';
  form.hidden=true;popup.showModal();positionPopup();load().catch(error=>status.textContent=error.message);
 };
 popup.querySelector('[data-address-book-close]').onclick=()=>popup.close();
 popup.addEventListener('close',()=>document.dispatchEvent(new Event('dashvanti:cancel-address-lookup')));
 popup.querySelector('[data-address-book-new]').onclick=()=>{
  document.dispatchEvent(new Event('dashvanti:cancel-address-lookup'));
  form.hidden=false;form.reset();form.elements.id.value='';save.disabled=true;status.textContent='';
  popup.querySelector('gmp-place-autocomplete').focus();
 };
 document.addEventListener('dashvanti:address-selected',event=>{
  if(!popup.open)return;event.stopImmediatePropagation();
  form.hidden=false;const detail=event.detail;
  form.elements.address.value=detail.address;form.elements.latitude.value=detail.latitude;
  form.elements.longitude.value=detail.longitude;save.disabled=false;status.textContent='Choose a label and default setting, then save.';
 },true);
 document.addEventListener('dashvanti:address-error',event=>{if(popup.open)status.textContent=event.detail?.message||'Address lookup failed';});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;save.disabled=true;status.textContent='Saving…';
  try{
   const response=await fetch('/customer/address-book',{method:'POST',body:new FormData(form),credentials:'same-origin'});
   if(!response.ok||response.redirected)throw new Error('Unable to save address. Please try again.');
   const data=await response.json();showAddress(data.details);
   window.dashvantiManualAddress=true;
   document.dispatchEvent(new CustomEvent('dashvanti:map-select',{detail:{mapId:'customer-pickup-map',id:'customer-current-address',name:'Your address',address:data.details}}));
   popup.close();
  }catch(error){status.textContent=error.message;}finally{busy=false;save.disabled=false;}
 });
 load().catch(()=>{});
})();