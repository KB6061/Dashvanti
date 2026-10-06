from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [path('',TemplateView.as_view(template_name='home.html')),path('customer/',include('customer_app.urls')),path('restaurant/',include('restaurant_app.urls')),path('driver/',include('driver_app.urls')),path('admin/',include('admin_app.urls'))]
