import re
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from common_app.api import call, APIError, api_client


@require_GET
def checkout(request, funding_id):
    if request.session.get('role')!='customer':return redirect('/customer/login')
    try:
        data=call(request,'GET','/account-experience/wallet/checkout/'+funding_id)
        return render(request,'customer_app/wallet_checkout.html',{'checkout':data,'title':'Secure wallet checkout'})
    except APIError as exc:return render(request,'customer_app/wallet_checkout.html',{'account_error':str(exc)},status=exc.status)


@csrf_exempt
@require_POST
def webhook(request, provider):
    if provider not in {'stripe','paypal','razorpay','phonepe','paytm','square','authorize_net'}:return HttpResponse(status=404)
    if len(request.body)>65536:return HttpResponse(status=413)
    names=('stripe-signature','x-razorpay-signature','authorization','paypal-auth-algo','paypal-cert-url','paypal-transmission-id','paypal-transmission-sig','paypal-transmission-time','x-square-hmacsha256-signature','x-anet-signature')
    headers={key:request.headers[key] for key in names if key in request.headers}
    headers['Content-Type']=request.headers.get('Content-Type','application/json')
    try:
        response=api_client().post(settings.API_URL+'/account-experience/wallet/callback/'+provider,content=request.body,headers=headers)
        if provider=='paytm' and response.is_success:return redirect('/customer/account/wallet')
        return HttpResponse(response.content,status=response.status_code,content_type='application/json')
    except Exception:return JsonResponse({'error':'Payment callback unavailable'},status=503)
