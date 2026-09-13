(() => {
 document.addEventListener('keydown', event => {
  if(event.key==='Enter' && event.target.matches('[data-restaurant-url]'))location.assign(event.target.dataset.restaurantUrl);
 });
 document.addEventListener('click', event => {
  const card=event.target.closest('[data-restaurant-url]');
  if(card && !event.target.closest('a,button,input'))location.assign(card.dataset.restaurantUrl);
  const arrow = event.target.closest('[data-shelf-arrow], [data-photo-arrow]');
  if (arrow) {
   const photo = arrow.hasAttribute('data-photo-arrow');
   const root = arrow.closest(photo ? '.restaurant-showcase' : '[data-restaurant-shelf]');
   const rail = root.querySelector(photo ? '[data-restaurant-photos]' : '[data-shelf-rail]');
   const direction = Number(photo ? arrow.dataset.photoArrow : arrow.dataset.shelfArrow);
   const max = rail.scrollWidth - rail.clientWidth;
   let target = rail.scrollLeft + direction * rail.clientWidth;
   if (photo && target > max + 2) target = 0;
   if (photo && target < -2) target = max;
   rail.scrollTo({left: target, behavior: 'smooth'});
  }
  const all = event.target.closest('[data-shelf-all]');
  if (all) {
   const shelf = all.closest('[data-restaurant-shelf]');
   const expanded = shelf.classList.toggle('show-all');
   all.textContent = expanded ? 'Show Less' : 'See All';
   all.setAttribute('aria-expanded', String(expanded));
  }
 });
})();
(() => {
 const initialized=new WeakSet();
 const selector='[data-restaurant-photos]';
 function initialize(){document.querySelectorAll(selector).forEach(rail=>{if(!initialized.has(rail)){rail.scrollLeft=0;initialized.add(rail);}});}
 initialize();
 new MutationObserver(initialize).observe(document.body,{childList:true,subtree:true});
 setInterval(()=>{
  if(document.hidden || matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  document.querySelectorAll(selector).forEach(rail=>{
   const box=rail.getBoundingClientRect();
   if(box.width===0 || box.bottom<0 || box.top>innerHeight || rail.closest('.restaurant-showcase').matches(':hover,:focus-within'))return;
   const max=rail.scrollWidth-rail.clientWidth;
   if(max<2)return;
   const next=rail.scrollLeft+rail.clientWidth;
   rail.scrollTo({left:next>max+2?0:next,behavior:'smooth'});
  });
 },4000);
})();
