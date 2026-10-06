(() => {
 if(!document.querySelector('.admin-workspace'))return;
 const seen=new Set();let busy=false;
 const banner=document.createElement('aside');banner.hidden=true;banner.className='partner-sos-alert';banner.style.cssText='position:fixed;bottom:20px;right:20px;z-index:1600;max-width:min(380px,90vw);padding:18px;background:#a82b2b;color:white;border-radius:12px;box-shadow:0 8px 30px #0003';document.body.append(banner);
 async function poll(){
  if(busy||document.hidden)return;busy=true;
  try{const res=await fetch('/admin/driver-partners/reports/incidents?download=1',{credentials:'same-origin'});if(!res.ok)return;const data=await res.json();const item=data.items.find(r=>r.status==='OPEN'&&!seen.has(r.id));if(!item)return;seen.add(item.id);banner.replaceChildren();
   const title=document.createElement('strong');title.textContent='Driver SOS #'+item.id+' · '+item.kind;
   const text=document.createElement('p');text.textContent=item.description;
   const link=document.createElement('a');link.href='/admin/driver-partners/reports/incidents';link.textContent='Open incident';link.style.color='white';
   const close=document.createElement('button');close.type='button';close.textContent='Dismiss';close.onclick=()=>banner.hidden=true;
   banner.append(title,text,link,close);banner.hidden=false;
  }catch(e){}finally{busy=false;}
 }
 poll();setInterval(poll,5000);document.addEventListener('visibilitychange',poll);
 const bank=document.querySelector('[data-driver-bank]');if(bank)bank.onclick=async()=>{const r=await fetch(bank.dataset.driverBank,{credentials:'same-origin',cache:'no-store'});if(r.ok){const data=await r.json();document.querySelector('[data-driver-bank-details]').textContent=Object.entries(data).map(([k,v])=>k+': '+v).join('\n');}};
})();
