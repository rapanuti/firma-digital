"""Motor de firma: genera el PDF firmado, el código único y los registros.

Todo ocurre en una transacción atómica: o se crea la firma completa (PDF firmado +
registro + auditoría + cambio de estado del documento) o no se crea nada.
"""

import io
import secrets

import fitz  # PyMuPDF
import qrcode
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from documents.geometry import fractions_to_rect
from documents.models import Document
from documents.utils import sha256_of_bytes

from .models import AuditEvent, Signature
from .seal import stamp_seal


class SigningError(Exception):
    """Error de negocio durante la firma (estado inválido, sin perfil, etc.)."""


def make_qr_png(data: str) -> bytes:
    """Genera un PNG con el código QR que apunta a ``data`` (URL de verificación)."""
    qr = qrcode.QRCode(
        border=1, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def generate_verification_code(when) -> str:
    """Código legible + sufijo aleatorio (no enumerable): FIRMA-AAAA-NNNNNN-xxxxxx."""
    n = Signature.objects.filter(signed_at__year=when.year).count() + 1
    return f"FIRMA-{when.year}-{n:06d}-{secrets.token_hex(3)}"


def _verification_url(code: str) -> str:
    return f"{settings.VERIFICATION_BASE_URL.rstrip('/')}/verificar/{code}/"


@transaction.atomic
def sign_document(document: Document, signer, *, ip=None, user_agent=""):
    """Firma ``document`` por ``signer`` y devuelve la ``Signature`` creada."""
    if document.status != Document.Status.PENDING:
        raise SigningError("El documento no está pendiente de firma.")
    if not document.has_placement:
        raise SigningError("Define la posición de la firma antes de firmar.")

    profile = getattr(signer, "signature_profile", None)
    if not profile or not profile.can_sign:
        raise SigningError("Tu perfil de firma no está activo o no tiene imagen.")

    signed_at = timezone.now()

    # Código único (con reintento ante colisión, astronómicamente improbable).
    code = generate_verification_code(signed_at)
    for _ in range(5):
        if not Signature.objects.filter(verification_code=code).exists():
            break
        code = generate_verification_code(signed_at)

    # Cargar el PDF original.
    document.original_file.open("rb")
    original_bytes = document.original_file.read()
    document.original_file.close()

    doc = fitz.open(stream=original_bytes, filetype="pdf")
    try:
        page = doc[document.placement_page - 1]
        rect = fractions_to_rect(
            page,
            document.placement_x,
            document.placement_y,
            document.placement_w,
            document.placement_h,
        )
        profile.signature_image.open("rb")
        signature_png = profile.signature_image.read()
        profile.signature_image.close()
        qr_png = make_qr_png(_verification_url(code))
        fecha = timezone.localtime(signed_at).strftime("%d/%m/%Y %H:%M")

        stamp_seal(
            page,
            rect,
            signature_png=signature_png,
            qr_png=qr_png,
            header="Firmado electrónicamente por:",
            name=profile.full_name,
            details=[
                f"C.I.: {profile.id_document}",
                f"Fecha: {fecha}",
                f"Código: {code}",
            ],
        )
        signed_bytes = doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()

    signed_sha = sha256_of_bytes(signed_bytes)

    signature = Signature(
        document=document,
        signer=signer,
        signer_name=profile.full_name,
        signer_id_document=profile.id_document,
        signer_title=profile.title,
        page_number=document.placement_page,
        pos_x=document.placement_x,
        pos_y=document.placement_y,
        width=document.placement_w,
        height=document.placement_h,
        page_rotation=document.placement_rotation,
        original_sha256=document.original_sha256,
        signed_sha256=signed_sha,
        verification_code=code,
        signed_at=signed_at,
    )
    signature.signed_file.save(f"{code}.pdf", ContentFile(signed_bytes), save=False)
    signature.save()

    document.status = Document.Status.SIGNED
    document.save(update_fields=["status", "updated_at"])

    AuditEvent.objects.create(
        actor=signer,
        document=document,
        signature=signature,
        action=AuditEvent.Action.SIGNED,
        ip_address=ip,
        user_agent=user_agent,
        page_number=signature.page_number,
        pos_x=signature.pos_x,
        pos_y=signature.pos_y,
        width=signature.width,
        height=signature.height,
        original_sha256=signature.original_sha256,
        signed_sha256=signature.signed_sha256,
        verification_code=code,
        status=signature.status,
    )
    return signature
