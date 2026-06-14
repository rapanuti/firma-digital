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

    class QrMode(models.TextChoices):
        URL = "url", "URL de verificación"
        DATA = "data", "Datos de la firma (offline)"

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

    # Ubicación de firma (borrador). Normalizado 0..1, origen arriba-izquierda,
    # respecto del recuadro visible de la página. Se resuelve a puntos al firmar.
    placement_page = models.PositiveIntegerField(null=True, blank=True)
    placement_x = models.FloatField(null=True, blank=True)
    placement_y = models.FloatField(null=True, blank=True)
    placement_w = models.FloatField(null=True, blank=True)
    placement_h = models.FloatField(null=True, blank=True)
    placement_rotation = models.IntegerField(default=0)
    qr_mode = models.CharField(
        max_length=4, choices=QrMode.choices, default=QrMode.URL
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "documento"
        verbose_name_plural = "documentos"

    def __str__(self):
        return self.title

    @property
    def has_placement(self) -> bool:
        return None not in (
            self.placement_page,
            self.placement_x,
            self.placement_y,
            self.placement_w,
            self.placement_h,
        )
