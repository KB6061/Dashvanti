(() => {
 function openOrder(event){
  if(event.target.closest('a,button,input,select,textarea,summary'))return;
  const row=event.target.closest('[data-order-url]');
  if(row){event.preventDefault();location.assign(row.dataset.orderUrl);}
 }
 document.addEventListener('dblclick',openOrder);
 document.addEventListener('keydown',event=>{if(event.key==='Enter')openOrder(event);});

 document.querySelectorAll('[data-order-table]').forEach(table=>{
  const rows=[...table.tBodies[0].rows];if(rows.length<=25)return;
  let page=0;const controls=document.createElement('div');controls.className='order-table-pages';
  const previous=document.createElement('button'),next=document.createElement('button'),status=document.createElement('span');
  previous.type=next.type='button';previous.textContent='Previous';next.textContent='Next';status.setAttribute('aria-live','polite');
  function render(){rows.forEach((row,i)=>row.hidden=i<page*25||i>=(page+1)*25);status.textContent=(page*25+1)+'–'+Math.min((page+1)*25,rows.length)+' of '+rows.length;previous.disabled=page===0;next.disabled=(page+1)*25>=rows.length;}
  previous.onclick=()=>{page--;render();};next.onclick=()=>{page++;render();};controls.append(previous,status,next);table.parentElement.after(controls);render();
 });
 document.querySelectorAll('[data-order-date]').forEach(el=>{let raw=el.dateTime;if(!/Z$|[+-]\d\d:\d\d$/.test(raw))raw+='Z';const date=new Date(raw);if(!isNaN(date.valueOf()))el.textContent=date.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short',hour12:true});});
})();
