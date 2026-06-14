"""Conversión de coordenadas normalizadas (visor web) → rectángulo de PyMuPDF.

PDF.js y PyMuPDF comparten el MISMO sistema de coordenadas de página:
origen arriba-izquierda, eje Y hacia abajo, y ambos muestran la página en su
orientación visible (con la rotación /Rotate ya aplicada).

Por eso, si en el cliente guardamos el bloque de firma como fracciones (0..1) del
recuadro visible de la página, la conversión a puntos PDF es directa: basta
multiplicar por el ancho/alto visible (``page.rect``), que ya refleja la rotación.
No hace falta voltear el eje Y ni aplicar matrices de rotación manualmente; PyMuPDF
se encarga al insertar imágenes/texto sobre una página rotada.
"""

import fitz  # PyMuPDF


def fractions_to_rect(page, fx, fy, fw, fh) -> "fitz.Rect":
    """Convierte fracciones (0..1, origen arriba-izq) a un ``fitz.Rect`` en puntos.

    :param page: página de PyMuPDF (``fitz.Page``)
    :param fx, fy: esquina superior-izquierda del bloque, como fracción
    :param fw, fh: ancho y alto del bloque, como fracción
    """
    pr = page.rect  # rectángulo visible; ya incluye la rotación de la página
    x0 = fx * pr.width
    y0 = fy * pr.height
    x1 = x0 + fw * pr.width
    y1 = y0 + fh * pr.height
    return fitz.Rect(x0, y0, x1, y1)
