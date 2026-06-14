"""URLs raíz del proyecto firma_digital."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import DashboardView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("documentos/", include("documents.urls")),
    path("", include("signing.urls")),
    path("verificar/", include("verification.urls")),
    path("", DashboardView.as_view(), name="dashboard"),
]

# En desarrollo Django sirve los archivos subidos (firmas, etc.).
# En PRODUCCIÓN esto NO aplica: los originales y firmados deben servirse por
# vistas con control de acceso, nunca como URL pública directa (riesgo R5).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
