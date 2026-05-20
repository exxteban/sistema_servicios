"""
Utilidades para mensajes y sugerencias de errores de productos.
"""
from __future__ import annotations

import re

from app import db
from app.models import Producto


_DUPLICATE_ENTRY_RE = re.compile(r"Duplicate entry '(.+?)' for key '(.+?)'")
_DATA_TOO_LONG_RE = re.compile(r"Data too long for column '(.+?)'")
_MAX_CODIGO_LEN = 50
_PRODUCTO_TEXT_LIMITS = {
    'codigo': ('Codigo', 50),
    'codigo_proveedor': ('Codigo de proveedor', 50),
    'codigo_barras': ('Codigo de barras', 50),
    'nombre': ('Nombre del producto', 200),
    'marca': ('Marca', 100),
    'modelo': ('Modelo', 100),
    'color': ('Color', 50),
    'capacidad': ('Capacidad', 50),
}


def validar_longitudes_producto(campos: dict[str, object]) -> str | None:
    errores = []
    for campo, (etiqueta, maximo) in _PRODUCTO_TEXT_LIMITS.items():
        valor = campos.get(campo)
        if valor is None:
            continue
        largo = len(str(valor))
        if largo > maximo:
            errores.append(f'{etiqueta} permite hasta {maximo} caracteres. Ingresaste {largo}.')
    if not errores:
        return None
    return ' '.join(errores)


def sugerir_codigo_disponible(codigo: str | None) -> str | None:
    base = (codigo or "").strip()
    if not base:
        return None

    if not _codigo_existe(base):
        return base

    base_recortada = base[:_MAX_CODIGO_LEN].rstrip(" -")
    for numero in range(2, 100):
        sufijo = f"-{numero:02d}"
        candidato = f"{base_recortada[:_MAX_CODIGO_LEN - len(sufijo)].rstrip(' -')}{sufijo}"
        if candidato and not _codigo_existe(candidato):
            return candidato

    sufijo = "-ALT"
    candidato = f"{base_recortada[:_MAX_CODIGO_LEN - len(sufijo)].rstrip(' -')}{sufijo}"
    return candidato or None


def mensaje_error_producto(exc: Exception, codigo: str | None = None, codigo_barras: str | None = None) -> str:
    detalle = str(getattr(exc, "orig", exc) or "")
    data_too_long = _DATA_TOO_LONG_RE.search(detalle)
    if data_too_long:
        campo = data_too_long.group(1)
        etiqueta, maximo = _PRODUCTO_TEXT_LIMITS.get(campo, ('El campo', None))
        if maximo:
            return f'El campo {etiqueta} permite hasta {maximo} caracteres. Revisa el dato e intenta de nuevo.'
        return 'Uno de los campos tiene mas caracteres de los permitidos. Revisa los datos e intenta de nuevo.'

    match = _DUPLICATE_ENTRY_RE.search(detalle)
    if not match and "UNIQUE constraint failed" not in detalle:
        return "No se pudo guardar el producto. Verifica los datos e intenta de nuevo."

    if match:
        valor_duplicado, indice = match.groups()
    else:
        valor_duplicado = codigo_barras or codigo or ""
        indice = detalle
    indice = (indice or "").lower()

    if "codigo_barras" in indice:
        return (
            f'El codigo de barras "{valor_duplicado}" ya esta en uso. '
            "Verifica el lector o dejalo vacio si todavia no queres cargarlo."
        )

    codigo_base = codigo or valor_duplicado
    sugerencia = sugerir_codigo_disponible(codigo_base)
    contexto = _contexto_producto_existente(buscar_producto_por_codigo(codigo_base))
    if sugerencia and sugerencia != codigo_base:
        return (
            f'El codigo "{codigo_base}" ya existe{contexto} y debe ser unico. '
            f'Podes probar con "{sugerencia}".'
        )

    return f'El codigo "{codigo_base}" ya existe{contexto} y debe ser unico.'


def mensaje_codigo_duplicado(codigo: str | None) -> str:
    codigo_limpio = (codigo or "").strip()
    sugerencia = sugerir_codigo_disponible(codigo_limpio)
    contexto = _contexto_producto_existente(buscar_producto_por_codigo(codigo_limpio))
    if sugerencia and sugerencia != codigo_limpio:
        return (
            f'El codigo "{codigo_limpio}" ya existe{contexto} y debe ser unico. '
            f'Podes probar con "{sugerencia}".'
        )
    return f'El codigo "{codigo_limpio}" ya existe{contexto} y debe ser unico.'


def buscar_producto_por_codigo(codigo: str | None, excluir_id: int | None = None) -> Producto | None:
    codigo_limpio = (codigo or "").strip()
    if not codigo_limpio:
        return None
    query = Producto.query.filter(db.func.lower(Producto.codigo) == codigo_limpio.lower())
    if excluir_id:
        query = query.filter(Producto.id_producto != excluir_id)
    return query.first()


def _codigo_existe(codigo: str) -> bool:
    return buscar_producto_por_codigo(codigo) is not None


def _contexto_producto_existente(producto: Producto | None) -> str:
    if not producto:
        return ""
    nombre = (producto.nombre or "").strip()
    estado = "activo" if bool(producto.activo) else "inactivo/eliminado"
    if nombre:
        return f' en "{nombre}" ({estado})'
    return f" en un producto {estado}"
