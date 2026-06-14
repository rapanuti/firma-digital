"""Vistas de documentos: listado, detalle, subida y descarga protegida."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView

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
        messages.success(self.request, "Documento subido correctamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("documents:detail", args=[self.object.pk])


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
