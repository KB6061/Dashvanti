from common_app import views as common
from django.urls import path
from . import views

urlpatterns = [
    path('order/<int:order_id>/cancellation', views.cancellation),
    path('route-distance', common.route_distance),
    path('funds', views.funds),
    path('funds/<str:section>', views.funds),
    path('login', views.login),
    path('dashboard', views.dashboard),
    path('content', views.content),
    path('operations', views.operations),
    path('users', views.users),
    path('restaurants', views.restaurants),
    path('drivers', views.drivers),
    path('orders', views.orders),
    path('order/<int:order_id>', views.order_detail),
    path('logout', views.logout),
]
