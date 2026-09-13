(() => {
 let savedChildren=null,loading=false;
 function prepare(){
  document.querySelectorAll('[data-local-order-date]').forEach(el=>{let raw=el.getAttribute('datetime');if(!raw)return;if(!/Z$|[+-]\d\d:\d\d$/.test(raw))raw+='Z';const date=new Date(raw);if(!Number.isNaN(date.valueOf()))el.textContent=date.toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',hour12:true});});
 }
 prepare();
 document.addEventListener('click',async event=>{
  const link=event.target.closest('a[href="/customer/orders"]');
  if(link&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey){
   event.preventDefault();if(loading)return;loading=true;
   try{
    if(typeof setAccount==='function')setAccount(false);
    const response=await fetch(link.href,{credentials:'same-origin'});
    if(!response.ok||response.redirected)throw new Error();
    const page=new DOMParser().parseFromString(await response.text(),'text/html');
    const history=page.querySelector('#customer-order-history');if(!history)throw new Error();
    const main=document.querySelector('main');
    if(!savedChildren){savedChildren=[...main.children].map(el=>({el,hidden:el.hidden}));savedChildren.forEach(({el})=>el.hidden=true);}
    main.querySelector(':scope > #customer-order-history:not([hidden])')?.remove();
    main.append(history);history.querySelector('[data-orders-back]').hidden=false;prepare();history.focus();window.scrollTo({top:0,behavior:'smooth'});
   }catch(_){location.assign(link.href);}finally{loading=false;}
  }
  if(event.target.closest('[data-orders-back]')){
   document.querySelector('main > #customer-order-history:not([hidden])')?.remove();
   savedChildren?.forEach(({el,hidden})=>el.hidden=hidden);savedChildren=null;
  }
  const filter=event.target.closest('[data-order-filter]');
  if(filter){
   const root=filter.closest('#customer-order-history');let count=0;
   root.querySelectorAll('[data-order-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b===filter)));
   root.querySelectorAll('[data-history-status]').forEach(row=>{
    const status=row.dataset.historyStatus.toUpperCase(),cancelled=['CANCELLED','CANCELED','REJECTED'].includes(status),completed=['DELIVERED','COMPLETED','COLLECTED'].includes(status);
    row.hidden=!(filter.dataset.orderFilter==='all'||(filter.dataset.orderFilter==='completed'&&completed)||(filter.dataset.orderFilter==='cancelled'&&cancelled)||(filter.dataset.orderFilter==='active'&&!cancelled&&!completed));if(!row.hidden)count++;
   });root.querySelector('[data-orders-filter-empty]').hidden=count>0;
  }
 });
})();
