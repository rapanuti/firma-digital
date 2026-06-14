"""Tests de la app signing (Fase 5): generación del PDF firmado y registros."""

import hashlib

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import SignatureProfile
from documents.models import Document
from signing.models import AuditEvent, Signature
from signing.services import SigningError, sign_document, void_signature

PASSWORD = "clave-segura-123"


def _setup(owner, png, pdf_bytes, *, with_placement=True, active=True):
    SignatureProfile.objects.create(
        user=owner,
        full_name="Ana Pérez",
        id_document="V-12345678",
        email="a@e.com",
        signature_image=png,
        is_active=active,
    )
    doc = Document.objects.create(
        owner=owner,
        title="Contrato",
        original_file=SimpleUploadedFile("d.pdf", pdf_bytes, content_type="application/pdf"),
        original_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_size=len(pdf_bytes),
        page_count=1,
    )
    if with_placement:
        doc.placement_page = 1
        doc.placement_x, doc.placement_y = 0.1, 0.6
        doc.placement_w, doc.placement_h = 0.6, 0.25
        doc.placement_rotation = 0
        doc.save()
    return doc


def _read(filefield):
    filefield.open("rb")
    data = filefield.read()
    filefield.close()
    return data


# --- Servicio de firma ---------------------------------------------------


def test_sign_document_crea_firma_y_auditoria(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante, ip="1.2.3.4", user_agent="pytest")

    assert sig.status == Signature.Status.VALID
    assert sig.verification_code.startswith("FIRMA-")
    doc.refresh_from_db()
    assert doc.status == Document.Status.SIGNED

    # El hash del original queda copiado; el del firmado coincide con el archivo.
    assert sig.original_sha256 == doc.original_sha256
    assert hashlib.sha256(_read(sig.signed_file)).hexdigest() == sig.signed_sha256

    # Registro de auditoría del evento de firma, con IP y coordenadas.
    ev = AuditEvent.objects.get(signature=sig, action=AuditEvent.Action.SIGNED)
    assert ev.ip_address == "1.2.3.4"
    assert ev.verification_code == sig.verification_code
    assert ev.page_number == 1


def test_pdf_firmado_contiene_sello(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante)

    pdf = fitz.open(stream=_read(sig.signed_file), filetype="pdf")
    try:
        page = pdf[0]
        text = page.get_text()
        assert "Ana Pérez" in text
        assert sig.verification_code in text
        assert "Firmado electrónicamente" in text
        # Hay al menos 2 imágenes nuevas: firma manuscrita + QR.
        assert len(page.get_images()) >= 2
    finally:
        pdf.close()


def test_codigos_son_unicos(db, firmante, otro, png_firma, pdf_carta_bytes):
    sig1 = sign_document(_setup(firmante, png_firma, pdf_carta_bytes), firmante)
    sig2 = sign_document(_setup(otro, png_firma, pdf_carta_bytes), otro)
    assert sig1.verification_code != sig2.verification_code


def test_sign_requiere_ubicacion(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes, with_placement=False)
    with pytest.raises(SigningError):
        sign_document(doc, firmante)


def test_sign_requiere_perfil_activo(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes, active=False)
    with pytest.raises(SigningError):
        sign_document(doc, firmante)


def test_no_refirma_documento_firmado(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sign_document(doc, firmante)
    with pytest.raises(SigningError):
        sign_document(doc, firmante)  # ya está firmado


# --- Vistas --------------------------------------------------------------


def test_sign_view_post_firma(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(reverse("signing:sign", args=[doc.pk]))
    assert resp.status_code == 302
    sig = Signature.objects.get(document=doc)
    assert resp.url == reverse("signing:result", args=[sig.pk])
    doc.refresh_from_db()
    assert doc.status == Document.Status.SIGNED


def test_sign_view_sin_ubicacion_redirige(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes, with_placement=False)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("signing:sign", args=[doc.pk]))
    assert resp.status_code == 302
    assert reverse("documents:place", args=[doc.pk]) in resp.url


def test_sign_view_ajeno_prohibido(client, firmante, otro, png_firma, pdf_carta_bytes):
    doc = _setup(otro, png_firma, pdf_carta_bytes)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("signing:sign", args=[doc.pk]))
    assert resp.status_code == 403


def test_descarga_firmado_protegida(client, firmante, otro, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante)
    url = reverse("signing:download_signed", args=[sig.pk])

    client.login(username="ana", password=PASSWORD)
    assert client.get(url).status_code == 200

    client.logout()
    client.login(username="otro", password=PASSWORD)
    assert client.get(url).status_code == 403


def test_result_view_muestra_codigo(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("signing:result", args=[sig.pk]))
    assert resp.status_code == 200
    assert sig.verification_code.encode() in resp.content


# === Fase 7: anulación y auditoría =======================================


def test_void_signature_service(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante)
    void_signature(sig, firmante, "Error en los datos", ip="9.9.9.9")

    sig.refresh_from_db()
    doc.refresh_from_db()
    assert sig.status == Signature.Status.VOIDED
    assert sig.void_reason == "Error en los datos"
    assert sig.voided_by == firmante
    assert doc.status == Document.Status.VOIDED
    assert AuditEvent.objects.filter(action=AuditEvent.Action.VOIDED, signature=sig).exists()


def test_no_se_puede_reanular(db, firmante, png_firma, pdf_carta_bytes):
    sig = sign_document(_setup(firmante, png_firma, pdf_carta_bytes), firmante)
    void_signature(sig, firmante, "motivo")
    with pytest.raises(SigningError):
        void_signature(sig, firmante, "otra vez")


def test_void_view_requiere_motivo(client, firmante, png_firma, pdf_carta_bytes):
    sig = sign_document(_setup(firmante, png_firma, pdf_carta_bytes), firmante)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(reverse("signing:void", args=[sig.pk]), {"reason": ""})
    assert resp.status_code == 200  # se queda en el formulario
    sig.refresh_from_db()
    assert sig.is_valid  # no se anuló


def test_void_view_ajeno_prohibido(client, firmante, otro, png_firma, pdf_carta_bytes):
    sig = sign_document(_setup(otro, png_firma, pdf_carta_bytes), otro)
    client.login(username="ana", password=PASSWORD)
    resp = client.post(reverse("signing:void", args=[sig.pk]), {"reason": "x"})
    assert resp.status_code == 403


def test_anulacion_visible_en_verificacion(client, firmante, png_firma, pdf_carta_bytes):
    sig = sign_document(_setup(firmante, png_firma, pdf_carta_bytes), firmante)
    void_signature(sig, firmante, "documento incorrecto")
    resp = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert resp.status_code == 200
    assert b"Anulada" in resp.content


def test_upload_crea_audit_event(client, firmante, pdf_carta):
    client.login(username="ana", password=PASSWORD)
    client.post(reverse("documents:upload"), {"title": "X", "original_file": pdf_carta})
    assert AuditEvent.objects.filter(action=AuditEvent.Action.UPLOADED).exists()


def test_auditoria_admin_ve_todo(client, administrador, firmante, png_firma, pdf_carta_bytes):
    sign_document(_setup(firmante, png_firma, pdf_carta_bytes), firmante)  # evento de ana
    client.login(username="root", password=PASSWORD)
    resp = client.get(reverse("signing:audit"))
    assert resp.status_code == 200
    assert b"Firmado" in resp.content


def test_auditoria_firmante_solo_lo_suyo(client, firmante, otro, png_firma, pdf_carta_bytes):
    otro_sig = sign_document(_setup(otro, png_firma, pdf_carta_bytes), otro)
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("signing:audit"))
    assert resp.status_code == 200
    # No debe ver el código de la firma de "otro".
    assert otro_sig.verification_code.encode() not in resp.content
