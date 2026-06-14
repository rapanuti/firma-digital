"""URLs raíz del proyecto firma_digital."""

from django.contrib import admin
from django.urls import include, path

from accounts.views import DashboardView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", DashboardView.as_view(), name="dashboard"),
]
