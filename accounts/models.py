"""Modelos de cuentas: usuario custom con rol básico.

Se define un usuario custom desde el inicio del proyecto porque cambiar
AUTH_USER_MODEL después de la primera migración es muy costoso en Django.
El perfil de firma (imagen manuscrita, cédula, etc.) se añade en la Fase 2.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


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
