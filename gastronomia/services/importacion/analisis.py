"""Paso 1 de la importacion: leer el Excel y armar la vista previa."""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date

from flask import current_app

from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from gastronomia.importacion_models import GastronomiaImportacion, GastronomiaImportAlias
from gastronomia.models import GastronomiaCategoria, GastronomiaPedidoPago, GastronomiaProducto
from gastronomia.services.importacion.dias import resolver_dias
from gastronomia.services.importacion.excel_lector import LecturaExcel, leer_excel
from gastronomia.services.importacion.productos_match import CLAVE_VARIOS, NOMBRE_VARIOS, agrupar_alias


EXTENSIONES = {'.xlsx', '.xlsm'}
CARPETA = 'importaciones_ventas'


def guardar_archivo(archivo) -> str:
    """Guarda el Excel subido con su hash como nombre; devuelve el token."""
    extension = os.path.splitext(archivo.filename or '')[1].lower()
    if extension not in EXTENSIONES:
        raise ValueError('Subi un archivo de Excel (.xlsx).')
    contenido = archivo.read()
    if not contenido:
        raise ValueError('El archivo esta vacio.')
    token = hashlib.sha256(contenido).hexdigest()
    carpeta = os.path.join(current_app.instance_path, CARPETA)
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, f'{token}.xlsx'), 'wb') as destino:
        destino.write(contenido)
    return token


def ruta_archivo(token: str) -> str:
    if not re.fullmatch(r'[0-9a-f]{64}', token or ''):
        raise ValueError('Archivo de importacion invalido.')
    ruta = os.path.join(current_app.instance_path, CARPETA, f'{token}.xlsx')
    if not os.path.exists(ruta):
        raise ValueError('El archivo ya no esta disponible: volve a subirlo.')
    return ruta


def leer_archivo(token: str) -> LecturaExcel:
    try:
        return leer_excel(ruta_archivo(token))
    except ValueError:
        raise
    except Exception as exc:  # openpyxl lanza varios tipos segun el archivo
        raise ValueError('No se pudo leer el Excel. Revisa que sea un .xlsx valido.') from exc


def filas_de_lectura(lectura: LecturaExcel) -> list[dict]:
    return [
        {'bloque': indice, 'fila': fila.fila, 'nombre': fila.nombre, 'cantidad': fila.cantidad, 'monto': fila.monto}
        for indice, bloque in enumerate(lectura.bloques)
        for fila in bloque.filas
    ]


def analizar(cliente_id: int, token: str, nombre_archivo: str = '') -> dict:
    lectura = leer_archivo(token)
    if not lectura.bloques:
        raise ValueError('No encontre ventas en el Excel. Necesito al menos columnas de producto y monto.')
    dias, sin_detalle = resolver_dias(lectura.bloques, lectura.totales_diarios)
    menu = productos_menu(cliente_id)
    grupos = agrupar_alias(filas_de_lectura(lectura), menu, alias_aprendidos(cliente_id))
    _marcar_dias_con_ventas(cliente_id, dias)
    return {
        'token': token,
        'nombre_archivo': nombre_archivo,
        'hojas': lectura.hojas,
        'dias': dias,
        'totales_sin_detalle': sin_detalle,
        'grupos': grupos,
        'menu': menu,
        'categorias': [
            {'id_categoria': c.id_categoria, 'nombre': c.nombre}
            for c in GastronomiaCategoria.query.filter_by(cliente_id=int(cliente_id), activo=True)
            .order_by(GastronomiaCategoria.orden.asc(), GastronomiaCategoria.nombre.asc()).all()
        ],
        'importacion_previa': _importacion_previa(cliente_id, token),
        'resumen': {
            'dias': len(dias),
            'pedidos': sum(dia['filas'] for dia in dias),
            'total': sum(dia['suma'] for dia in dias),
        },
    }


def productos_menu(cliente_id: int) -> list[dict]:
    productos = (
        GastronomiaProducto.query
        .filter_by(cliente_id=int(cliente_id), activo=True)
        .filter(GastronomiaProducto.nombre != NOMBRE_VARIOS)
        .order_by(GastronomiaProducto.nombre.asc())
        .all()
    )
    return [{'id_producto': p.id_producto, 'nombre': p.nombre, 'precio': float(p.precio or 0)} for p in productos]


def alias_aprendidos(cliente_id: int) -> dict[str, int | str]:
    """alias -> id de producto, o CLAVE_VARIOS si la ultima vez se mando a Varios."""
    filas = (
        GastronomiaImportAlias.query
        .join(GastronomiaProducto, GastronomiaProducto.id_producto == GastronomiaImportAlias.producto_id)
        .filter(GastronomiaImportAlias.cliente_id == int(cliente_id))
        .with_entities(GastronomiaImportAlias.alias, GastronomiaImportAlias.producto_id, GastronomiaProducto.nombre)
        .all()
    )
    return {alias: CLAVE_VARIOS if nombre == NOMBRE_VARIOS else int(producto_id) for alias, producto_id, nombre in filas}


def _importacion_previa(cliente_id: int, token: str) -> dict | None:
    previa = (
        GastronomiaImportacion.query
        .filter_by(cliente_id=int(cliente_id), hash_archivo=token, estado='aplicada')
        .order_by(GastronomiaImportacion.id_importacion.desc())
        .first()
    )
    return previa.to_dict() if previa else None


def _marcar_dias_con_ventas(cliente_id: int, dias: list[dict]) -> None:
    fechas = sorted({date.fromisoformat(dia['fecha']) for dia in dias if dia['fecha']})
    if not fechas:
        return
    inicio, fin = utc_bounds_for_local_dates(fechas[0], fechas[-1])
    pagos = (
        GastronomiaPedidoPago.query
        .filter(
            GastronomiaPedidoPago.cliente_id == int(cliente_id),
            GastronomiaPedidoPago.fecha_pago >= inicio,
            GastronomiaPedidoPago.fecha_pago < fin,
        )
        .with_entities(GastronomiaPedidoPago.fecha_pago)
        .all()
    )
    con_ventas = {utc_naive_to_local(fila.fecha_pago).date().isoformat() for fila in pagos}
    for dia in dias:
        if dia['fecha'] in con_ventas:
            dia['ya_tiene_ventas'] = True
            dia['avisos'].append('El sistema ya tiene ventas en esta fecha: importarlo podria duplicarlas.')
            dia['estado'] = 'revisar'
