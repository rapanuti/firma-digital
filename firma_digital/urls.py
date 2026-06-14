"""URLs raíz del proyecto firma_digital.

En la Fase 0 solo se expone el admin y una página de inicio mínima para
verificar que el proyecto arranca. La autenticación y el dashboard real se
añaden en la Fase 1 (app accounts).
"""

from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="dashboard.html"), name="dashboard"),
]
