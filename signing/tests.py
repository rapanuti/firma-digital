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

def _nueva_firma(profile, **kwargs):
    """Firma con los datos del perfil (como se crean desde la interfaz)."""
    from accounts.models import SignatureImage

    img = SignatureImage.from_profile(profile, **kwargs)
    img.save()
    return img


PASSWORD = "clave-segura-123"


def _setup(owner, png, pdf_bytes, *, with_placement=True, active=True):
    profile = SignatureProfile.objects.create(
        user=owner,
        full_name="Ana Pérez",
        id_document="V-12345678",
        email="a@e.com",
        is_active=active,
    )
    _nueva_firma(profile, image=png, is_default=True)
    doc = Document.objects.create(
        owner=owner,
        title="Contrato",
        original_file=SimpleUploadedFile("d.pdf", pdf_bytes, content_type="application/pdf"),
        original_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        file_size=len(pdf_bytes),
        page_count=1,
    )
    if with_placement:
        doc.placements.create(page=1, x=0.1, y=0.6, w=0.6, h=0.25)
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
        # El SHA-256 del documento ORIGINAL aparece impreso en el sello.
        assert "SHA-256" in text
        assert sig.original_sha256[:16] in text
        # Hay al menos 2 imágenes nuevas: firma manuscrita + QR.
        assert len(page.get_images()) >= 2
    finally:
        pdf.close()


def test_qr_content_segun_modo():
    from documents.models import Document
    from signing.services import _qr_content

    kw = dict(url="http://x/verificar/ABC", name="Ana Pérez", ci="V-1",
              fecha="14/06/2026 10:00", code="ABC", original_sha256="deadbeef")
    data = _qr_content(Document.QrMode.DATA, **kw)
    assert "Ana Pérez" in data and "ABC" in data and "deadbeef" in data
    # En modo datos NO debe haber ninguna URL.
    assert "http" not in data and "Verificar" not in data
    assert _qr_content(Document.QrMode.URL, **kw) == "http://x/verificar/ABC"


def test_sign_guarda_qr_mode(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    doc.qr_mode = "data"
    doc.save(update_fields=["qr_mode"])
    sig = sign_document(doc, firmante)
    assert sig.qr_mode == "data"


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


# --- Elección de firma ---------------------------------------------------


def _otra_png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(buf, "PNG")
    return SimpleUploadedFile("rubrica.png", buf.getvalue(), content_type="image/png")


def test_sign_usa_predeterminada_por_defecto(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    sig = sign_document(doc, firmante)
    assert sig.signature_image == firmante.signature_profile.default_image


def test_sign_usa_firma_elegida_en_documento(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    rubrica = _nueva_firma(firmante.signature_profile, name="Rúbrica", image=_otra_png())
    doc.placements.update(signature_image=rubrica)
    sig = sign_document(doc, firmante)
    assert sig.signature_image == rubrica
    ev = AuditEvent.objects.get(signature=sig, action=AuditEvent.Action.SIGNED)
    assert ev.metadata["seals"][0]["signature_image"] == "Rúbrica"


def test_sign_rechaza_firma_ajena(db, firmante, otro, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    _setup(otro, _otra_png(), pdf_carta_bytes)
    with pytest.raises(SigningError):
        sign_document(
            doc, firmante,
            images={doc.placements.get().pk: otro.signature_profile.default_image},
        )


def test_sign_view_aplica_firma_elegida(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    rubrica = _nueva_firma(firmante.signature_profile, name="Rúbrica", image=_otra_png())
    client.login(username="ana", password=PASSWORD)

    resp = client.get(reverse("signing:sign", args=[doc.pk]))
    assert b"R\xc3\xbabrica" in resp.content

    placement = doc.placements.get()
    resp = client.post(
        reverse("signing:sign", args=[doc.pk]), {f"firma_{placement.pk}": rubrica.pk}
    )
    assert resp.status_code == 302
    assert Signature.objects.get(document=doc).signature_image == rubrica


def test_sello_usa_datos_de_la_firma_elegida(db, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    representante = _nueva_firma(
        firmante.signature_profile,
        name="Representante",
        image=_otra_png(),
        full_name="Inversiones Ana C.A.",
        id_document="J-40123456-7",
        title="Representante legal",
    )
    sig = sign_document(doc, firmante, images={doc.placements.get().pk: representante})

    assert sig.signer_name == "Inversiones Ana C.A."
    assert sig.signer_id_document == "J-40123456-7"
    assert sig.signer_title == "Representante legal"
    pdf = fitz.open(stream=_read(sig.signed_file), filetype="pdf")
    try:
        text = pdf[0].get_text()
        assert "Inversiones Ana C.A." in text
        assert "J-40123456-7" in text
        assert "Ana Pérez" not in text
    finally:
        pdf.close()


# --- Varias firmas en un mismo documento ---------------------------------


def _pdf_dos_paginas():
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    doc.new_page(width=612, height=792)
    data = doc.tobytes()
    doc.close()
    return data


def test_varias_firmas_mismo_instante(db, firmante, png_firma):
    pdf_bytes = _pdf_dos_paginas()
    doc = _setup(firmante, png_firma, pdf_bytes, with_placement=False)
    doc.page_count = 2
    doc.save(update_fields=["page_count"])
    profile = firmante.signature_profile
    cesare = _nueva_firma(
        profile, name="Cesare", image=_otra_png(),
        full_name="Cesare Domenighini", id_document="V-111",
    )
    jesus = _nueva_firma(
        profile, name="Jesus", image=_otra_png(),
        full_name="Jesus Lopez", id_document="V-222",
    )
    doc.placements.create(page=1, x=0.05, y=0.7, w=0.45, h=0.2, order=0)
    doc.placements.create(page=1, x=0.5, y=0.7, w=0.45, h=0.2, signature_image=cesare, order=1)
    doc.placements.create(page=2, x=0.1, y=0.1, w=0.5, h=0.2, signature_image=jesus, order=2)

    sig = sign_document(doc, firmante)

    # Un solo PDF, un solo código y un sello por ubicación.
    assert Signature.objects.filter(document=doc).count() == 1
    seals = list(sig.seals.all())
    assert [s.signer_name for s in seals] == ["Ana Pérez", "Cesare Domenighini", "Jesus Lopez"]
    assert [s.page_number for s in seals] == [1, 1, 2]

    pdf = fitz.open(stream=_read(sig.signed_file), filetype="pdf")
    try:
        p1, p2 = pdf[0].get_text(), pdf[1].get_text()
        assert "Ana Pérez" in p1 and "Cesare Domenighini" in p1
        assert "Jesus Lopez" in p2 and "Jesus Lopez" not in p1
        assert p1.count(sig.verification_code) == 2
        assert sig.verification_code in p2
    finally:
        pdf.close()

    ev = AuditEvent.objects.get(signature=sig, action=AuditEvent.Action.SIGNED)
    assert len(ev.metadata["seals"]) == 3


def test_confirmar_elige_firma_por_bloque(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    segundo = doc.placements.create(page=1, x=0.1, y=0.1, w=0.4, h=0.2, order=1)
    primero = doc.placements.order_by("order", "pk").first()
    otra = _nueva_firma(
        firmante.signature_profile, name="Otra", image=_otra_png(),
        full_name="Otra Persona", id_document="V-9",
    )
    client.login(username="ana", password=PASSWORD)
    resp = client.get(reverse("signing:sign", args=[doc.pk]))
    assert resp.content.count(b"<select") == 2

    client.post(
        reverse("signing:sign", args=[doc.pk]),
        {f"firma_{primero.pk}": firmante.signature_profile.default_image.pk,
         f"firma_{segundo.pk}": otra.pk},
    )
    sig = Signature.objects.get(document=doc)
    assert [s.signer_name for s in sig.seals.all()] == ["Ana Pérez", "Otra Persona"]


def test_verificacion_publica_lista_firmantes(client, firmante, png_firma, pdf_carta_bytes):
    doc = _setup(firmante, png_firma, pdf_carta_bytes)
    otra = _nueva_firma(
        firmante.signature_profile, name="Otra", image=_otra_png(),
        full_name="Otra Persona", id_document="V-98765432",
    )
    doc.placements.create(page=1, x=0.1, y=0.1, w=0.4, h=0.2, signature_image=otra, order=1)
    sig = sign_document(doc, firmante)

    resp = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert b"Ana P" in resp.content and b"Otra Persona" in resp.content
    assert b"Firmante 2" in resp.content
    assert b"V-98765432" not in resp.content  # C.I. enmascarada
