(() => {
 if(!document.body.classList.contains('customer-portal'))return;
 window.dashvantiSignupLocation=async data=>{
  if(!navigator.geolocation)return;
  const position=await new Promise(resolve=>navigator.geolocation.getCurrentPosition(resolve,()=>resolve(null),{enableHighAccuracy:true,maximumAge:30000,timeout:8000}));
  if(position){data.set('latitude',position.coords.latitude);data.set('longitude',position.coords.longitude);}
 };
 document.addEventListener('submit',async event=>{
  const form=event.target;
  if(!form.matches('[data-auth-form="register"]')||form.dataset.locationPrepared==='true')return;
  event.preventDefault();
  if(form.dataset.locating==='true')return;
  form.dataset.locating='true';
  const button=event.submitter;const data=new FormData(form);
  if(button)button.disabled=true;
  try{
   await window.dashvantiSignupLocation(data);
   for(const name of ['latitude','longitude']){
    if(data.has(name)&&form.elements[name])form.elements[name].value=data.get(name);
   }
   form.dataset.locationPrepared='true';
  }finally{
   delete form.dataset.locating;if(button)button.disabled=false;
  }
  setTimeout(()=>{if(button)form.requestSubmit(button);else form.requestSubmit();},0);
 },true);
})();
