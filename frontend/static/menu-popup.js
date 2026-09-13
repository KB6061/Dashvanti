(() => {
 let popup, form, currentCard, busy=false, sequence=0;
 function create() {
  popup=document.createElement('dialog');popup.className='menu-detail-popup';
  popup.setAttribute('aria-labelledby','menu-popup-title');
  popup.innerHTML='<button type="button" class="menu-popup-close" aria-label="Close menu details">&times;</button><h2 id="menu-popup-title"></h2><p data-menu-meta></p><img data-menu-photo alt=""><p data-menu-description></p><form><h3>Your preferences</h3><p>Optional requests, subject to restaurant availability. Preferences apply to all quantities of this item.</p><label>Spice preference<select name="spice"><option value="">No preference</option><option>Mild</option><option>Medium</option><option>Hot</option></select></label><label>Cutlery<select name="cutlery"><option value="">No preference</option><option>No cutlery</option><option>Please include cutlery</option></select></label><label>Special instructions<textarea name="instructions" maxlength="850" rows="3" placeholder="Tell the kitchen your preferences"></textarea></label><label>Quantity<input name="quantity" type="number" min="1" max="50" value="1" required></label><p data-menu-status role="status"></p><footer><button type="submit"></button></footer></form>';
  document.body.append(popup);form=popup.querySelector('form');
  popup.querySelector('.menu-popup-close').onclick=()=>popup.close();
  popup.addEventListener('close',()=>{sequence++;currentCard?.focus();});
  form.onsubmit=async event=>{
   event.preventDefault();event.stopPropagation();if(busy)return;
   busy=true;const button=form.querySelector('[type=submit]');button.disabled=true;
   const status=popup.querySelector('[data-menu-status]');
   const body=new FormData();
   body.set('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]').value);
   body.set('menu_item_id',currentCard.dataset.id);body.set('quantity',form.elements.quantity.value);
   body.set('special_instructions',[form.elements.spice.value?'Spice: '+form.elements.spice.value:'',form.elements.cutlery.value,form.elements.instructions.value.trim()].filter(Boolean).join('; '));
   try{
    if(!await window.dashvantiStoreAvailable('menu',currentCard.dataset.id))return;
    const response=await fetch('/customer/cart',{method:'POST',body,headers:{'X-Requested-With':'fetch'},credentials:'same-origin'});
    if(!response.ok||response.redirected)throw new Error('Unable to save. Please try again.');
    const data=await response.json();
    document.querySelectorAll('.customer-cart-link strong').forEach(el=>el.textContent=data.cart_count);
    status.textContent='Saved to your cart.';
    button.dataset.action='Update cart';button.textContent='Update cart';
    const page=await fetch(location.href,{credentials:'same-origin'});
    if(page.ok){
     const doc=new DOMParser().parseFromString(await page.text(),'text/html');
     const old=document.querySelector('.cart-panel'),fresh=doc.querySelector('.cart-panel');
     if(old&&fresh)old.replaceWith(fresh);
    }
   }catch(error){status.textContent=error.message;}finally{busy=false;button.disabled=false;}
  };
 }
 async function open(card) {
  if(busy)return;
  try{if(!await window.dashvantiStoreAvailable('menu',card.dataset.id))return;}catch(_){return;}
  if(!popup)create();else if(popup.open)popup.close();const serial=++sequence;currentCard=card;form.reset();
  popup.querySelector('h2').textContent=card.dataset.name;
  popup.querySelector('[data-menu-description]').textContent=card.dataset.description||'Freshly prepared to order.';
  popup.querySelector('[data-menu-meta]').textContent=[card.dataset.restaurant,card.dataset.category,card.dataset.veg,'$'+Number(card.dataset.price).toFixed(2)].filter(Boolean).join(' · ');
  const photo=popup.querySelector('[data-menu-photo]'),source=card.querySelector('img');
  photo.hidden=!source;if(source){photo.src=source.dataset.fullSrc||source.currentSrc||source.src;photo.alt=card.dataset.name;}
  const button=form.querySelector('[type=submit]');button.disabled=true;button.dataset.action='Add to cart';
  const updatePrice=()=>{button.textContent=button.dataset.action+' · $'+(Number(card.dataset.price)*Number(form.elements.quantity.value||1)).toFixed(2);};
  form.elements.quantity.oninput=updatePrice;updatePrice();
  const status=popup.querySelector('[data-menu-status]');status.textContent='Loading cart…';
  popup.showModal();
  try {
   const response=await fetch('/customer/cart',{credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});
   if(!response.ok||response.redirected)throw new Error('Unable to load your cart. Close and try again.');
   const data=await response.json();if(serial!==sequence)return;
   const item=data.items.find(item=>String(item.menu_item_id)===card.dataset.id);
   if(item){form.elements.quantity.value=item.quantity;form.elements.instructions.value=item.special_instructions||'';button.dataset.action='Update cart';button.textContent='Update cart';}
   status.textContent='';button.disabled=false;
  }catch(error){if(serial===sequence)status.textContent=error.message;}
 }
 document.addEventListener('click',event=>{
  const card=event.target.closest('[data-menu-popup]');if(!card)return;
  event.preventDefault();event.stopImmediatePropagation();open(card);
 },true);
 document.addEventListener('keydown',event=>{
  if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-menu-popup]')){
   event.preventDefault();open(event.target);
  }
 });
})();