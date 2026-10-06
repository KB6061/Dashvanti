from . import driver_partners
from common_app.road_controls import road_controls
from common_app.views import navigation_state
from common_app import views as common
from django.urls import path
from . import views

from . import payments

urlpatterns = [
    path('driver-partners/manager-login', driver_partners.manager_login),
    path('driver-partners/manager-logout', driver_partners.manager_logout),
    path('driver-partners/reports/<str:kind>', driver_partners.reports),
    path('driver-partners/documents/<int:document_id>', driver_partners.document),
    path('driver-partners/<int:driver_id>/bank', driver_partners.bank),
    path('driver-partners/<int:driver_id>', driver_partners.detail),
    path('driver-partners', driver_partners.listing),
    path('road-controls', road_controls),
    path('payments/logs', payments.logs),
    path('payments/<int:transaction_id>', payments.transaction),
    path('payments', payments.payments),
    path('navigation-state', navigation_state),
    path('order/<int:order_id>/cancellation', views.cancellation),
    path('route-distance', common.route_distance),
    path('funds', views.funds),
    path('funds/<str:section>', views.funds),
    path('login', views.login),
    path('dashboard', views.dashboard),
    path('chat-feed', views.chat_feed),
    path('content', views.content),
    path('operations', views.operations),
    path('users', views.users),
    path('restaurants', views.restaurants),
    path('drivers', views.drivers),
    path('orders', views.orders),
    path('order/<int:order_id>', views.order_detail),
    path('logout', views.logout),
]
