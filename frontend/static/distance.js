(() => {
 const valid=p=>p&&[p.latitude,p.longitude].every(v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v)))&&Math.abs(Number(p.latitude))<=90&&Math.abs(Number(p.longitude))<=180;
 window.dashvantiValidCoordinates=valid;
 const cache=new Map(),queue=[];let active=0;
 function run(){while(active<4&&queue.length){active++;const task=queue.shift();task().finally(()=>{active--;run();});}}
 window.dashvantiDistance=(origin,destination)=>{
  if(!valid(origin)||!valid(destination))return Promise.reject(new Error('Invalid coordinates'));
  const key=JSON.stringify([origin,destination]),cached=cache.get(key);
  if(cached&&cached.expires>Date.now())return cached.promise;
  const promise=new Promise((resolve,reject)=>{
   queue.push(async()=>{
    try{
     const csrf=document.querySelector('[name=csrfmiddlewaretoken]')?.value;
     const role=location.pathname.split('/')[1];
     const response=await fetch('/'+role+'/route-distance',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf||''},body:JSON.stringify({origin,destination})});
     if(!response.ok||response.redirected)throw new Error('Route unavailable');
     resolve(await response.json());
    }catch(error){cache.delete(key);reject(error);}
   });run();
  });
  if(cache.size>=500)cache.clear();
  cache.set(key,{promise,expires:Date.now()+120000});return promise;
 };
})();
