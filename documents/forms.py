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
