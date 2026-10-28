"""Vistas de la app accounts: login, dashboard, perfil y listado (admin)."""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView, UpdateView

from .forms import (
    ProfileForm,
    SignatureImageForm,
    SignatureProfileForm,
    StyledAuthenticationForm,
)
from .models import SignatureImage, SignatureProfile, User
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
    images = profile.images.all() if profile else []
    return render(
        request,
        "accounts/signature_profile.html",
        {"profile": profile, "images": images, "image_form": SignatureImageForm()},
    )


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
        form.save_signature_image(obj)
        messages.success(request, "Perfil de firma guardado correctamente.")
        return redirect("accounts:signature_profile")
    return render(request, "accounts/signature_profile_edit.html", {"form": form})


def _own_image_or_404(request, pk):
    return get_object_or_404(SignatureImage, pk=pk, profile__user=request.user)


@login_required
@require_POST
def signature_image_add(request):
    """Agrega una imagen de firma al perfil del usuario."""
    profile = SignatureProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.warning(request, "Primero configura tu perfil de firma.")
        return redirect("accounts:signature_profile_edit")

    form = SignatureImageForm(request.POST, request.FILES)
    if form.is_valid():
        img = form.save(commit=False)
        img.profile = profile
        img.save()
        if img.is_default or profile.images.count() == 1:
            img.make_default()
        messages.success(request, f"Firma «{img.name}» agregada.")
        return redirect("accounts:signature_profile")

    return render(
        request,
        "accounts/signature_profile.html",
        {"profile": profile, "images": profile.images.all(), "image_form": form},
    )


@login_required
@require_POST
def signature_image_default(request, pk):
    """Marca una imagen de firma como la predeterminada."""
    img = _own_image_or_404(request, pk)
    img.make_default()
    messages.success(request, f"«{img.name}» es ahora tu firma predeterminada.")
    return redirect("accounts:signature_profile")


@login_required
@require_POST
def signature_image_delete(request, pk):
    """Elimina una imagen de firma (las firmas ya emitidas no se ven afectadas)."""
    img = _own_image_or_404(request, pk)
    profile = img.profile
    if profile.images.count() == 1:
        messages.error(request, "No puedes eliminar tu única firma.")
        return redirect("accounts:signature_profile")

    was_default = img.is_default
    name = img.name
    img.image.delete(save=False)
    img.delete()
    if was_default:
        profile.default_image.make_default()
    messages.success(request, f"Firma «{name}» eliminada.")
    return redirect("accounts:signature_profile")
