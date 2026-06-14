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
    path("usuarios/", views.UserListView.as_view(), name="user_list"),
]
