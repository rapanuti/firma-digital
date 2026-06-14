"""Vistas públicas de verificación (sin login)."""

from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from documents.utils import sha256_of
from signing.models import AuditEvent, Signature

from .forms import VerifyByFileForm
from .utils import mask_id_document


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _log_verification(request, signature):
    AuditEvent.objects.create(
        action=AuditEvent.Action.VERIFIED,
        signature=signature,
        document=signature.document,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        verification_code=signature.verification_code,
        status=signature.status,
    )


def index(request):
    """Portada de verificación: por código o por archivo."""
    code = request.GET.get("codigo", "").strip()
    if code:
        return redirect("verification:detail", code=code)
    return render(request, "verification/index.html", {"file_form": VerifyByFileForm()})


def detail(request, code):
    """Resultado de verificación de un código, con comparación opcional de archivo."""
    signature = (
        Signature.objects.select_related("document", "signer")
        .filter(verification_code=code)
        .first()
    )
    if signature:
        _log_verification(request, signature)

    file_match = None
    file_form = VerifyByFileForm()
    if request.method == "POST" and signature:
        file_form = VerifyByFileForm(request.POST, request.FILES)
        if file_form.is_valid():
            digest = sha256_of(file_form.cleaned_data["archivo"])
            file_match = digest == signature.signed_sha256

    context = {
        "signature": signature,
        "code": code,
        "masked_ci": mask_id_document(signature.signer_id_document) if signature else None,
        "show_title": settings.VERIFICATION_SHOW_DOCUMENT_TITLE,
        "file_form": file_form,
        "file_match": file_match,
    }
    return render(request, "verification/detail.html", context)


@require_POST
def verify_by_file(request):
    """Busca una firma cuyo hash coincida con el del PDF subido."""
    form = VerifyByFileForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "verification/index.html", {"file_form": form})

    digest = sha256_of(form.cleaned_data["archivo"])
    signature = (
        Signature.objects.select_related("document", "signer")
        .filter(signed_sha256=digest)
        .first()
    )
    if signature:
        _log_verification(request, signature)

    return render(
        request,
        "verification/file_result.html",
        {
            "signature": signature,
            "digest": digest,
            "masked_ci": mask_id_document(signature.signer_id_document) if signature else None,
            "show_title": settings.VERIFICATION_SHOW_DOCUMENT_TITLE,
        },
    )
