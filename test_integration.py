"""Test de integración end-to-end del MVP (Fase 8).

Recorre el flujo completo con el cliente HTTP: perfil de firma → subir PDF →
ubicar → firmar → descargar → verificar (código y archivo) → anular.
"""

import hashlib
import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

PASSWORD = "clave-segura-123"


def test_flujo_completo(client, firmante, png_firma, pdf_carta_bytes):
    from documents.models import Document
    from signing.models import Signature

    assert client.login(username="ana", password=PASSWORD)

    # 1) Configurar el perfil de firma
    r = client.post(
        reverse("accounts:signature_profile_edit"),
        {
            "full_name": "Ana Pérez",
            "id_document": "V-12345678",
            "email": "ana@example.com",
            "signature_image": png_firma,
            "is_active": "on",
        },
    )
    assert r.status_code == 302

    # 2) Subir un PDF
    pdf = SimpleUploadedFile("contrato.pdf", pdf_carta_bytes, content_type="application/pdf")
    r = client.post(reverse("documents:upload"), {"title": "Contrato", "original_file": pdf})
    assert r.status_code == 302
    doc = Document.objects.get(owner=firmante)
    assert doc.original_sha256 == hashlib.sha256(pdf_carta_bytes).hexdigest()

    # 3) Ubicar la firma (coordenadas normalizadas, vía API)
    r = client.post(
        reverse("documents:placement_api", args=[doc.pk]),
        data=json.dumps({"page": 1, "fx": 0.1, "fy": 0.6, "fw": 0.6, "fh": 0.2, "rotation": 0}),
        content_type="application/json",
    )
    assert r.status_code == 200

    # 4) Firmar
    r = client.post(reverse("signing:sign", args=[doc.pk]))
    assert r.status_code == 302
    sig = Signature.objects.get(document=doc)
    doc.refresh_from_db()
    assert doc.status == Document.Status.SIGNED

    # 5) Descargar el PDF firmado y comprobar su hash
    r = client.get(reverse("signing:download_signed", args=[sig.pk]))
    assert r.status_code == 200
    signed_bytes = b"".join(r.streaming_content)
    assert hashlib.sha256(signed_bytes).hexdigest() == sig.signed_sha256

    # 6) Verificación pública por código -> válida
    r = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert r.status_code == 200
    assert b"V\xc3\xa1lida" in r.content

    # 7) Verificación por archivo (el PDF firmado coincide)
    r = client.post(
        reverse("verification:verify_by_file"),
        {"archivo": SimpleUploadedFile("f.pdf", signed_bytes, content_type="application/pdf")},
    )
    assert r.status_code == 200
    assert "auténtico".encode() in r.content

    # 8) Anular y comprobar que la verificación pública lo refleja
    r = client.post(reverse("signing:void", args=[sig.pk]), {"reason": "prueba de anulación"})
    assert r.status_code == 302
    r = client.get(reverse("verification:detail", args=[sig.verification_code]))
    assert b"Anulada" in r.content
