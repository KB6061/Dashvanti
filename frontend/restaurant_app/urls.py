from django.urls import path
from common_app import views as common
from . import views

urlpatterns = [
    path('order/<int:order_id>/cancellation', common.cancellation),
    path('order-sound', common.order_sound),
    path('route-distance', common.route_distance),
    path('order/<int:order_id>/bill', common.download_report),
    path('live-alerts', common.live_alerts),
    path('login',common.auth,{'role':'restaurant','action':'login'}),
    path('register',common.auth,{'role':'restaurant','action':'register'}),
    path('forgot',common.auth,{'role':'restaurant','action':'forgot'}),
    path('reset',common.auth,{'role':'restaurant','action':'reset'}),
    path('logout',common.logout,{'role':'restaurant'}),
    path('profile',views.profile),
    path('files',common.files),
    path('files/<int:file_id>',common.download),
    path('orders',views.orders),
    path('order/<int:order_id>',views.order),
    path('dashboard',views.dashboard),
    path('content',views.content),
    path('menu',views.menu),
    path('menu/<int:item_id>',views.menu),
    path('stats',views.stats),
    path('support',common.support),
    path('notifications',common.notifications),
    path('order/<int:order_id>/chat',common.chat),
]
