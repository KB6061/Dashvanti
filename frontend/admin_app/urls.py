from . import driver_partners
from common_app.road_controls import road_controls
from common_app.views import navigation_state
from common_app import views as common
from django.urls import path
from . import views, account_management

from . import payments, delivery_fees

from customer_app.account_views import admin_account

urlpatterns = [
    path('profile', common.profile),
    path('wallet-refunds', account_management.wallet_refunds),
    path('account-login', account_management.account_login),
    path('audit-center', account_management.audit_center),
    path('support-center', account_management.support_center),
    path('gateway-controls', account_management.gateway_controls),
    path('review-moderation', account_management.review_moderation),
    path('account-verification', account_management.account_verification),
    path('experience/<path:endpoint>', account_management.experience_proxy),
    path('customer/<int:customer_id>/account', admin_account),
    path('delivery-fees', delivery_fees.manage),
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
