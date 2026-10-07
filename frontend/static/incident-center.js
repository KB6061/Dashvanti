(() => {
 const portal=location.pathname.split('/')[1],admin=portal==='admin';
 const prefix=`/${portal}/experience/`;let active=null,timer=null,filters=new URLSearchParams(),page=1;
 const csrf=()=>document.querySelector('[name=csrfmiddlewaretoken]')?.value||'';
 const node=(tag,text,attributes={})=>{const value=document.createElement(tag);if(text!=null)value.textContent=text;Object.entries(attributes).forEach(([key,item])=>value.setAttribute(key,item));return value;};
 const api=async(path,options={})=>{const response=await fetch(prefix+path,{credentials:'same-origin',cache:'no-store',headers:{'X-CSRFToken':csrf(),...(options.body instanceof FormData?{}:{'Content-Type':'application/json'})},...options});const data=await response.json();if(!response.ok)throw Error(data.error||data.detail||'Request failed');return data;};
 const announce=(message,error=false)=>{const target=document.querySelector('[data-account-status],[data-incident-status]');if(target){target.textContent=message;target.classList.toggle('account-error',error);}};
 const thread=()=>document.querySelector('[data-ticket-thread]');
 const label=(text,input)=>{const value=node('label',text);value.append(input);return value;};
 function renderMessages(data){
  const target=thread()?.querySelector('[data-thread-messages]');if(!target)return;
  const nearBottom=target.scrollHeight-target.scrollTop-target.clientHeight<60;
  target.replaceChildren(...data.messages.map(message=>{const article=node('article',null,{class:'account-message','data-internal':String(message.internal)});article.append(node('strong',`${message.user} · ${message.role}${message.internal?' · Internal note':''}`),node('time',new Date(message.created_at.endsWith('Z')?message.created_at:message.created_at+'Z').toLocaleString()),node('p',message.body));return article;}));
  const files=thread().querySelector('[data-thread-files]');files.replaceChildren(...data.attachments.map(file=>node('a',file.name,{href:prefix+`attachments/${file.id}`,download:file.name})));
  thread().querySelector('[data-thread-status]').textContent=`${data.status} · ${data.priority} · ${admin?data.assignee:data.assigned_to}`;
  if(nearBottom)target.scrollTop=target.scrollHeight;
 }
 async function open(id){
  clearInterval(timer);active=id;const data=await api(`tickets/${id}`),target=thread();if(!target)return;
  target.hidden=false;target.replaceChildren(node('h3',data.number),node('p',null,{'data-thread-status':''}),node('p',data.description),node('div',null,{'data-thread-messages':''}),node('div',null,{'data-thread-files':''}));
  if(data.merged_into){target.append(node('p','Merged into '+data.merged_into));renderMessages(data);return;}
  const form=node('form',null,{'data-ticket-reply':String(id)});form.append(label('Reply',node('textarea',null,{name:'body',required:'',maxlength:'10000'})));
  if(admin){const internal=node('input',null,{type:'checkbox',name:'internal'});form.append(label('Internal note',internal));}
  form.append(label('Attachments (optional)',node('input',null,{type:'file',name:'files',multiple:'',accept:'image/jpeg,image/png,image/webp,application/pdf'})),node('button','Send reply',{type:'submit'}));target.append(form);
  if(admin){
   const panel=node('details');panel.append(node('summary','Assignment, escalation and status'));
   const edit=node('form',null,{'data-ticket-manage':String(id)}),action=node('select',null,{name:'action'});
   [['assign','Assign / Reassign'],['escalate','Escalate'],['status','Change status'],['merge','Merge ticket']].forEach(([value,text])=>action.append(node('option',text,{value})));
   const assignee=node('select',null,{name:'assignee_id'});assignee.append(node('option','Choose assignee',{value:''}));(await api('admin/assignees')).forEach(user=>assignee.append(node('option',user.name,{value:user.id})));
   const statuses=node('select',null,{name:'status'});['Open','Assigned','In Progress','Waiting Customer','Escalated','Resolved','Closed'].forEach(value=>statuses.append(node('option',value,{value})));
   const priority=node('select',null,{name:'priority'});['Low','Medium','High','Critical','Emergency'].forEach(value=>priority.append(node('option',value,{value})));
   edit.append(label('Action',action),label('Assignee',assignee),label('Department',node('input',null,{name:'department',value:data.department||'Support',maxlength:'80'})),label('Status',statuses),label('Priority',priority),label('Merge into ticket ID',node('input',null,{name:'merge_into',type:'number',min:'1'})),node('button','Apply',{type:'submit'}));panel.append(edit);target.append(panel);
   const audit=node('details');audit.append(node('summary',`SLA: ${data.sla_due_at||'Not configured'} · Full ticket audit`));data.events.forEach(event=>audit.append(node('p',`${event.created_at} · ${event.actor} · ${event.action} · ${JSON.stringify(event.details)}`)));target.append(audit);
  }
  renderMessages(data);target.scrollIntoView({behavior:'smooth',block:'nearest'});
  timer=setInterval(async()=>{if(document.hidden||!thread()||thread().hidden)return;try{renderMessages(await api(`tickets/${active}`));}catch(_){clearInterval(timer);}},10000);
 }
 async function upload(id,files,internal=false){for(const file of files){const body=new FormData();body.append('file',file);body.append('internal',String(internal));await api(`tickets/${id}/attachments`,{method:'POST',body});}}
 async function list(){filters.set('page',page);if(document.querySelector('.my-account')){window.dispatchEvent(new CustomEvent('dashvanti:ticket-filter',{detail:filters.toString()}));return;}
  const response=await fetch(location.pathname+'?'+filters,{credentials:'same-origin',headers:{'X-Incident-Panel':'1'}});if(!response.ok)throw Error('Could not load tickets');const data=await response.json();document.querySelector('[data-incident-list]').innerHTML=data.html;window.dispatchEvent(new Event('dashvanti:incident-list'));}
 document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-ticket-open],[data-ticket-export],[data-ticket-page]');if(!button)return;event.preventDefault();
  try{if(button.dataset.ticketOpen)await open(button.dataset.ticketOpen);else if(button.hasAttribute('data-ticket-export')){const query=new URLSearchParams(filters);query.set('export','true');const response=await fetch(prefix+'tickets?'+query,{credentials:'same-origin'});if(!response.ok)throw Error('Export unavailable');const url=URL.createObjectURL(await response.blob());const a=node('a','',{href:url,download:'dashvanti-incidents.csv'});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}else{page=button.dataset.ticketPage==='previous'?Math.max(1,page-1):page+1;await list();}}
  catch(error){announce(error.message,true);}
 },true);
 document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('[data-ticket-create],[data-ticket-reply],[data-ticket-manage],[data-ticket-filter]'))return;event.preventDefault();event.stopImmediatePropagation();if(!form.reportValidity())return;
  const values=new FormData(form),button=form.querySelector('button[type=submit],button:not([type])');if(button)button.disabled=true;
  try{
   if(form.matches('[data-ticket-filter]')){filters=new URLSearchParams([...values].filter(([,value])=>value!==''));page=1;await list();return;}
   if(form.matches('[data-ticket-create]')){const payload={category:values.get('category'),subcategory:values.get('subcategory')||'',priority:values.get('priority')||'Medium',description:values.get('description'),order_id:values.get('order_id')?Number(values.get('order_id')):null};const data=await api('tickets',{method:'POST',body:JSON.stringify(payload)});await upload(data.id,[...form.querySelector('[name=attachments]')?.files||[]]);form.reset();await list();announce(`${data.number} created`);return;}
   if(form.matches('[data-ticket-reply]')){const id=form.dataset.ticketReply,internal=values.get('internal')==='on';await api(`tickets/${id}`,{method:'POST',body:JSON.stringify({action:internal?'note':'reply',body:values.get('body')})});await upload(id,[...form.querySelector('[name=files]').files],internal);await open(id);announce('Reply saved');return;}
   const action=values.get('action'),payload={action};if(action==='assign'){payload.assignee_id=Number(values.get('assignee_id'));payload.department=values.get('department');}if(action==='status')payload.status=values.get('status');if(['status','escalate'].includes(action))payload.priority=values.get('priority');if(action==='merge')payload.merge_into=Number(values.get('merge_into'));await api(`tickets/${form.dataset.ticketManage}`,{method:'POST',body:JSON.stringify(payload)});await open(form.dataset.ticketManage);announce('Ticket updated');
  }catch(error){announce(error.message,true);}finally{if(button)button.disabled=false;}
 },true);
 window.addEventListener('dashvanti:account-panel',()=>{active=null;clearInterval(timer);});
})();
