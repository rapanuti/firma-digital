"""Fixtures compartidas para los tests (PNG de firma y PDF de prueba)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture(autouse=True)
def _media_temporal(settings, tmp_path):
    """Aísla los archivos subidos en cada test a un directorio temporal."""
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def png_firma():
    """PNG pequeño con fondo transparente, simulando una firma manuscrita."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (300, 120), (0, 0, 0, 0)).save(buf, "PNG")
    return SimpleUploadedFile("firma.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def pdf_carta_bytes():
    """Bytes de un PDF de una página tamaño Carta (612x792 pt)."""
    import fitz

    doc = fitz.open()
    doc.new_page(width=612, height=792)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_carta(pdf_carta_bytes):
    """PDF Carta como archivo subido."""
    return SimpleUploadedFile(
        "documento.pdf", pdf_carta_bytes, content_type="application/pdf"
    )
