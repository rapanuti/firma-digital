"""Composición visual del sello de firma sobre la página del PDF (PyMuPDF).

El sello se dibuja directamente con PyMuPDF usando fuentes integradas (Helvetica),
sin depender de archivos de fuente externos. Layout en dos columnas:

    +-------------------------------+
    | [firma manuscrita]      [QR]  |
    | Firmado electrónicamente por: |
    | NOMBRE                        |
    | C.I.: ...                     |
    | Fecha: ...                    |
    | Código: ...                   |
    +-------------------------------+
"""

import fitz  # PyMuPDF

_BORDER = (0.82, 0.84, 0.88)
_WHITE = (1.0, 1.0, 1.0)
_DARK = (0.10, 0.12, 0.16)
_MUTED = (0.42, 0.47, 0.54)
_BRAND = (0.31, 0.27, 0.90)


def stamp_seal(page, rect, *, signature_png, qr_png, header, name, details, doc_hash=None):
    """Dibuja el sello dentro de ``rect`` (coordenadas de página PyMuPDF).

    Si se pasa ``doc_hash`` (SHA-256 del documento ORIGINAL), se añade como texto
    visible bajo los datos. Se usa el hash del original porque es estable: el hash
    del PDF firmado no puede imprimirse dentro de sí mismo (cambiaría sus bytes).
    """
    # Tarjeta blanca con borde, para legibilidad sobre cualquier contenido.
    page.draw_rect(rect, color=_BORDER, fill=_WHITE, width=0.8)
    # Acento de marca en el borde izquierdo.
    accent = fitz.Rect(rect.x0, rect.y0, rect.x0 + max(2.0, rect.width * 0.012), rect.y1)
    page.draw_rect(accent, color=_BRAND, fill=_BRAND, width=0)

    pad = max(4.0, min(rect.width, rect.height) * 0.06)
    inner = fitz.Rect(rect.x0 + pad * 1.6, rect.y0 + pad, rect.x1 - pad, rect.y1 - pad)

    # QR a la derecha, cuadrado y centrado verticalmente.
    qr_side = max(1.0, min(inner.height, inner.width * 0.30))
    qr_rect = fitz.Rect(
        inner.x1 - qr_side,
        inner.y0 + (inner.height - qr_side) / 2,
        inner.x1,
        inner.y0 + (inner.height + qr_side) / 2,
    )
    page.insert_image(qr_rect, stream=qr_png, keep_proportion=True)

    # Columna izquierda: firma arriba, texto abajo. Con hash, la firma ocupa
    # menos para dejar sitio al texto.
    left = fitz.Rect(inner.x0, inner.y0, qr_rect.x0 - pad, inner.y1)
    sig_share = 0.32 if doc_hash else 0.42
    sig_rect = fitz.Rect(left.x0, left.y0, left.x1, left.y0 + left.height * sig_share)
    page.insert_image(sig_rect, stream=signature_png, keep_proportion=True)

    text_rect = fitz.Rect(left.x0, sig_rect.y1 + pad * 0.2, left.x1, left.y1)
    _draw_text(page, text_rect, header, name, details, doc_hash)


def _draw_text(page, rect, header, name, details, doc_hash=None):
    """Apila las líneas de texto del sello dentro de ``rect``.

    Usa ``insert_text`` (coloca cada línea en su baseline, sin recorte por ajuste
    de caja), que es más predecible que ``insert_textbox`` para líneas cortas.
    El hash se parte en varias líneas con fuente monoespaciada para que quepa.
    """
    # Estimación de filas (el hash ocupa etiqueta + ~2 líneas) para el tamaño de fuente.
    rows = 2 + len(details) + (3 if doc_hash else 0)
    fs = max(4.2, min(9.5, rect.height / (rows * 1.45)))
    y = rect.y0

    def line(text, size, color, font="helv"):
        nonlocal y
        page.insert_text(
            (rect.x0, y + size), text, fontname=font, fontsize=size, color=color
        )
        y += size * 1.45

    line(header, fs * 0.85, _MUTED)
    line(name, fs * 1.1, _DARK, font="hebo")
    for d in details:
        line(d, fs * 0.85, _DARK)

    if doc_hash:
        line("SHA-256 (documento original):", fs * 0.78, _MUTED)
        for chunk in _split_hash(doc_hash, rect.width, fs * 0.85):
            line(chunk, fs * 0.85, _DARK, font="cour")


def _split_hash(value, width, fontsize=6.0):
    """Parte el hash en trozos que quepan en ``width`` con fuente Courier."""
    if not value:
        return []
    # Courier: ancho de carácter ≈ 0.6 * fontsize.
    per_line = max(16, int(width / (fontsize * 0.62)))
    return [value[i : i + per_line] for i in range(0, len(value), per_line)]
