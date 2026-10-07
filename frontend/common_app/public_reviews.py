import re
from django.shortcuts import render
from django.http import HttpResponse
from common_app.api import call, APIError
from common_app.account_experience import proxy


def reviews(request):
    try:
        page=max(1,int(request.GET.get('page','1')))
        restaurant=request.GET.get('restaurant_id')
        params={'page':page,'size':20}
        if restaurant:params['restaurant_id']=int(restaurant)
        data=call(request,'GET','/account-experience/reviews',params=params)
        for review in data['items']:
            if review.get('avatar'):review['avatar']=review['avatar'].replace('/api/account-experience/','/reviews/media/').replace('/customer/experience/','/reviews/media/')
            review['photo_urls']=['/reviews/media/review-photo/'+str(file_id) for file_id in review.get('photos',[])]
        return render(request,'account_components/public_review_page.html',{'reviews':data['items'],'page':page,'previous':page-1,'next':page+1 if page*20<data['total'] else None,'restaurant_id':restaurant or '', 'title':'Customer reviews'})
    except (APIError,ValueError):return render(request,'account_components/public_review_page.html',{'account_error':'Reviews could not load. Please try again.'},status=503)


def review_media(request,endpoint):
    if not re.fullmatch(r'(avatar|review-photo)/\d+',endpoint):return HttpResponse(status=404)
    return proxy(request,endpoint)


def review_action(request,review_id):
    return proxy(request,'reviews/'+str(review_id))
