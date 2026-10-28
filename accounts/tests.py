"""Tests de la app accounts (Fase 1): autenticación, perfil y permisos por rol."""

import pytest
from django.urls import reverse

from accounts.models import User

# Las fixtures `firmante`, `administrador` y `otro` viven en conftest.py.
PASSWORD = "clave-segura-123"


# --- Modelo -------------------------------------------------------------

def test_user_model_roles(db):
    """Los helpers de rol responden correctamente."""
    ana = User.objects.create_user(
        username="x", email="x@e.com", password=PASSWORD, role=User.Role.SIGNER
    )
    root = User.objects.create_user(
        username="y", email="y@e.com", password=PASSWORD, role=User.Role.ADMIN
    )
    assert ana.is_signer and not ana.is_admin_role
    assert root.is_admin_role


# --- Login obligatorio --------------------------------------------------

def test_dashboard_redirige_sin_login(client, db):
    """El dashboard exige sesión: anónimo -> redirect a login."""
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_login_da_acceso_al_dashboard(client, firmante):
    assert client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("dashboard"))
    assert resp.status_code == 200
    assert b"Firma Digital" in resp.content


def test_login_view_post_redirige(client, firmante):
    resp = client.post(
        reverse("accounts:login"), {"username": "ana", "password": PASSWORD}
    )
    assert resp.status_code == 302  # -> LOGIN_REDIRECT_URL (dashboard)


def test_login_credenciales_invalidas(client, firmante):
    resp = client.post(
        reverse("accounts:login"), {"username": "ana", "password": "incorrecta"}
    )
    assert resp.status_code == 200  # se queda en el formulario
    assert resp.wsgi_request.user.is_anonymous


def test_logout_cierra_sesion(client, firmante):
    client.login(username="ana", password=PASSWORD)
    resp = client.post(reverse("accounts:logout"))
    assert resp.status_code == 302
    # Tras salir, el dashboard vuelve a exigir login.
    assert client.get(reverse("dashboard")).status_code == 302


# --- Perfil -------------------------------------------------------------

def test_editar_perfil(client, firmante):
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("accounts:profile_edit"),
        {"first_name": "Ana", "last_name": "Pérez", "email": "ana.nueva@example.com"},
    )
    assert resp.status_code == 302
    firmante.refresh_from_db()
    assert firmante.first_name == "Ana"
    assert firmante.email == "ana.nueva@example.com"


def test_editar_perfil_email_duplicado(client, firmante, administrador):
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("accounts:profile_edit"),
        {"first_name": "Ana", "last_name": "P", "email": "root@example.com"},
    )
    assert resp.status_code == 200  # form inválido
    assert "Ya existe un usuario".encode() in resp.content
    firmante.refresh_from_db()
    assert firmante.email == "ana@example.com"  # no cambió


# --- Permisos por rol ---------------------------------------------------

def test_user_list_anonimo_redirige(client, db):
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_user_list_firmante_prohibido(client, firmante):
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 403


def test_user_list_admin_ok(client, administrador):
    client.login(username="root", password=PASSWORD)
    resp = client.get(reverse("accounts:user_list"))
    assert resp.status_code == 200
    assert b"root" in resp.content


# --- Perfil de firma (Fase 2) -------------------------------------------

from accounts.models import SignatureProfile  # noqa: E402


def test_signature_profile_requiere_login(client, db):
    resp = client.get(reverse("accounts:signature_profile"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_crear_signature_profile(client, firmante, png_firma):
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("accounts:signature_profile_edit"),
        {
            "full_name": "Ana Pérez",
            "id_document": "V-12345678",
            "email": "ana.firma@example.com",
            "signature_image": png_firma,
            "title": "Analista",
            "is_active": "on",
        },
    )
    assert resp.status_code == 302
    profile = SignatureProfile.objects.get(user=firmante)
    assert profile.full_name == "Ana Pérez"
    assert profile.can_sign is True


def test_signature_image_rechaza_no_imagen(client, firmante):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.login(username="ana", password=PASSWORD)
    fake = SimpleUploadedFile("firma.png", b"esto no es una imagen", content_type="image/png")
    resp = client.post(
        reverse("accounts:signature_profile_edit"),
        {
            "full_name": "Ana",
            "id_document": "V-1",
            "email": "a@e.com",
            "signature_image": fake,
            "is_active": "on",
        },
    )
    assert resp.status_code == 200  # form inválido
    assert not SignatureProfile.objects.filter(user=firmante).exists()


def test_signature_profile_inactiva_no_firma(db, firmante, png_firma):
    profile = SignatureProfile.objects.create(
        user=firmante,
        full_name="Ana",
        id_document="V-1",
        email="a@e.com",
        is_active=False,
    )
    profile.images.create(image=png_firma, is_default=True)
    assert profile.can_sign is False


# --- Múltiples firmas ----------------------------------------------------

from accounts.models import SignatureImage  # noqa: E402


def _png(name="otra.png"):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (200, 80), (0, 0, 0, 0)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _perfil(user, png):
    profile = SignatureProfile.objects.create(
        user=user, full_name="Ana", id_document="V-1", email="a@e.com"
    )
    profile.images.create(name="Firma completa", image=png, is_default=True)
    return profile


def test_agregar_segunda_firma(client, firmante, png_firma):
    profile = _perfil(firmante, png_firma)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("accounts:signature_image_add"),
        {"name": "Rúbrica", "image": _png()},
    )
    assert resp.status_code == 302
    assert profile.images.count() == 2
    # La nueva no reemplaza a la predeterminada salvo que se pida.
    assert profile.default_image.name == "Firma completa"


def test_agregar_firma_como_predeterminada(client, firmante, png_firma):
    profile = _perfil(firmante, png_firma)
    client.login(username="ana", password=PASSWORD)
    client.post(
        reverse("accounts:signature_image_add"),
        {"name": "Rúbrica", "image": _png(), "is_default": "on"},
    )
    assert profile.images.filter(is_default=True).count() == 1
    assert profile.default_image.name == "Rúbrica"


def test_cambiar_predeterminada(client, firmante, png_firma):
    profile = _perfil(firmante, png_firma)
    rubrica = profile.images.create(name="Rúbrica", image=_png())
    client.login(username="ana", password=PASSWORD)
    client.post(reverse("accounts:signature_image_default", args=[rubrica.pk]))
    assert profile.default_image == rubrica
    assert profile.images.filter(is_default=True).count() == 1


def test_eliminar_firma_promueve_otra(client, firmante, png_firma):
    profile = _perfil(firmante, png_firma)
    principal = profile.default_image
    rubrica = profile.images.create(name="Rúbrica", image=_png())
    client.login(username="ana", password=PASSWORD)
    client.post(reverse("accounts:signature_image_delete", args=[principal.pk]))
    assert list(profile.images.all()) == [rubrica]
    rubrica.refresh_from_db()
    assert rubrica.is_default is True


def test_no_eliminar_unica_firma(client, firmante, png_firma):
    profile = _perfil(firmante, png_firma)
    client.login(username="ana", password=PASSWORD)
    client.post(reverse("accounts:signature_image_delete", args=[profile.default_image.pk]))
    assert profile.images.count() == 1


def test_no_gestionar_firma_ajena(client, firmante, otro, png_firma):
    ajena = _perfil(otro, png_firma).default_image
    _perfil(firmante, _png())
    client.login(username="ana", password=PASSWORD)
    resp = client.post(reverse("accounts:signature_image_delete", args=[ajena.pk]))
    assert resp.status_code == 404
    assert SignatureImage.objects.filter(pk=ajena.pk).exists()
