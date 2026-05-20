import importlib
import os
import platform
from pathlib import Path


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
