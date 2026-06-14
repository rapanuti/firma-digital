"""Utilidades para documentos: hash SHA-256 y metadatos de PDF."""

import hashlib

import fitz  # PyMuPDF


def sha256_of(fileobj) -> str:
    """Calcula el SHA-256 de un archivo (en streaming) y rebobina el puntero."""
    fileobj.seek(0)
    h = hashlib.sha256()
    for chunk in iter(lambda: fileobj.read(8192), b""):
        h.update(chunk)
    fileobj.seek(0)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    """Calcula el SHA-256 de un bloque de bytes (p.ej. el PDF firmado en memoria)."""
    return hashlib.sha256(data).hexdigest()


def pdf_page_count(fileobj) -> int:
    """Número de páginas de un PDF (sin alterar el puntero del archivo)."""
    fileobj.seek(0)
    data = fileobj.read()
    fileobj.seek(0)
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return doc.page_count
    finally:
        doc.close()
