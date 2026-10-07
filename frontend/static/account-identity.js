(() => {
 const portal=location.pathname.split('/')[1];if(!['customer','restaurant','driver','admin'].includes(portal))return;
 const selectors='.sidebar-avatar,.profile-avatar,[data-account-avatar],[data-user-avatar-container]';
 const localURL=url=>url.startsWith('/api/account-experience/')?`/${portal}/experience/`+url.slice('/api/account-experience/'.length):url;
 const show=data=>{
  if(data.avatar){document.querySelectorAll(selectors).forEach(container=>{let image=container.querySelector('img');if(!image){image=document.createElement('img');container.replaceChildren(image);}image.src=localURL(data.avatar);image.alt=data.name||'Profile photo';image.className='account-user-avatar';});}
  if(data.name){document.querySelectorAll('[data-account-name],.sidebar-profile strong,.profile-row > a strong').forEach(node=>node.textContent=data.name);}
  if(data.verified){document.querySelectorAll('.sidebar-profile,.profile-row > a').forEach(profile=>{if(profile.querySelector('.account-verified,.google-verified'))return;const badge=document.createElement('small');badge.className='account-verified';badge.textContent='✓ Verified';profile.querySelector('strong')?.after(badge);});}
 };
 window.addEventListener('dashvanti:identity-update',event=>show(event.detail));
 document.addEventListener('change',event=>{
   const input=event.target;if(input.name!=='profile_photo'||!input.files?.[0])return;
   const url=URL.createObjectURL(input.files[0]);show({avatar:url});
   window.addEventListener('pagehide',()=>URL.revokeObjectURL(url),{once:true});
 });
 if(document.querySelector(selectors))fetch(`/${portal}/experience/identity`,{credentials:'same-origin',cache:'no-store'}).then(response=>response.ok?response.json():null).then(data=>{if(data){show(data);if(data.location_needed&&navigator.geolocation)navigator.geolocation.getCurrentPosition(position=>{fetch(`/${portal}/experience/location`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value||''},body:JSON.stringify({latitude:position.coords.latitude,longitude:position.coords.longitude,language:navigator.language,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone})}).then(response=>{if(response.ok)window.dispatchEvent(new Event('dashvanti:location-changed'));}).catch(()=>{});},()=>{},{timeout:8000,maximumAge:60000});}}).catch(()=>{});
})();
