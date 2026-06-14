"""Tests de la verificación pública (Fase 6)."""

import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import SignatureProfile
from documents.models import Document
from signing.models import AuditEvent, Signature
from signing.services import sign_document
from verification.utils import mask_id_document


def _firma(owner, png, pdf_bytes):
    SignatureProfile.objects.create(
        user=owner, full_name="Ana Pérez", id_document="V-12345678",
        email="a@e.com", signature_image=png, is_active=True,
    )
    doc = Document.objects.create(
        owner=owner, title="Contrato",
        original_file=SimpleUploadedFile("d.pdf", pdf_bytes, content_type="application/pdf"),
        original_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_size=len(pdf_bytes), page_count=1,
    )
    doc.placement_page = 1
    doc.placement_x, doc.placement_y = 0.1, 0.6
    doc.placement_w, doc.placement_h = 0.6, 0.25
    doc.save()
    return sign_document(doc, owner)


def _read(filefield):
    filefield.open("rb")
    data = filefield.read()
    filefield.close()
    return data


# --- Enmascarado ---------------------------------------------------------

def test_mask_id_document():
    assert mask_id_document("V-12345678") == "V-****5678"
    assert mask_id_document("12345678") == "****5678"
    assert mask_id_document("123") == "123"


# --- Páginas públicas ----------------------------------------------------

def test_index_es_publico(client, db):
    resp = client.get(reverse("verification:index"))
    assert resp.status_code == 200  # sin login


def test_detail_codigo_valido(client, firmante, png_firma, pdf_carta_bytes):
    sig = _firma(firmante, png_firma, pdf_carta_bytes)
    resp = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert resp.status_code == 200
    assert b"V\xc3\xa1lida" in resp.content  # "Válida"
    assert sig.signer_name.encode() in resp.content
    assert b"V-****5678" in resp.content       # C.I. enmascarada
    assert b"V-12345678" not in resp.content   # nunca el documento completo
    assert sig.signed_sha256.encode() in resp.content
    assert sig.original_sha256.encode() in resp.content  # hash del original (cotejable con el sello)


def test_detail_codigo_inexistente(client, db):
    resp = client.get(reverse("verification:detail", args=["FIRMA-NOPE"]))
    assert resp.status_code == 200
    assert "no encontrada".encode() in resp.content


def test_detail_anulada(client, firmante, png_firma, pdf_carta_bytes):
    sig = _firma(firmante, png_firma, pdf_carta_bytes)
    sig.status = Signature.Status.VOIDED
    sig.save(update_fields=["status"])
    resp = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert resp.status_code == 200
    assert b"Anulada" in resp.content


def test_detail_registra_auditoria(client, firmante, png_firma, pdf_carta_bytes):
    sig = _firma(firmante, png_firma, pdf_carta_bytes)
    AuditEvent.objects.filter(action=AuditEvent.Action.VERIFIED).delete()
    client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert AuditEvent.objects.filter(
        action=AuditEvent.Action.VERIFIED, signature=sig
    ).exists()


# --- Verificación por archivo --------------------------------------------

def test_verificar_archivo_coincide(client, firmante, png_firma, pdf_carta_bytes):
    sig = _firma(firmante, png_firma, pdf_carta_bytes)
    data = _read(sig.signed_file)
    resp = client.post(
        reverse("verification:verify_by_file"),
        {"archivo": SimpleUploadedFile("firmado.pdf", data, content_type="application/pdf")},
    )
    assert resp.status_code == 200
    assert "auténtico".encode() in resp.content
    assert sig.signer_name.encode() in resp.content


def test_verificar_archivo_no_coincide(client, firmante, png_firma, pdf_carta_bytes):
    _firma(firmante, png_firma, pdf_carta_bytes)
    # El PDF original (sin firmar) no coincide con ningún hash registrado.
    resp = client.post(
        reverse("verification:verify_by_file"),
        {"archivo": SimpleUploadedFile("orig.pdf", pdf_carta_bytes, content_type="application/pdf")},
    )
    assert resp.status_code == 200
    assert "no registrado".encode() in resp.content
