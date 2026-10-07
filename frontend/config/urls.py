from common_app.public_reviews import reviews, review_media, review_action
from common_app.views import about_us
from django.urls import path, include
from django.views.generic import TemplateView
from common_app.sounds import arrival as arrival_sound
from common_app.views import gps_ticket
from common_app.live_views import order_statuses

urlpatterns = [path('about-us', about_us),path('',TemplateView.as_view(template_name='home.html')),path('customer/',include('customer_app.urls')),path('restaurant/',include('restaurant_app.urls')),path('driver/',include('driver_app.urls')),path('admin/',include('admin_app.urls'))]
urlpatterns.insert(0,path('sounds/arrival.mp3',arrival_sound))
urlpatterns.insert(0,path('<str:portal>/gps-ticket',gps_ticket))
urlpatterns.insert(0,path('<str:portal>/live-status',order_statuses))

urlpatterns += [path('reviews',reviews),path('reviews/media/<path:endpoint>',review_media),path('reviews/actions/reviews/<int:review_id>',review_action)]
