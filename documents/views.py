"""Vistas de documentos: listado, detalle, subida, descarga y ubicación de firma."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from accounts.models import SignatureProfile

from .forms import DocumentUploadForm
from .models import Document
from .utils import pdf_page_count, sha256_of


class OwnerScopedQuerysetMixin:
    """Restringe el queryset al dueño, salvo administradores (que ven todo)."""

    def get_queryset(self):
        qs = Document.objects.all()
        if not self.request.user.is_admin_role:
            qs = qs.filter(owner=self.request.user)
        return qs


class DocumentListView(LoginRequiredMixin, OwnerScopedQuerysetMixin, ListView):
    template_name = "documents/document_list.html"
    context_object_name = "documentos"


class DocumentDetailView(LoginRequiredMixin, OwnerScopedQuerysetMixin, DetailView):
    template_name = "documents/document_detail.html"
    context_object_name = "documento"


class DocumentCreateView(LoginRequiredMixin, CreateView):
    model = Document
    form_class = DocumentUploadForm
    template_name = "documents/document_form.html"

    def form_valid(self, form):
        f = form.cleaned_data["original_file"]
        form.instance.owner = self.request.user
        form.instance.original_sha256 = sha256_of(f)
        form.instance.file_size = f.size or 0
        form.instance.page_count = pdf_page_count(f)
        response = super().form_valid(form)  # guarda -> self.object

        from signing.models import AuditEvent

        AuditEvent.objects.create(
            actor=self.request.user,
            document=self.object,
            action=AuditEvent.Action.UPLOADED,
            ip_address=_client_ip(self.request),
            user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
            original_sha256=self.object.original_sha256,
        )
        messages.success(self.request, "Documento subido correctamente.")
        return response

    def get_success_url(self):
        return reverse("documents:detail", args=[self.object.pk])


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _get_document_or_403(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    if doc.owner_id != request.user.id and not request.user.is_admin_role:
        raise PermissionDenied
    return doc


@login_required
def download_original(request, pk):
    """Descarga protegida del PDF original (solo dueño o admin)."""
    doc = _get_document_or_403(request, pk)
    return FileResponse(
        doc.original_file.open("rb"),
        as_attachment=True,
        filename=f"{doc.title}.pdf",
        content_type="application/pdf",
    )


# --- Ubicación visual de la firma (Fase 4) -------------------------------


@ensure_csrf_cookie
@login_required
def placement_view(request, pk):
    """Página con el visor PDF.js para ubicar el bloque de firma."""
    doc = _get_document_or_403(request, pk)
    if doc.status != Document.Status.PENDING:
        messages.info(request, "Este documento ya no está pendiente de firma.")
        return redirect("documents:detail", pk=doc.pk)

    profile = SignatureProfile.objects.filter(user=request.user, is_active=True).first()
    if not profile or not profile.can_sign:
        messages.warning(
            request, "Primero configura tu firma (imagen manuscrita y datos)."
        )
        return redirect("accounts:signature_profile_edit")

    context = {
        "documento": doc,
        "perfil": profile,
        "pdf_url": reverse("documents:download_original", args=[doc.pk]),
        "signature_image_url": profile.signature_image.url,
    }
    return render(request, "documents/document_place.html", context)


@login_required
@require_POST
def placement_api(request, pk):
    """Guarda la posición normalizada del bloque de firma (JSON)."""
    doc = _get_document_or_403(request, pk)
    if doc.status != Document.Status.PENDING:
        return HttpResponseBadRequest("El documento no está pendiente.")

    try:
        data = json.loads(request.body.decode("utf-8"))
        page = int(data["page"])
        fx, fy = float(data["fx"]), float(data["fy"])
        fw, fh = float(data["fw"]), float(data["fh"])
        rotation = int(data.get("rotation", 0))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Datos inválidos.")

    if not (1 <= page <= (doc.page_count or 1)):
        return HttpResponseBadRequest("Página fuera de rango.")
    if any(not (0.0 <= v <= 1.0) for v in (fx, fy, fw, fh)):
        return HttpResponseBadRequest("Coordenadas fuera de rango.")
    if fw <= 0 or fh <= 0:
        return HttpResponseBadRequest("Tamaño inválido.")
    if fx + fw > 1.0001 or fy + fh > 1.0001:
        return HttpResponseBadRequest("El bloque se sale de la página.")
    if rotation not in (0, 90, 180, 270):
        rotation = 0

    doc.placement_page = page
    doc.placement_x, doc.placement_y = fx, fy
    doc.placement_w, doc.placement_h = fw, fh
    doc.placement_rotation = rotation
    doc.save(
        update_fields=[
            "placement_page", "placement_x", "placement_y",
            "placement_w", "placement_h", "placement_rotation", "updated_at",
        ]
    )
    return JsonResponse({"ok": True})
