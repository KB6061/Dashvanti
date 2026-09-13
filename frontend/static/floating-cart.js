(() => {
 const cart=document.querySelector('[data-floating-cart]');
 if(!cart)return;
 const toggle=cart.querySelector('[data-cart-toggle]');
 function setCollapsed(collapsed) {
  cart.classList.toggle('cart-minimized',collapsed);
  toggle.setAttribute('aria-expanded',String(!collapsed));
  toggle.querySelector('span').textContent=collapsed?'+':'−';
  toggle.setAttribute('aria-label',collapsed?'Expand cart':'Minimize cart');
 }
 let saved=false;
 try{saved=sessionStorage.getItem('dashvanti-cart-minimized')==='true';}catch(_){}
 setCollapsed(saved);
 toggle.onclick=()=>{
  const collapsed=!cart.classList.contains('cart-minimized');
  setCollapsed(collapsed);
  try{sessionStorage.setItem('dashvanti-cart-minimized',String(collapsed));}catch(_){}
 };
 const sounds=document.querySelector('[data-order-alerts]');
 function position(){
  const offset=sounds && sounds.getBoundingClientRect().height>0?Math.max(18,window.innerHeight-sounds.getBoundingClientRect().top+12):18;
  cart.style.setProperty('--cart-bottom',offset+'px');
 }
 if(sounds)new ResizeObserver(position).observe(sounds);
 window.addEventListener('resize',position);
 position();
})();