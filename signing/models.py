"""Modelos de firma: registro de firma (sello) y eventos de auditoría."""

from django.conf import settings
from django.db import models

from documents.models import Document


def signed_pdf_path(instance, filename):
    """Ruta del PDF firmado, nombrada por el código de verificación."""
    return f"documents/signed/{instance.document.owner_id}/{instance.verification_code}.pdf"


class Signature(models.Model):
    """Registro inmutable de una firma emitida (la fuente de verdad)."""

    class Status(models.TextChoices):
        VALID = "valid", "Válida"
        VOIDED = "voided", "Anulada"

    document = models.ForeignKey(
        Document, on_delete=models.PROTECT, related_name="signatures"
    )
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signatures"
    )

    # Snapshot inmutable de la identidad al momento de firmar (no cambia si el
    # usuario edita su perfil después).
    signer_name = models.CharField(max_length=150)
    signer_id_document = models.CharField(max_length=30)
    signer_title = models.CharField(max_length=150, blank=True)

    # Ubicación usada (normalizada 0..1, origen arriba-izquierda).
    page_number = models.PositiveIntegerField()
    pos_x = models.FloatField()
    pos_y = models.FloatField()
    width = models.FloatField()
    height = models.FloatField()
    page_rotation = models.IntegerField(default=0)
    qr_mode = models.CharField(max_length=4, default="url")  # "url" o "data"

    # Archivos e integridad.
    signed_file = models.FileField(upload_to=signed_pdf_path)
    original_sha256 = models.CharField(max_length=64)
    signed_sha256 = models.CharField(max_length=64)

    # Verificación pública.
    verification_code = models.CharField(max_length=40, unique=True, db_index=True)
    signed_at = models.DateTimeField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.VALID, db_index=True
    )

    # Anulación (una firma no se modifica; solo se anula y se emite otra).
    void_reason = models.TextField(blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "firma"
        verbose_name_plural = "firmas"

    def __str__(self):
        return self.verification_code

    @property
    def is_valid(self) -> bool:
        return self.status == self.Status.VALID

    @property
    def verification_url(self) -> str:
        base = settings.VERIFICATION_BASE_URL.rstrip("/")
        return f"{base}/verificar/{self.verification_code}/"


class AuditEvent(models.Model):
    """Bitácora append-only de acciones sobre documentos y firmas."""

    class Action(models.TextChoices):
        UPLOADED = "uploaded", "Subido"
        SIGNED = "signed", "Firmado"
        VOIDED = "voided", "Anulado"
        VERIFIED = "verified", "Verificado"
        DOWNLOADED = "downloaded", "Descargado"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    document = models.ForeignKey(
        Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    signature = models.ForeignKey(
        Signature, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Snapshot de los datos relevantes en el momento del evento.
    page_number = models.PositiveIntegerField(null=True, blank=True)
    pos_x = models.FloatField(null=True, blank=True)
    pos_y = models.FloatField(null=True, blank=True)
    width = models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    original_sha256 = models.CharField(max_length=64, blank=True)
    signed_sha256 = models.CharField(max_length=64, blank=True)
    verification_code = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "evento de auditoría"
        verbose_name_plural = "eventos de auditoría"

    def __str__(self):
        return f"{self.get_action_display()} · {self.verification_code or self.document_id}"
