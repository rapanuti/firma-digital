from django.contrib import admin

from .models import Document, SignaturePlacement


class SignaturePlacementInline(admin.TabularInline):
    model = SignaturePlacement
    extra = 0


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    inlines = [SignaturePlacementInline]
    list_display = ("title", "owner", "status", "page_count", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "owner__username", "original_sha256")
    readonly_fields = ("original_sha256", "file_size", "page_count", "created_at", "updated_at")
