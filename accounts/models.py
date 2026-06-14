"""Modelos de cuentas: usuario custom y perfil de firma.

Se define un usuario custom desde el inicio del proyecto porque cambiar
AUTH_USER_MODEL después de la primera migración es muy costoso en Django.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from .validators import validate_signature_image


class User(AbstractUser):
    """Usuario del sistema.

    Mantiene el login por ``username`` de Django (simple y estándar para el MVP),
    pero exige un correo único y añade un rol básico: administrador o firmante.
    """

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        SIGNER = "firmante", "Firmante"

    email = models.EmailField("correo electrónico", unique=True)
    role = models.CharField(
        "rol",
        max_length=20,
        choices=Role.choices,
        default=Role.SIGNER,
    )

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        full = self.get_full_name()
        return full or self.username

    @property
    def is_signer(self) -> bool:
        return self.role == self.Role.SIGNER

    @property
    def is_admin_role(self) -> bool:
        """True si es admin por rol o superusuario de Django."""
        return self.role == self.Role.ADMIN or self.is_superuser


def signature_image_path(instance, filename):
    """Ruta de almacenamiento de la firma manuscrita, por usuario."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return f"signatures/{instance.user_id}/firma.{ext}"


class SignatureProfile(models.Model):
    """Configuración de firma de un usuario (datos que aparecen en el sello)."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="signature_profile"
    )
    full_name = models.CharField("nombre completo", max_length=150)
    id_document = models.CharField("documento de identidad", max_length=30)
    email = models.EmailField("correo de firma")
    signature_image = models.ImageField(
        "firma manuscrita",
        upload_to=signature_image_path,
        validators=[validate_signature_image],
        help_text="Imagen PNG (preferible con fondo transparente) o JPG.",
    )
    title = models.CharField("cargo", max_length=150, blank=True)
    is_active = models.BooleanField("firma activa", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil de firma"
        verbose_name_plural = "perfiles de firma"

    def __str__(self):
        return f"Firma de {self.full_name}"

    @property
    def can_sign(self) -> bool:
        """La firma es utilizable si está activa y tiene imagen."""
        return self.is_active and bool(self.signature_image)
