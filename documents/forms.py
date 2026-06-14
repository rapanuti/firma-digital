"""Formularios de documentos."""

from django import forms

from .models import Document

INPUT_CLASSES = (
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm "
    "focus:border-brand-600 focus:ring-1 focus:ring-brand-600 focus:outline-none"
)


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "original_file"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": INPUT_CLASSES, "placeholder": "Nombre del documento"}
            ),
            "original_file": forms.ClearableFileInput(
                attrs={"class": "block w-full text-sm", "accept": "application/pdf"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No validar la longitud del NOMBRE original del archivo: al guardar se
        # renombra con un UUID corto (ver upload_to), así que el nombre que sube
        # el usuario puede ser tan largo como quiera.
        self.fields["original_file"].max_length = None
