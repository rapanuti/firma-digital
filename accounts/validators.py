"""Validadores de archivos para la app accounts."""

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}


def validate_signature_image(f):
    """Valida que el archivo sea una imagen PNG/JPG dentro del tamaño permitido.

    Se prefiere PNG con fondo transparente para la firma manuscrita, pero se
    aceptan también JPG.
    """
    max_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    if f.size and f.size > max_bytes:
        raise ValidationError(
            f"La imagen supera el máximo de {settings.MAX_IMAGE_SIZE_MB} MB."
        )

    name = (getattr(f, "name", "") or "").lower()
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("Formato no permitido. Usa una imagen PNG o JPG.")

    # Verifica que el contenido sea realmente una imagen (no solo la extensión).
    try:
        f.seek(0)
        img = Image.open(f)
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise ValidationError("El archivo no es una imagen válida.")
    finally:
        f.seek(0)

    if img.format not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Formato no permitido. Usa una imagen PNG o JPG.")
