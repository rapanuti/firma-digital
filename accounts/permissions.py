"""Utilidades de control de permisos por rol.

- Usuarios anónimos -> redirigidos al login.
- Usuarios autenticados sin rol admin -> 403 (PermissionDenied).
"""

from functools import wraps

from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


class AdminRequiredMixin(AccessMixin):
    """Restringe una vista basada en clase a usuarios con rol administrador."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()  # -> login
        if not request.user.is_admin_role:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


def admin_required(view_func):
    """Decorador equivalente para vistas basadas en función."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not request.user.is_admin_role:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return _wrapped
