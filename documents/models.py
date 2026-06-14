"""Modelo de documento PDF original."""

import uuid

from django.conf import settings
from django.db import models

from .validators import validate_pdf


def original_pdf_path(instance, filename):
    """Ruta única para cada PDF original (nunca se sobrescribe)."""
    return f"documents/original/{instance.owner_id}/{uuid.uuid4().hex}.pdf"


class Document(models.Model):
    """PDF subido por un usuario, pendiente de firma."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SIGNED = "signed", "Firmado"
        VOIDED = "voided", "Anulado"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    title = models.CharField("título", max_length=255)
    original_file = models.FileField(
        "PDF original", upload_to=original_pdf_path, validators=[validate_pdf]
    )
    original_sha256 = models.CharField(max_length=64, blank=True, editable=False)
    file_size = models.PositiveIntegerField("tamaño (bytes)", default=0)
    page_count = models.PositiveIntegerField("páginas", null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "documento"
        verbose_name_plural = "documentos"

    def __str__(self):
        return self.title
