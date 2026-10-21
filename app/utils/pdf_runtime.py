import importlib
import os
import platform
from pathlib import Path
from io import BytesIO


def is_arm_machine() -> bool:
    return platform.machine().upper() in {'ARM64', 'AARCH64'}


def local_freetype_dir() -> Path:
    return Path(__file__).resolve().parents[2] / '.local-arm' / 'freetype'


def import_pisa():
    if not is_arm_machine():
        return importlib.import_module('xhtml2pdf.pisa')

    dll_dir = local_freetype_dir()
    if not (dll_dir / 'freetype.dll').exists():
        return importlib.import_module('xhtml2pdf.pisa')

    previous_cwd = Path.cwd()
    try:
        os.chdir(dll_dir)
        return importlib.import_module('xhtml2pdf.pisa')
    finally:
        os.chdir(previous_cwd)


def generar_pdf_bytes(html: str) -> bytes | None:
    """Renderiza HTML a bytes PDF. Devuelve None si el entorno ARM no tiene
    soporte de PDF o si la generacion falla; relanza en entornos no-ARM sin pisa."""
    try:
        pisa = import_pisa()
    except Exception:
        if not is_arm_machine():
            raise
        return None

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf_buffer, encoding='UTF-8')
    if pisa_status.err:
        return None
    pdf_buffer.seek(0)
    return pdf_buffer.read()
