from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('api/metrics/', views.metrics_api, name='metrics_api'),
]
