"""Formularios de la app accounts."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import SignatureProfile, User

# Clases Tailwind reutilizables para inputs (estilo sobrio y profesional).
INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
    "focus:border-brand-600 focus:ring-1 focus:ring-brand-600 focus:outline-none"
)


class StyledAuthenticationForm(AuthenticationForm):
    """Formulario de login con estilos Tailwind aplicados a los widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": INPUT_CLASSES})


class ProfileForm(forms.ModelForm):
    """Edición de datos básicos del propio usuario."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": INPUT_CLASSES}),
            "last_name": forms.TextInput(attrs={"class": INPUT_CLASSES}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASSES}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"]
        existe = (
            User.objects.exclude(pk=self.instance.pk)
            .filter(email__iexact=email)
            .exists()
        )
        if existe:
            raise forms.ValidationError("Ya existe un usuario con este correo.")
        return email


class SignatureProfileForm(forms.ModelForm):
    """Configuración del perfil de firma del usuario."""

    class Meta:
        model = SignatureProfile
        fields = [
            "full_name",
            "id_document",
            "email",
            "signature_image",
            "title",
            "is_active",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": INPUT_CLASSES}),
            "id_document": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "V-12345678"}
            ),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASSES}),
            "signature_image": forms.ClearableFileInput(
                attrs={"class": "block w-full text-sm", "accept": "image/png,image/jpeg"}
            ),
            "title": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Cargo (opcional)"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300"}
            ),
        }
