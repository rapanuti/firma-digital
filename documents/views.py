"""Vistas de documentos: listado, detalle, subida, descarga y ubicación de firma."""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView

from accounts.models import SignatureImage, SignatureProfile

from .forms import DocumentUploadForm
from .models import Document, SignaturePlacement
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["max_pdf_mb"] = settings.MAX_PDF_SIZE_MB
        return ctx

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

    firmas = list(profile.images.all())
    placements = [
        {
            "page": p.page, "x": p.x, "y": p.y, "w": p.w, "h": p.h,
            "rotation": p.rotation, "signature_image": p.signature_image_id,
        }
        for p in doc.placements.all()
    ]

    context = {
        "documento": doc,
        "perfil": profile,
        "firmas": firmas,
        "firma_seleccionada": profile.default_image,
        "placements": placements,
        "pdf_url": reverse("documents:download_original", args=[doc.pk]),
    }
    return render(request, "documents/document_place.html", context)


MAX_PLACEMENTS = 20


def _parse_placement(item, doc):
    """Valida un bloque recibido del editor; devuelve dict o lanza ValueError."""
    page = int(item["page"])
    fx, fy = float(item["fx"]), float(item["fy"])
    fw, fh = float(item["fw"]), float(item["fh"])
    rotation = int(item.get("rotation", 0))
    image_id = item.get("signature_image")

    if not (1 <= page <= (doc.page_count or 1)):
        raise ValueError("Página fuera de rango.")
    if any(not (0.0 <= v <= 1.0) for v in (fx, fy, fw, fh)):
        raise ValueError("Coordenadas fuera de rango.")
    if fw <= 0 or fh <= 0:
        raise ValueError("Tamaño inválido.")
    if fx + fw > 1.0001 or fy + fh > 1.0001:
        raise ValueError("El bloque se sale de la página.")
    if rotation not in (0, 90, 180, 270):
        rotation = 0
    return {
        "page": page, "x": fx, "y": fy, "w": fw, "h": fh, "rotation": rotation,
        "image_id": int(image_id) if image_id is not None else None,
    }


@login_required
@require_POST
def placement_api(request, pk):
    """Guarda los bloques de firma del documento (JSON).

    Formato: ``{"qr_mode": "url", "placements": [{page, fx, fy, fw, fh, rotation,
    signature_image}, ...]}``. También acepta un único bloque en el nivel raíz.
    Reemplaza todos los bloques anteriores.
    """
    doc = _get_document_or_403(request, pk)
    if doc.status != Document.Status.PENDING:
        return HttpResponseBadRequest("El documento no está pendiente.")

    try:
        data = json.loads(request.body.decode("utf-8"))
        items = data["placements"] if "placements" in data else [data]
        if not isinstance(items, list):
            raise ValueError("Datos inválidos.")
        parsed = [_parse_placement(item, doc) for item in items]
    except ValueError as exc:
        msg = str(exc) if str(exc).endswith(".") else "Datos inválidos."
        return HttpResponseBadRequest(msg)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Datos inválidos.")

    if not parsed:
        return HttpResponseBadRequest("Agrega al menos una firma.")
    if len(parsed) > MAX_PLACEMENTS:
        return HttpResponseBadRequest(f"Máximo {MAX_PLACEMENTS} firmas por documento.")

    image_ids = {p["image_id"] for p in parsed if p["image_id"] is not None}
    own_images = {
        img.pk: img
        for img in SignatureImage.objects.filter(pk__in=image_ids, profile__user=request.user)
    }
    if len(own_images) != len(image_ids):
        return HttpResponseBadRequest("Firma no válida.")

    qr_mode = str(data.get("qr_mode", Document.QrMode.URL))
    if qr_mode not in Document.QrMode.values:
        qr_mode = Document.QrMode.URL

    with transaction.atomic():
        doc.placements.all().delete()
        SignaturePlacement.objects.bulk_create(
            SignaturePlacement(
                document=doc,
                signature_image=own_images.get(p["image_id"]),
                page=p["page"], x=p["x"], y=p["y"], w=p["w"], h=p["h"],
                rotation=p["rotation"], order=i,
            )
            for i, p in enumerate(parsed)
        )
        doc.qr_mode = qr_mode
        doc.save(update_fields=["qr_mode", "updated_at"])
    return JsonResponse({"ok": True, "count": len(parsed)})
