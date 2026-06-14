"""Vistas de firma: confirmar, generar el PDF firmado, resultado y descarga."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from documents.models import Document

from .models import AuditEvent, Signature
from .services import SigningError, make_qr_png, sign_document, void_signature


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _own_document_or_403(request, doc_id):
    doc = get_object_or_404(Document, pk=doc_id)
    if doc.owner_id != request.user.id and not request.user.is_admin_role:
        raise PermissionDenied
    return doc


def _own_signature_or_403(request, pk):
    sig = get_object_or_404(Signature, pk=pk)
    if sig.document.owner_id != request.user.id and not request.user.is_admin_role:
        raise PermissionDenied
    return sig


@login_required
def sign_view(request, doc_id):
    """GET: pantalla de confirmación. POST: genera el PDF firmado."""
    doc = _own_document_or_403(request, doc_id)

    if doc.status != Document.Status.PENDING:
        messages.info(request, "Este documento ya no está pendiente de firma.")
        return redirect("documents:detail", pk=doc.pk)
    if not doc.has_placement:
        messages.warning(request, "Primero ubica la firma en el documento.")
        return redirect("documents:place", pk=doc.pk)

    if request.method == "POST":
        try:
            signature = sign_document(
                doc,
                request.user,
                ip=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except SigningError as exc:
            messages.error(request, str(exc))
            return redirect("documents:detail", pk=doc.pk)
        messages.success(request, "Documento firmado correctamente.")
        return redirect("signing:result", pk=signature.pk)

    profile = getattr(request.user, "signature_profile", None)
    return render(request, "signing/sign_confirm.html", {"documento": doc, "perfil": profile})


@login_required
def result_view(request, pk):
    """Pantalla de resultado con código, QR, hashes y descarga."""
    sig = _own_signature_or_403(request, pk)
    import base64

    qr_b64 = base64.b64encode(make_qr_png(sig.verification_url)).decode("ascii")
    return render(
        request,
        "signing/signature_result.html",
        {"firma": sig, "qr_data_uri": f"data:image/png;base64,{qr_b64}"},
    )


@login_required
def download_signed(request, pk):
    """Descarga protegida del PDF firmado (solo dueño del documento o admin)."""
    sig = _own_signature_or_403(request, pk)
    return FileResponse(
        sig.signed_file.open("rb"),
        as_attachment=True,
        filename=f"{sig.document.title}-firmado.pdf",
        content_type="application/pdf",
    )


@login_required
def void_view(request, pk):
    """Anula una firma (dueño del documento o admin). GET confirma, POST anula."""
    sig = _own_signature_or_403(request, pk)

    if sig.status != Signature.Status.VALID:
        messages.info(request, "Esta firma ya está anulada.")
        return redirect("signing:result", pk=sig.pk)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Debes indicar el motivo de la anulación.")
            return render(request, "signing/void_confirm.html", {"firma": sig})
        void_signature(
            sig,
            request.user,
            reason,
            ip=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        messages.success(request, "Firma anulada.")
        return redirect("signing:result", pk=sig.pk)

    return render(request, "signing/void_confirm.html", {"firma": sig})


@login_required
def audit_list(request):
    """Bitácora de auditoría: el admin ve todo; el firmante, lo suyo."""
    events = AuditEvent.objects.select_related("actor", "document", "signature")
    if not request.user.is_admin_role:
        events = events.filter(
            Q(actor=request.user) | Q(document__owner=request.user)
        ).distinct()
    return render(request, "signing/audit_list.html", {"eventos": events[:500]})
