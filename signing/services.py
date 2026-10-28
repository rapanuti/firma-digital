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

from .models import AuditEvent, Signature, SignatureSeal
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


def _qr_content(mode, *, url, name, ci, fecha, code, original_sha256) -> str:
    """Contenido del QR según el modo elegido al ubicar la firma.

    - "url":  solo la URL de verificación (requiere el sistema en línea).
    - "data": bloque autocontenido con los datos de la firma, legible sin servidor.
    """
    if mode == Document.QrMode.DATA:
        # Modo datos: 100% autocontenido, sin URLs (lectura totalmente offline).
        return (
            "FIRMA ELECTRONICA VERIFICABLE\n"
            f"Firmante: {name}\n"
            f"C.I.: {ci}\n"
            f"Fecha: {fecha}\n"
            f"Codigo: {code}\n"
            f"SHA-256 (original): {original_sha256}"
        )
    return url


def _read_file(filefield) -> bytes:
    filefield.open("rb")
    try:
        return filefield.read()
    finally:
        filefield.close()


@transaction.atomic
def sign_document(document: Document, signer, *, images=None, ip=None, user_agent=""):
    """Firma ``document`` por ``signer`` y devuelve la ``Signature`` creada.

    Se estampa un sello en cada ubicación del documento. Todos comparten el código
    de verificación y el PDF firmado. La firma de cada sello es, en este orden:
    la indicada en ``images`` ({id de ubicación: SignatureImage}), la elegida al
    ubicar o la predeterminada del perfil.
    """
    if document.status != Document.Status.PENDING:
        raise SigningError("El documento no está pendiente de firma.")
    placements = list(document.placements.select_related("signature_image"))
    if not placements:
        raise SigningError("Define la posición de la firma antes de firmar.")

    profile = getattr(signer, "signature_profile", None)
    if not profile or not profile.can_sign:
        raise SigningError("Tu perfil de firma no está activo o no tiene imagen.")

    images = images or {}
    default_image = profile.default_image
    plan = []
    for placement in placements:
        image = images.get(placement.pk) or placement.signature_image or default_image
        if image.profile_id != profile.pk:
            raise SigningError("La firma elegida no pertenece a tu perfil.")
        plan.append((placement, image))

    signed_at = timezone.now()

    # Código único (con reintento ante colisión, astronómicamente improbable).
    code = generate_verification_code(signed_at)
    for _ in range(5):
        if not Signature.objects.filter(verification_code=code).exists():
            break
        code = generate_verification_code(signed_at)

    original_bytes = _read_file(document.original_file)
    fecha = timezone.localtime(signed_at).strftime("%d/%m/%Y %H:%M")
    image_bytes = {}

    doc = fitz.open(stream=original_bytes, filetype="pdf")
    try:
        for placement, image in plan:
            page = doc[placement.page - 1]
            rect = fractions_to_rect(page, placement.x, placement.y, placement.w, placement.h)
            if image.pk not in image_bytes:
                image_bytes[image.pk] = _read_file(image.image)

            qr_content = _qr_content(
                document.qr_mode,
                url=_verification_url(code),
                name=image.full_name,
                ci=image.id_document,
                fecha=fecha,
                code=code,
                original_sha256=document.original_sha256,
            )
            stamp_seal(
                page,
                rect,
                signature_png=image_bytes[image.pk],
                qr_png=make_qr_png(qr_content),
                header="Firmado electrónicamente por:",
                name=image.full_name,
                details=[
                    f"C.I.: {image.id_document}",
                    f"Fecha: {fecha}",
                    f"Código: {code}",
                ],
                doc_hash=document.original_sha256,
            )
        signed_bytes = doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()

    signed_sha = sha256_of_bytes(signed_bytes)

    first_placement, first_image = plan[0]
    signature = Signature(
        document=document,
        signer=signer,
        signer_name=first_image.full_name,
        signer_id_document=first_image.id_document,
        signer_title=first_image.title,
        page_number=first_placement.page,
        pos_x=first_placement.x,
        pos_y=first_placement.y,
        width=first_placement.w,
        height=first_placement.h,
        page_rotation=first_placement.rotation,
        qr_mode=document.qr_mode,
        signature_image=first_image,
        original_sha256=document.original_sha256,
        signed_sha256=signed_sha,
        verification_code=code,
        signed_at=signed_at,
    )
    signature.signed_file.save(f"{code}.pdf", ContentFile(signed_bytes), save=False)
    signature.save()

    SignatureSeal.objects.bulk_create(
        SignatureSeal(
            signature=signature,
            signature_image=image,
            signer_name=image.full_name,
            signer_id_document=image.id_document,
            signer_title=image.title,
            page_number=placement.page,
            pos_x=placement.x,
            pos_y=placement.y,
            width=placement.w,
            height=placement.h,
            order=i,
        )
        for i, (placement, image) in enumerate(plan)
    )

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
        metadata={
            "seals": [
                {"signature_image": image.name, "signer": image.full_name, "page": placement.page}
                for placement, image in plan
            ]
        },
    )
    return signature


@transaction.atomic
def void_signature(signature, by_user, reason, *, ip=None, user_agent=""):
    """Anula una firma emitida (no se modifica; se anula y se registra)."""
    if signature.status != Signature.Status.VALID:
        raise SigningError("La firma ya está anulada.")

    signature.status = Signature.Status.VOIDED
    signature.void_reason = reason
    signature.voided_at = timezone.now()
    signature.voided_by = by_user
    signature.save(update_fields=["status", "void_reason", "voided_at", "voided_by"])

    document = signature.document
    document.status = Document.Status.VOIDED
    document.save(update_fields=["status", "updated_at"])

    AuditEvent.objects.create(
        actor=by_user,
        document=document,
        signature=signature,
        action=AuditEvent.Action.VOIDED,
        ip_address=ip,
        user_agent=user_agent,
        verification_code=signature.verification_code,
        status=signature.status,
        reason=reason,
    )
    return signature
