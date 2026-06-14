from django.contrib import admin

from .models import AuditEvent, Signature


@admin.register(Signature)
class SignatureAdmin(admin.ModelAdmin):
    list_display = ("verification_code", "signer_name", "document", "status", "signed_at")
    list_filter = ("status",)
    search_fields = ("verification_code", "signer_name", "signer_id_document")
    readonly_fields = [f.name for f in Signature._meta.fields]


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "verification_code", "actor", "ip_address", "timestamp")
    list_filter = ("action",)
    search_fields = ("verification_code", "actor__username", "ip_address")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_change_permission(self, request, obj=None):
        # Auditoría append-only: no se edita desde el admin.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
