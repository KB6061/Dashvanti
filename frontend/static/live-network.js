(() => {
 window.dashvantiTimeoutSignal=milliseconds=>{
  if(typeof AbortSignal!=='undefined'&&typeof AbortSignal.timeout==='function')return AbortSignal.timeout(milliseconds);
  if(typeof AbortController==='undefined')return undefined;
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),milliseconds);
  controller.signal.addEventListener('abort',()=>clearTimeout(timer),{once:true});return controller.signal;
 };
})();
