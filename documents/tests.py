"""Tests de la app documents (Fase 3): subida, hash, listado, detalle, descarga."""

import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from documents.models import Document

PASSWORD = "clave-segura-123"


def test_upload_requiere_login(client, db):
    resp = client.get(reverse("documents:upload"))
    assert resp.status_code == 302
    assert reverse("accounts:login") in resp.url


def test_subir_pdf_crea_documento(client, firmante, pdf_carta, pdf_carta_bytes):
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("documents:upload"),
        {"title": "Contrato", "original_file": pdf_carta},
    )
    assert resp.status_code == 302
    doc = Document.objects.get(owner=firmante)
    assert doc.title == "Contrato"
    assert doc.status == Document.Status.PENDING
    assert doc.page_count == 1
    assert doc.file_size > 0
    # El hash almacenado coincide con el SHA-256 de los bytes subidos.
    assert doc.original_sha256 == hashlib.sha256(pdf_carta_bytes).hexdigest()


def test_subir_rechaza_no_pdf(client, firmante):
    client.login(username="ana", password=PASSWORD)
    fake = SimpleUploadedFile("doc.txt", b"texto plano", content_type="text/plain")
    resp = client.post(
        reverse("documents:upload"), {"title": "X", "original_file": fake}
    )
    assert resp.status_code == 200  # form inválido
    assert not Document.objects.exists()


def test_subir_rechaza_pdf_falso(client, firmante):
    """Un archivo con extensión .pdf pero sin cabecera %PDF se rechaza."""
    client.login(username="ana", password=PASSWORD)
    fake = SimpleUploadedFile("doc.pdf", b"no soy un pdf", content_type="application/pdf")
    resp = client.post(
        reverse("documents:upload"), {"title": "X", "original_file": fake}
    )
    assert resp.status_code == 200
    assert not Document.objects.exists()


def _make_doc(owner, pdf_bytes):
    return Document.objects.create(
        owner=owner,
        title="Doc de " + owner.username,
        original_file=SimpleUploadedFile("d.pdf", pdf_bytes, content_type="application/pdf"),
        original_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_size=len(pdf_bytes),
        page_count=1,
    )


def test_listado_solo_propios(client, firmante, otro, pdf_carta_bytes):
    _make_doc(firmante, pdf_carta_bytes)
    _make_doc(otro, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("documents:list"))
    assert resp.status_code == 200
    assert b"Doc de ana" in resp.content
    assert b"Doc de otro" not in resp.content


def test_admin_ve_todos(client, administrador, firmante, pdf_carta_bytes):
    _make_doc(firmante, pdf_carta_bytes)
    client.login(username="root", password=PASSWORD)
    resp = client.get(reverse("documents:list"))
    assert resp.status_code == 200
    assert b"Doc de ana" in resp.content


def test_detalle_requiere_propiedad(client, firmante, otro, pdf_carta_bytes):
    doc = _make_doc(otro, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("documents:detail", args=[doc.pk]))
    assert resp.status_code == 404  # no es suyo -> no existe para él


def test_descarga_original_protegida(client, firmante, otro, pdf_carta_bytes):
    doc = _make_doc(firmante, pdf_carta_bytes)
    url = reverse("documents:download_original", args=[doc.pk])

    # Dueño: OK
    client.login(username="ana", password=PASSWORD)
    assert client.get(url).status_code == 200

    # Otro usuario: prohibido
    client.logout()
    client.login(username="otro", password=PASSWORD)
    assert client.get(url).status_code == 403
