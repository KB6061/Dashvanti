(() => {
 const driver=document.body.classList.contains('driver-portal');
 let avatar='arrow';try{if(driver&&localStorage.getItem('dashvanti-navigation-avatar')==='car')avatar='car';}catch(_){}
 if(!driver)avatar='car';
 window.dashvantiSetNavigationAvatar=kind=>{if(!driver||!['car','arrow'].includes(kind))return;avatar=kind;try{localStorage.setItem('dashvanti-navigation-avatar',kind);}catch(_){}window.dispatchEvent(new Event('dashvanti:avatar-change'));};
 const icons=new Map();
 window.dashvantiNavigationIcon=(heading=0,kind=avatar)=>{
  const angle=Number.isFinite(heading)?heading:0;
  if(kind==='arrow')return {path:'M 0,-18 L 12,12 L 0,6 L -12,12 Z',fillColor:'#1976e8',fillOpacity:1,strokeColor:'#fff',strokeWeight:3,scale:1.3,rotation:angle,anchor:new google.maps.Point(0,0)};
  if(!carImage.src.startsWith('data:'))return {url:carImage.src,scaledSize:new google.maps.Size(56,56),anchor:new google.maps.Point(28,28)};
  const rotation=Math.round(angle/5)*5%360;
  if(!icons.has(rotation)){
   const svg='<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="96" height="96" viewBox="0 0 96 96"><image x="14" y="14" width="68" height="68" transform="rotate('+rotation+' 48 48)" href="'+carImage.src+'"/></svg>';
   icons.set(rotation,{url:'data:image/svg+xml;charset=UTF-8,'+encodeURIComponent(svg),scaledSize:new google.maps.Size(72,72),anchor:new google.maps.Point(36,36)});
  }
  return icons.get(rotation);
 };

 window.dashvantiNavigationAvatar=()=>avatar;
 const carImage={src:'/static/navigation-car.png?v=1'};
 fetch(carImage.src,{cache:'force-cache'}).then(response=>{if(!response.ok)throw new Error('Car icon unavailable');return response.blob();}).then(blob=>{
  const reader=new FileReader();reader.onload=()=>{carImage.src=reader.result;icons.clear();window.dispatchEvent(new Event('dashvanti:avatar-change'));};reader.readAsDataURL(blob);
 }).catch(()=>{});
})();
