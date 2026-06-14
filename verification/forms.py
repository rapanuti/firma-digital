"""Formularios de la verificación pública."""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError


class VerifyByFileForm(forms.Form):
    """Subida de un PDF para comparar su hash con los registrados."""

    archivo = forms.FileField(
        label="Archivo PDF",
        widget=forms.ClearableFileInput(
            attrs={"class": "block w-full text-sm", "accept": "application/pdf"}
        ),
    )

    def clean_archivo(self):
        f = self.cleaned_data["archivo"]
        max_bytes = settings.MAX_PDF_SIZE_MB * 1024 * 1024
        if f.size and f.size > max_bytes:
            raise ValidationError(
                f"El archivo supera el máximo de {settings.MAX_PDF_SIZE_MB} MB."
            )
        f.seek(0)
        head = f.read(5)
        f.seek(0)
        if head != b"%PDF-":
            raise ValidationError("El archivo debe ser un PDF.")
        return f
