"""Utilidades de la verificación pública."""


def mask_id_document(value: str) -> str:
    """Enmascara el documento dejando visibles solo los últimos 4 dígitos.

    Ej.: 'V-12345678' -> 'V-****5678' · '12345678' -> '****5678'
    """
    if not value:
        return ""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) <= 4:
        return value  # demasiado corto para enmascarar de forma útil
    prefix = ""
    if "-" in value:
        prefix = value.split("-", 1)[0] + "-"
    return f"{prefix}****{digits[-4:]}"
