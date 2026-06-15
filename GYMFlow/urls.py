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

from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core_views.root, name="root"),
    path("dashboard/", core_views.dashboard, name="dashboard"),
    path("faq/", core_views.faq, name="faq"),
    path("dashboard/quick-search/", core_views.dashboard_quick_search, name="dashboard_quick_search"),

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

    # Módulo de reportes/métricas
    path("reports/", include("apps.reports.urls")),
]
