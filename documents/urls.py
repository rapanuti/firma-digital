"""URLs de la app documents."""

from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("", views.DocumentListView.as_view(), name="list"),
    path("subir/", views.DocumentCreateView.as_view(), name="upload"),
    path("<int:pk>/", views.DocumentDetailView.as_view(), name="detail"),
    path("<int:pk>/original/", views.download_original, name="download_original"),
]
