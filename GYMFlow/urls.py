"""
URL configuration for GYMFlow project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.root, name="root"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("faq/", views.faq, name="faq"),

    # Módulo de usuarios
    path("users/", include("apps.users.urls")),

    # Módulo de notificaciones
    path("notifications/", include("apps.notifications.urls")),

    # Módulo de asistencia
    path("attendance/", include("apps.attendance.urls")),

    # Módulo de pagos
    path("payments/", include("apps.payments.urls")),

    # Módulo de clases
    path("classes/", include("apps.classes.urls")),

    # Para el desarrollo
    path("__reload__/", include("django_browser_reload.urls")),
]
