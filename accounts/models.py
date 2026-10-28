"""Modelos de cuentas: usuario custom y perfil de firma.

Se define un usuario custom desde el inicio del proyecto porque cambiar
AUTH_USER_MODEL después de la primera migración es muy costoso en Django.
"""

import uuid

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
    """Ruta de almacenamiento de la firma manuscrita (por usuario, nombre único)."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return f"signatures/{instance.profile.user_id}/{uuid.uuid4().hex}.{ext}"


class SignatureProfile(models.Model):
    """Configuración de firma de un usuario (datos que aparecen en el sello)."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="signature_profile"
    )
    full_name = models.CharField("nombre completo", max_length=150)
    id_document = models.CharField("documento de identidad", max_length=30)
    email = models.EmailField("correo de firma")
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
    def default_image(self):
        """Firma predeterminada (o la más reciente si ninguna está marcada)."""
        return self.images.order_by("-is_default", "-created_at").first()

    @property
    def can_sign(self) -> bool:
        """El perfil es utilizable si está activo y tiene al menos una imagen."""
        return self.is_active and self.images.exists()


class SignatureImage(models.Model):
    """Firma del usuario: imagen manuscrita + datos que aparecen en el sello.

    Un perfil puede tener varias (p. ej. a título personal y como representante),
    cada una con su propio nombre, C.I., correo y cargo.
    """

    profile = models.ForeignKey(
        SignatureProfile, on_delete=models.CASCADE, related_name="images"
    )
    name = models.CharField("nombre de la firma", max_length=80, default="Firma principal")
    full_name = models.CharField("nombre completo", max_length=150)
    id_document = models.CharField("documento de identidad", max_length=30)
    email = models.EmailField("correo de firma")
    title = models.CharField("cargo", max_length=150, blank=True)
    image = models.ImageField(
        "imagen de firma",
        upload_to=signature_image_path,
        validators=[validate_signature_image],
        help_text="Imagen PNG (preferible con fondo transparente) o JPG.",
    )
    is_default = models.BooleanField("predeterminada", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "created_at"]
        verbose_name = "imagen de firma"
        verbose_name_plural = "imágenes de firma"

    def __str__(self):
        return self.name

    @classmethod
    def from_profile(cls, profile, **kwargs):
        """Nueva firma con los datos por defecto del perfil."""
        data = {
            "full_name": profile.full_name,
            "id_document": profile.id_document,
            "email": profile.email,
            "title": profile.title,
        }
        data.update(kwargs)
        return cls(profile=profile, **data)

    def make_default(self):
        """Marca esta imagen como la predeterminada del perfil (y desmarca las demás)."""
        self.profile.images.exclude(pk=self.pk).update(is_default=False)
        if not self.is_default:
            self.is_default = True
            self.save(update_fields=["is_default"])
