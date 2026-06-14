"""Tests de la app documents (Fases 3 y 4): subida, hash, listado, ubicación."""

import hashlib
import json

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import SignatureProfile
from documents.geometry import fractions_to_rect
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


def test_subir_pdf_nombre_muy_largo(client, firmante, pdf_carta_bytes):
    """Un nombre de archivo largo (>100) no debe bloquear la subida."""
    client.login(username="ana", password=PASSWORD)
    nombre = "a" * 200 + ".pdf"
    f = SimpleUploadedFile(nombre, pdf_carta_bytes, content_type="application/pdf")
    resp = client.post(reverse("documents:upload"), {"title": "X", "original_file": f})
    assert resp.status_code == 302
    assert Document.objects.filter(owner=firmante).exists()


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


def test_subir_rechaza_pdf_demasiado_grande(client, firmante, settings, pdf_carta):
    """Se respeta el límite de tamaño configurable (MAX_PDF_SIZE_MB)."""
    settings.MAX_PDF_SIZE_MB = 0  # cualquier archivo no vacío supera el límite
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("documents:upload"), {"title": "X", "original_file": pdf_carta}
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


# === Fase 4: geometría y ubicación =======================================


def test_fractions_to_rect_carta():
    """Conversión directa en una página Carta (sin rotación)."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    r = fractions_to_rect(page, 0.1, 0.2, 0.3, 0.1)
    assert abs(r.x0 - 61.2) < 0.01
    assert abs(r.y0 - 158.4) < 0.01
    assert abs(r.width - 183.6) < 0.01
    assert abs(r.height - 79.2) < 0.01
    doc.close()


def test_fractions_to_rect_rotada_90():
    """Con rotación 90°, page.rect intercambia ancho/alto y la conversión sigue."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.set_rotation(90)
    r = fractions_to_rect(page, 0.0, 0.0, 1.0, 1.0)
    assert abs(r.width - 792) < 0.01   # ancho visible = alto original
    assert abs(r.height - 612) < 0.01
    doc.close()


def _make_doc_local(owner, pdf_bytes):
    return Document.objects.create(
        owner=owner,
        title="Doc",
        original_file=SimpleUploadedFile("d.pdf", pdf_bytes, content_type="application/pdf"),
        original_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_size=len(pdf_bytes),
        page_count=1,
    )


def _con_perfil(user, png):
    return SignatureProfile.objects.create(
        user=user, full_name="Ana", id_document="V-1", email="a@e.com",
        signature_image=png, is_active=True,
    )


def test_placement_api_guarda(client, firmante, pdf_carta_bytes):
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("documents:placement_api", args=[doc.pk]),
        data=json.dumps({"page": 1, "fx": 0.1, "fy": 0.2, "fw": 0.3, "fh": 0.1, "rotation": 0}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    doc.refresh_from_db()
    assert doc.placement_page == 1
    assert abs(doc.placement_x - 0.1) < 1e-6
    assert doc.has_placement is True


def test_placement_api_guarda_qr_mode(client, firmante, pdf_carta_bytes):
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    client.post(
        reverse("documents:placement_api", args=[doc.pk]),
        data=json.dumps({"page": 1, "fx": 0.1, "fy": 0.2, "fw": 0.3, "fh": 0.1, "qr_mode": "data"}),
        content_type="application/json",
    )
    doc.refresh_from_db()
    assert doc.qr_mode == "data"


def test_placement_api_qr_mode_invalido_cae_a_url(client, firmante, pdf_carta_bytes):
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    client.post(
        reverse("documents:placement_api", args=[doc.pk]),
        data=json.dumps({"page": 1, "fx": 0.1, "fy": 0.2, "fw": 0.3, "fh": 0.1, "qr_mode": "xxx"}),
        content_type="application/json",
    )
    doc.refresh_from_db()
    assert doc.qr_mode == "url"


def test_placement_api_rechaza_fuera_de_rango(client, firmante, pdf_carta_bytes):
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(
        reverse("documents:placement_api", args=[doc.pk]),
        data=json.dumps({"page": 1, "fx": 0.9, "fy": 0, "fw": 0.5, "fh": 0.1, "rotation": 0}),
        content_type="application/json",
    )
    assert resp.status_code == 400  # fx + fw > 1
    doc.refresh_from_db()
    assert doc.has_placement is False


def test_place_requiere_perfil_firma(client, firmante, pdf_carta_bytes):
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("documents:place", args=[doc.pk]))
    assert resp.status_code == 302
    assert reverse("accounts:signature_profile_edit") in resp.url


def test_place_con_perfil_ok(client, firmante, png_firma, pdf_carta_bytes):
    _con_perfil(firmante, png_firma)
    doc = _make_doc_local(firmante, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("documents:place", args=[doc.pk]))
    assert resp.status_code == 200
    assert b"Ubicar firma" in resp.content


def test_place_requiere_propiedad(client, firmante, otro, png_firma, pdf_carta_bytes):
    _con_perfil(otro, png_firma)
    doc = _make_doc_local(otro, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("documents:place", args=[doc.pk]))
    assert resp.status_code == 403  # _get_document_or_403 (igual que la descarga)
