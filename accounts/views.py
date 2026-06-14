"""Vistas de la app accounts: login, dashboard, perfil y listado (admin)."""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, UpdateView

from .forms import ProfileForm, SignatureProfileForm, StyledAuthenticationForm
from .models import SignatureProfile, User
from .permissions import AdminRequiredMixin


class CustomLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"


class ProfileUpdateView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile_edit.html"
    success_url = reverse_lazy("accounts:profile")
    success_message = "Perfil actualizado correctamente."

    def get_object(self, queryset=None):
        # Siempre se edita el propio usuario autenticado.
        return self.request.user


class UserListView(AdminRequiredMixin, ListView):
    """Listado de usuarios, accesible solo para administradores."""

    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "usuarios"
    ordering = ["username"]


# --- Perfil de firma -----------------------------------------------------


@login_required
def signature_profile(request):
    """Muestra el perfil de firma del usuario (o invita a crearlo)."""
    profile = SignatureProfile.objects.filter(user=request.user).first()
    return render(request, "accounts/signature_profile.html", {"profile": profile})


@login_required
def signature_profile_edit(request):
    """Crea o actualiza el perfil de firma del usuario."""
    profile = SignatureProfile.objects.filter(user=request.user).first()
    form = SignatureProfileForm(
        request.POST or None, request.FILES or None, instance=profile
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Perfil de firma guardado correctamente.")
        return redirect("accounts:signature_profile")
    return render(request, "accounts/signature_profile_edit.html", {"form": form})
