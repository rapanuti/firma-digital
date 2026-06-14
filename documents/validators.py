"""Validación de archivos PDF subidos."""

import fitz  # PyMuPDF
from django.conf import settings
from django.core.exceptions import ValidationError


def validate_pdf(f):
    """Valida que el archivo sea un PDF legible, no cifrado y dentro del tamaño."""
    max_bytes = settings.MAX_PDF_SIZE_MB * 1024 * 1024
    if f.size and f.size > max_bytes:
        raise ValidationError(
            f"El PDF supera el máximo de {settings.MAX_PDF_SIZE_MB} MB."
        )

    name = (getattr(f, "name", "") or "").lower()
    if not name.endswith(".pdf"):
        raise ValidationError("El archivo debe tener extensión .pdf")

    # Magic bytes: todo PDF comienza con "%PDF-".
    f.seek(0)
    head = f.read(5)
    f.seek(0)
    if head != b"%PDF-":
        raise ValidationError("El archivo no es un PDF válido.")

    # Apertura real con PyMuPDF: detecta corrupción y cifrado.
    try:
        f.seek(0)
        data = f.read()
        f.seek(0)
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise ValidationError("No se pudo leer el PDF (archivo corrupto).")

    try:
        if doc.needs_pass:
            raise ValidationError(
                "El PDF está protegido con contraseña; no se admite."
            )
        if doc.page_count < 1:
            raise ValidationError("El PDF no contiene páginas.")
    finally:
        doc.close()
