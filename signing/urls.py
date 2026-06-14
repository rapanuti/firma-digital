"""URLs de la app signing."""

from django.urls import path

from . import views

app_name = "signing"

urlpatterns = [
    path("documentos/<int:doc_id>/firmar/", views.sign_view, name="sign"),
    path("firmas/<int:pk>/", views.result_view, name="result"),
    path("firmas/<int:pk>/descargar/", views.download_signed, name="download_signed"),
]
