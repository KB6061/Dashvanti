(() => {
 const portal=location.pathname.split('/')[1],prefix=portal==='reviews'?'/reviews/actions/':`/${portal}/experience/`;
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-review-action]');if(!button)return;event.preventDefault();
  const card=button.closest('[data-review-id]'),action=button.dataset.reviewAction;
  const report=card.querySelector('[data-review-report]');if(action==='report'&&report.hidden){report.hidden=false;report.querySelector('input').focus();return;}
  const reason=action==='report'?report.querySelector('input').value:'';button.disabled=true;
  try{const response=await fetch(prefix+`reviews/${card.dataset.reviewId}`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value||''},body:JSON.stringify({action,reason})});const data=await response.json();if(!response.ok)throw Error(data.error||data.detail||'Could not save');card.querySelector('[data-review-status]').textContent=data.message;}
  catch(error){const status=card.querySelector('[data-review-status]');status.textContent=error.message;status.classList.add('account-error');}finally{button.disabled=false;}
 });
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-favorite-kind]');if(!button)return;event.preventDefault();const enabled=button.getAttribute('aria-pressed')!=='true';button.disabled=true;
  try{const response=await fetch(prefix+'favorites',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value||''},body:JSON.stringify({kind:button.dataset.favoriteKind,target_id:Number(button.dataset.favoriteId),enabled})});if(!response.ok)throw Error();button.setAttribute('aria-pressed',String(enabled));button.textContent=enabled?'♥ Unfavorite':'♡ Favorite';}catch(_){button.textContent='Could not save. Retry';}finally{button.disabled=false;}
 });
})();
