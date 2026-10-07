(async()=>{
  const node=document.getElementById('wallet-checkout-data');
  if(!node)return;
  const data=JSON.parse(node.textContent),button=document.getElementById('wallet-pay'),error=document.getElementById('wallet-payment-error');
  const load=url=>new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=url;script.onload=resolve;script.onerror=reject;document.head.appendChild(script);});
  try {
    if(['stripe','apple_pay','google_pay'].includes(data.provider)) {
      await load('https://js.stripe.com/v3/');
      const stripe=Stripe(data.publishable_key),elements=stripe.elements({clientSecret:data.client_secret});
      if(data.provider==='stripe') {
        const payment=elements.create('payment',{wallets:{applePay:data.apple_pay?'auto':'never',googlePay:data.google_pay?'auto':'never'}});
        payment.mount('#wallet-payment');
        button.onclick=async()=>{button.disabled=true;const result=await stripe.confirmPayment({elements,confirmParams:{return_url:data.return_url}});if(result.error){error.textContent=result.error.message;button.disabled=false;}};
      } else {
        button.hidden=true;
        const express=elements.create('expressCheckout',{paymentMethods:{applePay:data.provider==='apple_pay'?'always':'never',googlePay:data.provider==='google_pay'?'always':'never',link:'never',paypal:'never',amazonPay:'never',klarna:'never'}});
        express.mount('#wallet-payment');
        express.on('ready',event=>{if(!event.availablePaymentMethods?.[data.provider==='apple_pay'?'applePay':'googlePay'])error.textContent='This payment option is unavailable on this device. Choose another enabled method.';});
        express.on('confirm',async()=>{const result=await stripe.confirmPayment({elements,confirmParams:{return_url:data.return_url}});if(result.error)error.textContent=result.error.message;});
      }
    } else if(data.provider==='paytm') {
      if(!['https://securegw.paytm.in','https://securegw-stage.paytm.in'].includes(data.base)||!/^[A-Za-z0-9]+$/.test(data.mid))throw new Error('Invalid checkout configuration');
      await load(data.base+'/merchantpgpui/checkoutjs/merchants/'+encodeURIComponent(data.mid)+'.js');
      button.onclick=async()=>{try{await window.Paytm.CheckoutJS.init({root:'',flow:'DEFAULT',data:{orderId:data.id,token:data.token,tokenType:'TXN_TOKEN',amount:data.amount},handler:{notifyMerchant:()=>{}}});window.Paytm.CheckoutJS.invoke();}catch(e){error.textContent='Payment checkout unavailable. Please try again.';}};
    }
  } catch(e){if(error)error.textContent='Secure payment checkout could not load. Please try again.';}
})();
