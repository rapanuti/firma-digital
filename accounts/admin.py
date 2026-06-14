from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import SignatureProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin del usuario custom, exponiendo el campo de rol."""

    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = BaseUserAdmin.list_filter + ("role",)
    fieldsets = BaseUserAdmin.fieldsets + (("Rol del sistema", {"fields": ("role",)}),)
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2", "role"),
            },
        ),
    )


@admin.register(SignatureProfile)
class SignatureProfileAdmin(admin.ModelAdmin):
    list_display = ("full_name", "id_document", "user", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("full_name", "id_document", "user__username")
