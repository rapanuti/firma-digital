"""Formularios de la app accounts."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import SignatureImage, SignatureProfile, User
from .validators import validate_signature_image

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


IMAGE_INPUT_ATTRS = {"class": "block w-full text-sm", "accept": "image/png,image/jpeg"}


class SignatureProfileForm(forms.ModelForm):
    """Configuración del perfil de firma del usuario.

    Las imágenes de firma viven en ``SignatureImage``; aquí se permite subir una
    adicional, obligatoria solo si el perfil todavía no tiene ninguna.
    """

    signature_image = forms.FileField(
        label="Imagen de firma",
        required=False,
        validators=[validate_signature_image],
        help_text="Imagen PNG (preferible con fondo transparente) o JPG.",
        widget=forms.ClearableFileInput(attrs=IMAGE_INPUT_ATTRS),
    )
    signature_name = forms.CharField(
        label="Nombre de la firma",
        max_length=80,
        required=False,
        initial="Firma principal",
        widget=forms.TextInput(
            attrs={"class": INPUT_CLASSES, "placeholder": "Ej.: Firma completa, Rúbrica"}
        ),
    )

    class Meta:
        model = SignatureProfile
        fields = [
            "full_name",
            "id_document",
            "email",
            "title",
            "is_active",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": INPUT_CLASSES}),
            "id_document": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "V-12345678"}
            ),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASSES}),
            "title": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Cargo (opcional)"}
            ),
            "is_active": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_images = bool(self.instance.pk and self.instance.images.exists())
        if self.has_images:
            self.fields["signature_image"].label = "Agregar otra firma (opcional)"
        else:
            self.fields["signature_image"].required = True

    def save_signature_image(self, profile):
        """Crea la imagen subida (si hay) para ``profile`` ya guardado."""
        upload = self.cleaned_data.get("signature_image")
        if not upload:
            return None
        img = SignatureImage.objects.create(
            profile=profile,
            name=self.cleaned_data.get("signature_name") or "Firma principal",
            image=upload,
        )
        if not self.has_images:
            img.make_default()
        return img


class SignatureImageForm(forms.ModelForm):
    """Alta de una imagen de firma adicional."""

    class Meta:
        model = SignatureImage
        fields = ["name", "image", "is_default"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Ej.: Firma completa, Rúbrica"}
            ),
            "image": forms.ClearableFileInput(attrs=IMAGE_INPUT_ATTRS),
            "is_default": forms.CheckboxInput(
                attrs={"class": "h-4 w-4 rounded border-slate-300"}
            ),
        }
