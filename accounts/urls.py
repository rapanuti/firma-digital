"""URLs de la app accounts."""

from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("perfil/", views.ProfileView.as_view(), name="profile"),
    path("perfil/editar/", views.ProfileUpdateView.as_view(), name="profile_edit"),
    path("perfil-firma/", views.signature_profile, name="signature_profile"),
    path("perfil-firma/editar/", views.signature_profile_edit, name="signature_profile_edit"),
    path("perfil-firma/firmas/agregar/", views.signature_image_add, name="signature_image_add"),
    path(
        "perfil-firma/firmas/<int:pk>/predeterminada/",
        views.signature_image_default,
        name="signature_image_default",
    ),
    path(
        "perfil-firma/firmas/<int:pk>/eliminar/",
        views.signature_image_delete,
        name="signature_image_delete",
    ),
    path("usuarios/", views.UserListView.as_view(), name="user_list"),
]
