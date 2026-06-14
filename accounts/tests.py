"""Tests de la app accounts (Fase 1): autenticación, perfil y permisos por rol."""

import pytest
from django.urls import reverse

from accounts.models import User

PASSWORD = "clave-segura-123"


@pytest.fixture
def firmante(db):
    return User.objects.create_user(
        username="ana", email="ana@example.com", password=PASSWORD, role=User.Role.SIGNER
    )


@pytest.fixture
def administrador(db):
    return User.objects.create_user(
        username="root", email="root@example.com", password=PASSWORD, role=User.Role.ADMIN
    )


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
