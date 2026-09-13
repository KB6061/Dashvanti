(() => {
 const popup=document.querySelector('.store-info-popup');
 if(!popup)return;
 document.querySelector('[data-store-more]').onclick=()=>{
  popup.classList.remove('is-hidden');popup.showModal();
  document.dispatchEvent(new CustomEvent('dashvanti:map-select',{detail:{mapId:'store-info-map',id:'primary'}}));
 };
 popup.querySelector('.store-info-close').onclick=()=>popup.close();
 popup.querySelector('[data-store-close]').onclick=()=>popup.close();
 popup.addEventListener('close',()=>popup.classList.add('is-hidden'));
 document.querySelector('[data-store-pricing]').onclick=()=>{document.querySelector('[data-store-pricing] span').textContent='Taxes, delivery and service fees are calculated for your cart at checkout.';};
 document.querySelector('[data-deals-all]').onclick=event=>{const expanded=document.querySelector('.store-deals-rail').classList.toggle('expanded');event.currentTarget.textContent=expanded?'Show less':'See All';};
 document.querySelectorAll('[data-deals-arrow]').forEach(button=>button.onclick=()=>{const rail=document.querySelector('.store-deals-rail');rail.scrollBy({left:Number(button.dataset.dealsArrow)*rail.clientWidth,behavior:'smooth'});});
 document.querySelector('[data-menu-section]')?.classList.add('is-active');
 const navEntries=[...document.querySelectorAll('[data-menu-section]')];
 const trackSections=()=>{const top=(document.querySelector('.customer-topbar')?.getBoundingClientRect().height||90)+40;let active=navEntries[0];navEntries.forEach(button=>{const section=document.getElementById(button.dataset.menuSection);if(section&&!section.hidden&&section.getBoundingClientRect().top<=top)active=button;});navEntries.forEach(button=>{button.classList.toggle('is-active',button===active);button.setAttribute('aria-current',button===active?'true':'false');});};
 window.addEventListener('scroll',trackSections,{passive:true});
 const search=document.querySelector('[data-restaurant-menu-search]');
 search.addEventListener('input',()=>{
  const query=search.value.trim().toLocaleLowerCase();let matches=0;
  document.querySelectorAll('.restaurant-store-menu .customer-menu-card').forEach(card=>{
   const found=[card.dataset.name,card.dataset.description,card.dataset.category].join(' ').toLocaleLowerCase().includes(query);
   card.hidden=!found;if(found)matches++;
  });
  document.querySelectorAll('.menu-category,.store-featured').forEach(section=>{
   section.hidden=!section.querySelector('.customer-menu-card:not([hidden])');
  });
  document.querySelector('[data-menu-search-empty]').hidden=matches>0;
 });
 document.addEventListener('click',event=>{
  const categoryArrow=event.target.closest('[data-category-arrow]');
  if(categoryArrow){const rail=categoryArrow.closest('.menu-category').querySelector('.restaurant-category-rail');rail.scrollBy({left:Number(categoryArrow.dataset.categoryArrow)*rail.clientWidth,behavior:'smooth'});}
  const arrow=event.target.closest('[data-featured-arrow]');
  if(arrow){const rail=document.querySelector('.store-featured-rail');rail.scrollBy({left:Number(arrow.dataset.featuredArrow)*rail.clientWidth,behavior:'smooth'});}
  const section=event.target.closest('[data-menu-section]');
  if(section){document.querySelectorAll('[data-menu-section]').forEach(b=>b.classList.toggle('is-active',b===section));}
  if(section)document.getElementById(section.dataset.menuSection)?.scrollIntoView({behavior:'smooth',block:'start'});
 });
})();