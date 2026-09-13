(() => {
 let dialog,form,quote,url,busy=false,sequence=0;
 function create(){
  dialog=document.createElement('dialog');dialog.className='cancellation-dialog';
  dialog.innerHTML='<h2>Review cancellation</h2><p data-message role="status"></p><dl><dt>Cancellation charge</dt><dd data-charge></dd><dt>New refund request</dt><dd data-refund></dd><dt>Previously refunded or pending</dt><dd data-previous></dd></dl><p>Refunds go to the original payment method. A refund remains pending until the payment provider confirms processing.</p><form><label>Reason<textarea name="reason" minlength="3" maxlength="500" required rows="3"></textarea></label><button type="submit">Confirm cancellation</button><button type="button" data-close>Keep order</button></form><a data-support>Contact support</a>';
  document.body.append(dialog);form=dialog.querySelector('form');
  dialog.querySelector('[data-close]').onclick=()=>{if(!busy)dialog.close();};
  dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  dialog.addEventListener('close',()=>sequence++);
  form.onsubmit=async event=>{
   event.preventDefault();if(busy||!quote)return;
   busy=true;const button=form.querySelector('[type=submit]');button.disabled=true;
   try{
    const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]')?.value||''},body:JSON.stringify({reason:form.elements.reason.value.trim(),expected_status:quote.status,expected_refund:quote.refund,expected_charge:quote.charge}),signal:AbortSignal.timeout(20000)});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'Unable to cancel');
    dialog.querySelector('[data-message]').textContent=data.action==='release'?'Delivery released. We are finding another driver.':'Order cancelled. Refund status: '+data.refund_status;
    form.hidden=true;
    const done=document.createElement('button');done.type='button';done.textContent='Continue';
    done.onclick=()=>{if(data.action==='release')location.assign('/driver/dashboard');else location.reload();};
    dialog.append(done);
   }catch(error){dialog.querySelector('[data-message]').textContent=error.message+' Close this window and reopen to review current amounts.';}
   finally{busy=false;button.disabled=false;}
  };
 }
 document.addEventListener('click',async event=>{
  const trigger=event.target.closest('[data-cancel-order]');if(!trigger||busy)return;
  if(dialog)dialog.remove();create();url=trigger.dataset.cancelOrder;quote=null;const version=++sequence;
  dialog.querySelector('[data-message]').textContent='Checking order and refund…';
  dialog.querySelector('[data-support]').href='/'+url.split('/')[1]+'/support';
  form.querySelector('[type=submit]').disabled=true;dialog.showModal();
  try{
   const response=await fetch(url,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000)});
   const data=await response.json();if(version!==sequence)return;if(!response.ok)throw new Error(data.detail||'Unable to calculate refund');
   quote=data;
   dialog.querySelector('[data-charge]').textContent='$'+Number(data.charge).toFixed(2);
   dialog.querySelector('[data-refund]').textContent='$'+Number(data.refund).toFixed(2);
   dialog.querySelector('[data-previous]').textContent='$'+Number(data.previous_refunds).toFixed(2);
   dialog.querySelector('[data-message]').textContent=data.action==='release'?'Release your assignment. The customer order will stay active.':'Please review these amounts before confirming.';
   form.querySelector('[type=submit]').disabled=false;
  }catch(error){if(version===sequence)dialog.querySelector('[data-message]').textContent=error.message;}
 });
})();