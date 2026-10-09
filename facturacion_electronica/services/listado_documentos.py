"""Listado de documentos electrónicos emitidos: la pantalla "Facturas electrónicas".

Una tabla por período con el número, la venta, el cliente, el total y el
estado de cada factura y nota de crédito, pensada para revisar qué salió, qué
quedó trabado y para pasarle el detalle al contador (CSV).

La fecha que manda es la fiscal (`dFeEmiDE`): la de la venta para la factura y
la de generación para la nota de crédito, igual que `emision_service.fecha_emision`.
Una venta facturada al día siguiente figura en el día de la venta.
"""
import csv
import io

from sqlalchemy import case, func
from sqlalchemy.orm import joinedload

from app.models import Venta
from app.models.devolucion import Devolucion
from app.utils.helpers import utc_bounds_for_local_dates, utc_naive_to_local
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_INUTILIZADO,
    ESTADO_RECHAZADO,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico

POR_PAGINA = 50

# Filtro de estado de la pantalla → estados guardados. "Sin enviar" agrupa lo
# que todavía no tiene respuesta de SIFEN.
FILTROS_ESTADO = {
    'aprobado': (ESTADO_APROBADO,),
    'sin_enviar': (ESTADO_GENERADO, ESTADO_FIRMADO, ESTADO_ENVIADO),
    'rechazado': (ESTADO_RECHAZADO,),
    'error': (ESTADO_ERROR,),
    'cancelado': (ESTADO_CANCELADO,),
    'inutilizado': (ESTADO_INUTILIZADO,),
}
ETIQUETAS_FILTRO = (
    ('', 'Todos'),
    ('aprobado', 'Aprobados'),
    ('sin_enviar', 'Sin respuesta de SIFEN'),
    ('rechazado', 'Rechazados'),
    ('error', 'Con error'),
    ('cancelado', 'Cancelados'),
    ('inutilizado', 'Inutilizados'),
)
# Los que alguien tiene que mirar: SIFEN no los aceptó o no llegaron.
ESTADOS_ATENCION = (ESTADO_RECHAZADO, ESTADO_ERROR)


def _fecha_fiscal():
    """Expresión SQL de la fecha de emisión: la venta, o la generación en la NC."""
    return case(
        (DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO,
         func.coalesce(DocumentoElectronico.fecha_generado, DocumentoElectronico.created_at)),
        else_=func.coalesce(Venta.fecha_venta, DocumentoElectronico.created_at),
    )


def _consulta(desde, hasta, estado='', tipo=''):
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)
    fecha = _fecha_fiscal()
    consulta = (
        DocumentoElectronico.query
        .join(Venta, Venta.id_venta == DocumentoElectronico.id_venta)
        .filter(fecha >= inicio, fecha < fin)
    )
    if estado in FILTROS_ESTADO:
        consulta = consulta.filter(DocumentoElectronico.estado.in_(FILTROS_ESTADO[estado]))
    if tipo == 'factura':
        consulta = consulta.filter(func.coalesce(DocumentoElectronico.tipo_documento, 1) == 1)
    elif tipo == 'nota_credito':
        consulta = consulta.filter(DocumentoElectronico.tipo_documento == TIPO_NOTA_CREDITO)
    return consulta, fecha


def _totales_nc(documentos):
    """Total de cada NC de devolución: lo devuelto, no la venta entera."""
    ids = [d.id_devolucion for d in documentos if d.es_nota_credito and d.id_devolucion]
    if not ids:
        return {}
    filas = Devolucion.query.with_entities(Devolucion.id_devolucion, Devolucion.monto_total) \
        .filter(Devolucion.id_devolucion.in_(ids)).all()
    return {id_dev: float(monto or 0) for id_dev, monto in filas}


def _fila(documento, totales_nc):
    venta = documento.venta
    cliente = getattr(venta, 'cliente', None)
    if documento.es_nota_credito:
        fecha = documento.fecha_generado or documento.created_at
        total = totales_nc.get(documento.id_devolucion, float(getattr(venta, 'total', 0) or 0))
    else:
        fecha = getattr(venta, 'fecha_venta', None) or documento.created_at
        total = float(getattr(venta, 'total', 0) or 0)
    return {
        'documento': documento,
        'id_venta': documento.id_venta,
        'tipo': 'Nota de crédito' if documento.es_nota_credito else 'Factura',
        'numero': documento.numero_formateado if documento.numero else '—',
        'fecha': utc_naive_to_local(fecha) if fecha else None,
        'cliente': (getattr(cliente, 'nombre', '') or '').strip() or '—',
        'ruc_ci': (getattr(cliente, 'ruc_ci', '') or '').strip() or '—',
        'total': total,
        'estado': documento.estado,
        'ambiente': documento.ambiente or '',
        'mensaje': (documento.respuesta_mensaje or '').strip(),
        'protocolo': documento.protocolo_autorizacion or '',
        'cdc': documento.cdc or '',
        'atencion': documento.estado in ESTADOS_ATENCION,
    }


def _resumen(desde, hasta, tipo):
    """Cantidad por estado del período (sin el filtro de estado) y el monto aprobado."""
    consulta, _fecha = _consulta(desde, hasta, tipo=tipo)
    por_estado = dict(
        consulta.with_entities(DocumentoElectronico.estado, func.count(DocumentoElectronico.id))
        .group_by(DocumentoElectronico.estado).all()
    )
    facturado = consulta.filter(
        DocumentoElectronico.estado == ESTADO_APROBADO,
        func.coalesce(DocumentoElectronico.tipo_documento, 1) == 1,
    ).with_entities(func.coalesce(func.sum(Venta.total), 0)).scalar()
    return {
        'por_estado': por_estado,
        'total': sum(por_estado.values()),
        'facturado_aprobado': float(facturado or 0),
        'atencion': sum(por_estado.get(e, 0) for e in ESTADOS_ATENCION),
        'sin_enviar': sum(por_estado.get(e, 0) for e in FILTROS_ESTADO['sin_enviar']),
    }


def listar_documentos(desde, hasta, estado='', tipo='', pagina=1):
    """Página del listado más el resumen del período. Más nuevos primero."""
    consulta, fecha = _consulta(desde, hasta, estado, tipo)
    cantidad = consulta.count()
    pagina = max(1, int(pagina or 1))
    documentos = (
        consulta.options(joinedload(DocumentoElectronico.venta).joinedload(Venta.cliente))
        .order_by(fecha.desc(), DocumentoElectronico.id.desc())
        .offset((pagina - 1) * POR_PAGINA).limit(POR_PAGINA).all()
    )
    totales_nc = _totales_nc(documentos)
    return {
        'filas': [_fila(d, totales_nc) for d in documentos],
        'cantidad': cantidad,
        'pagina': pagina,
        'paginas': max(1, -(-cantidad // POR_PAGINA)),
        'resumen': _resumen(desde, hasta, tipo),
    }


def csv_documentos(desde, hasta, estado='', tipo=''):
    """El mismo listado, completo, como CSV (separador `;`, lo que abre Excel en es-PY)."""
    consulta, fecha = _consulta(desde, hasta, estado, tipo)
    documentos = (
        consulta.options(joinedload(DocumentoElectronico.venta).joinedload(Venta.cliente))
        .order_by(fecha.asc(), DocumentoElectronico.id.asc()).all()
    )
    totales_nc = _totales_nc(documentos)
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=';')
    escritor.writerow(['Fecha', 'Tipo', 'Número', 'Venta', 'Cliente', 'RUC/CI', 'Total',
                       'Estado', 'Ambiente', 'Protocolo', 'CDC', 'Mensaje'])
    for d in documentos:
        f = _fila(d, totales_nc)
        escritor.writerow([
            f['fecha'].strftime('%d/%m/%Y %H:%M') if f['fecha'] else '',
            f['tipo'], f['numero'], f['id_venta'], f['cliente'], f['ruc_ci'],
            f"{f['total']:.0f}", f['estado'], f['ambiente'], f['protocolo'], f['cdc'],
            f['mensaje'][:200],
        ])
    # BOM: sin él Excel abre el CSV en otra codificación y rompe las tildes.
    return '﻿' + salida.getvalue()


def periodo_por_defecto(hoy):
    """Del 1 del mes a hoy: lo que el contador revisa."""
    return hoy.replace(day=1), hoy


__all__ = [
    'ETIQUETAS_FILTRO',
    'POR_PAGINA',
    'csv_documentos',
    'listar_documentos',
    'periodo_por_defecto',
]
