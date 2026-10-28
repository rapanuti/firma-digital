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

    # Las ubicaciones de firma (borrador) viven en SignaturePlacement.
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
        return self.placements.exists()


class SignaturePlacement(models.Model):
    """Un bloque de firma ubicado sobre el documento (puede haber varios).

    Posición normalizada 0..1, origen arriba-izquierda, respecto del recuadro
    visible de la página. Se resuelve a puntos PDF al firmar.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="placements"
    )
    # Firma a estampar (None = la predeterminada del perfil al momento de firmar).
    signature_image = models.ForeignKey(
        "accounts.SignatureImage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    page = models.PositiveIntegerField()
    x = models.FloatField()
    y = models.FloatField()
    w = models.FloatField()
    h = models.FloatField()
    rotation = models.IntegerField(default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "ubicación de firma"
        verbose_name_plural = "ubicaciones de firma"

    def __str__(self):
        return f"{self.document} · pág. {self.page}"
