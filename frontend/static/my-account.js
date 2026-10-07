(() => {
 function initialize(){
 const account=document.querySelector('.my-account');if(!account)return;
 const status=account.querySelector('[data-account-status]');
 document.querySelectorAll('[data-account-confirm]').forEach(form=>form.addEventListener('submit',event=>{if(!confirm(form.dataset.accountConfirm))event.preventDefault();}));
 account.querySelectorAll('[data-copy-text]').forEach(button=>button.onclick=async()=>{try{await navigator.clipboard.writeText(button.dataset.copyText);status.textContent='Copied';}catch(_){status.textContent='Copy unavailable. Select the text and copy it.';}});
 account.querySelectorAll('[data-share-link]').forEach(button=>button.onclick=async()=>{try{if(navigator.share)await navigator.share({title:'Join Dashvanti',url:button.dataset.shareLink});else{await navigator.clipboard.writeText(button.dataset.shareLink);status.textContent='Link copied';}}catch(_){} });
 const deviceTimezone=Intl.DateTimeFormat().resolvedOptions().timeZone;
 const timezone=account.dataset.timezoneDetected==='true'?account.dataset.accountTimezone:deviceTimezone;
 if(account.dataset.timezoneDetected==='false'&&!account.hasAttribute('data-read-only')){const body=new FormData();body.set('csrfmiddlewaretoken',document.querySelector('[name=csrfmiddlewaretoken]')?.value||'');body.set('action','timezone_detect');body.set('timezone',deviceTimezone);void fetch(location.pathname,{method:'POST',body,credentials:'same-origin'}).catch(()=>{});}
 account.querySelectorAll('[data-account-date]').forEach(element=>{const raw=element.textContent.trim();if(!/^\d{4}-\d{2}-\d{2}T/.test(raw))return;const value=new Date(/[Zz]|[+-]\d{2}:\d{2}$/.test(raw)?raw:raw+'Z');if(!Number.isNaN(value.getTime()))element.textContent=value.toLocaleString(undefined,{timeZone:timezone,dateStyle:'medium',timeStyle:'short'});});
 account.querySelector('[data-use-device-timezone]')?.addEventListener('click',()=>{account.querySelector('[data-timezone-input]').value=Intl.DateTimeFormat().resolvedOptions().timeZone;});
 }
 initialize();window.addEventListener('dashvanti:account-panel',initialize);
})();

(() => {
 const shell=document.querySelector('.my-account');if(!shell)return;
 const nav=shell.querySelector('[data-account-nav]'),status=shell.querySelector('[data-account-status]');
 let current=shell.querySelector('[data-account-panel]').dataset.section,controller;
 const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
 const endpoint=section=>shell.hasAttribute('data-read-only')?`${location.pathname}?section=${encodeURIComponent(section)}`:`/customer/account/${section}`;
 const announce=(message,error=false)=>{status.textContent=message;status.classList.toggle('account-error',error);};
 const mount=()=>{
  const fitNav=()=>{nav.style.maxHeight=Math.max(180,innerHeight-nav.getBoundingClientRect().top-12)+'px';};fitNav();
  shell.querySelectorAll('[data-request-key]').forEach(input=>{if(!input.value)input.value=crypto.randomUUID();});
  const gateway=shell.querySelector('[name=gateway]'),add=shell.querySelector('[data-wallet-add]');if(add)add.disabled=!gateway?.options.length;
  shell.querySelectorAll('[data-state-dropdown]').forEach(async select=>{
   try{const response=await fetch(`/customer/experience/states/${select.dataset.country}`,{credentials:'same-origin'});if(!response.ok)throw Error();const data=await response.json();const blank=new Option('Choose state','');select.replaceChildren(blank,...data.states.map(value=>new Option(value,value,false,value===select.dataset.selected)));}catch(_){announce('State list could not load. Try again.',true);}
  });
  window.dispatchEvent(new CustomEvent('dashvanti:account-panel',{detail:{section:current}}));
 };
 let resizePending=false;const resizeNav=()=>{if(resizePending)return;resizePending=true;requestAnimationFrame(()=>{nav.style.maxHeight=Math.max(180,innerHeight-nav.getBoundingClientRect().top-12)+'px';resizePending=false;});};window.addEventListener('resize',resizeNav);window.addEventListener('scroll',resizeNav,{passive:true});
 async function load(section,options={}){
  controller?.abort();controller=new AbortController();const abort=controller;
  shell.querySelector('[data-account-panel]').setAttribute('aria-busy','true');
  try{
   const target=endpoint(section);
   const response=await fetch(target+(options.query?(target.includes('?')?'&':'?')+options.query:''),{credentials:'same-origin',headers:{'X-Account-Panel':'1','X-CSRFToken':csrf()},signal:abort.signal,...options.request});
   if(response.status===401){location.assign('/customer/login');return;}
   if(!response.headers.get('content-type')?.includes('application/json'))throw Error('Account panel could not load. Try again.');
   const data=await response.json();if(data.redirect){location.assign(data.redirect);return;}
   if(!data.html)throw Error(data.error||'Account panel could not load.');
   const fragment=document.createElement('template');fragment.innerHTML=data.html;const panel=fragment.content.querySelector('[data-account-panel]');if(!panel)throw Error('Invalid panel response');
   shell.querySelector('[data-account-panel]').replaceWith(panel);current=section;
   nav.querySelectorAll('a').forEach(link=>{if(link.getAttribute('href')?.endsWith('/'+section)||link.search===`?section=${section}`)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
   if(data.theme)shell.dataset.accountTheme=data.theme;
   if(data.avatar)window.dispatchEvent(new CustomEvent('dashvanti:identity-update',{detail:{avatar:data.avatar,name:data.name}}));
   announce(data.error||'',Boolean(data.error));mount();if(options.focus!==false)panel.focus({preventScroll:true});
  }catch(error){if(error.name!=='AbortError')announce(error.message||'Connection unavailable. Your changes have not been lost.',true);}
  finally{shell.querySelector('[data-account-panel]')?.removeAttribute('aria-busy');}
 }
 shell.addEventListener('click',event=>{
  const link=event.target.closest('a');if(link&&link.closest('[data-account-nav],.account-quick-actions')&&(/\/account\/[a-z-]+$/.test(link.pathname)||link.search.startsWith('?section='))){event.preventDefault();event.stopImmediatePropagation();const section=link.search?new URLSearchParams(link.search).get('section'):link.pathname.split('/').pop();load(section);}
  const tab=event.target.closest('[data-favorite-tab]');if(tab){shell.querySelectorAll('[data-favorite-tab]').forEach(button=>button.setAttribute('aria-selected',String(button===tab)));shell.querySelectorAll('[data-favorite-panel]').forEach(panel=>panel.hidden=panel.dataset.favoritePanel!==tab.dataset.favoriteTab);}
 },true);
 document.addEventListener('click',event=>{
  const link=event.target.closest('a');if(!link||shell.contains(link)||!/^\/customer\/account\/[a-z-]+$/.test(link.pathname)||['export','verify-login'].includes(link.pathname.split('/').pop()))return;
  event.preventDefault();event.stopImmediatePropagation();document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));load(link.pathname.split('/').pop());
 },true);
 shell.addEventListener('submit',event=>{
  const form=event.target;if(!form.closest('[data-account-panel]')||!form.matches('form[method=post]')||form.hasAttribute('action')||form.matches('[data-ticket-create],[data-ticket-filter]'))return;
  event.preventDefault();event.stopImmediatePropagation();if(!form.reportValidity())return;
  const body=new FormData(form);load(current,{request:{method:'POST',body},focus:false});
 },true);
 shell.addEventListener('change',event=>{
  if(event.target.matches('input[name=photo]')&&event.target.files[0]){const url=URL.createObjectURL(event.target.files[0]);shell.querySelectorAll('[data-account-avatar]').forEach(avatar=>{let img=avatar.querySelector('img');if(!img){img=document.createElement('img');img.alt='Selected profile photo';avatar.replaceChildren(img);}img.src=url;img.onload=()=>URL.revokeObjectURL(url);});}
 });
 window.addEventListener('dashvanti:account-reload',()=>load(current,{focus:false}));
 window.addEventListener('dashvanti:ticket-filter',event=>load('support',{query:event.detail,focus:false}));
 mount();
 const pending=shell.querySelector('[data-wallet-pending]');if(pending){let attempts=0;const timer=setInterval(async()=>{if(document.hidden||current!=='wallet')return;try{const response=await fetch(`/customer/experience/wallet/funding/${pending.dataset.walletPending}/verify`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf()},body:'{}'});const data=await response.json();if(response.ok&&data.status!=='pending'){clearInterval(timer);await load('wallet');announce(data.message);}else if(++attempts>=12){clearInterval(timer);announce(data.error||'Payment is still pending. Recheck from your wallet.');}}catch(_){if(++attempts>=12)clearInterval(timer);}},5000);}
})();
