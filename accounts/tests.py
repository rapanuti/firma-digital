"""Tests de la app accounts.

Fase 0: smoke test de que el proyecto arranca y la página de inicio responde.
Los tests de autenticación y permisos se añaden en la Fase 1.
"""

import pytest


@pytest.mark.django_db
def test_homepage_responde_200(client):
    """La página de inicio renderiza correctamente."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Firma Digital" in resp.content


@pytest.mark.django_db
def test_user_model_roles():
    """El modelo de usuario expone los roles y sus helpers."""
    from accounts.models import User

    firmante = User.objects.create_user(
        username="ana", email="ana@example.com", password="x", role=User.Role.SIGNER
    )
    admin = User.objects.create_user(
        username="root", email="root@example.com", password="x", role=User.Role.ADMIN
    )
    assert firmante.is_signer is True
    assert firmante.is_admin_role is False
    assert admin.is_admin_role is True
