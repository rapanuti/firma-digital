"""URLs públicas de verificación."""

from django.urls import path

from . import views

app_name = "verification"

urlpatterns = [
    path("", views.index, name="index"),
    path("archivo/", views.verify_by_file, name="verify_by_file"),
    path("<str:code>/", views.detail, name="detail"),
]
