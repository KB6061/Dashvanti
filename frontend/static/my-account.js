(() => {
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
})();
