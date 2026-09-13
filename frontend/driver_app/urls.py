from django.urls import path
from common_app import views as common
from . import views

urlpatterns = [
    path('presence', views.presence),
    path('location/update',views.navigation_update,{'kind':'location'}),
    path('status/update',views.navigation_update,{'kind':'status'}),
    path('order/<int:order_id>/cancellation', common.cancellation),
    path('order/<int:order_id>/tracking', common.tracking),
    path('order-sound', common.order_sound),
    path('route-distance', common.route_distance),
    path('earnings/pdf', common.download_report),
    path('live-alerts', common.live_alerts),
    path('login',common.auth,{'role':'driver','action':'login'}),
    path('register',common.auth,{'role':'driver','action':'register'}),
    path('forgot',common.auth,{'role':'driver','action':'forgot'}),
    path('reset',common.auth,{'role':'driver','action':'reset'}),
    path('logout',common.logout,{'role':'driver'}),
    path('profile',common.profile),
    path('files',common.files),
    path('files/<int:file_id>',common.download),
    path('orders',views.orders),
    path('order/<int:order_id>',views.order),
    path('dashboard',views.dashboard),
    path('order/<int:order_id>/accept',views.accept),
    path('earnings',views.stats),
    path('support',common.support),
    path('notifications',common.notifications),
    path('order/<int:order_id>/chat',common.chat),
]
