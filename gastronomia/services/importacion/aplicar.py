"""Paso 2 de la importacion: guardar las ventas confirmadas en la vista previa."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app import db
from app.models.caja import Caja
from app.utils.helpers import today_local
from gastronomia.importacion_models import GastronomiaImportacion, GastronomiaImportacionRegistro
from gastronomia.services.importacion.analisis import (
    alias_aprendidos,
    filas_de_lectura,
    leer_archivo,
    productos_menu,
)
from gastronomia.services.importacion.dias import resolver_dias
from gastronomia.services.importacion.productos_destino import ResolutorProductos, recordar_alias
from gastronomia.services.importacion.productos_match import agrupar_alias, analizar_nombre, clave_alias
from gastronomia.services.importacion.venta_historica import (
    HORA_PRIMERA_VENTA,
    abrir_sesion_historica,
    cerrar_sesion_historica,
    crear_venta_historica,
    metodo_efectivo,
    utc_desde_local,
)


MINUTOS_ENTRE_VENTAS = 2


def aplicar_importacion(cliente_id: int, usuario_id: int, payload: dict) -> dict:
    token = str(payload.get('token') or '')
    lectura = leer_archivo(token)
    if not payload.get('forzar') and GastronomiaImportacion.query.filter_by(
        cliente_id=int(cliente_id), hash_archivo=token, estado='aplicada',
    ).first():
        raise ValueError('Este mismo archivo ya fue importado. Deshace esa importacion antes de volver a cargarlo.')

    dias_por_bloque = _dias_confirmados(lectura, payload.get('dias') or [])
    if not dias_por_bloque:
        raise ValueError('No hay dias seleccionados para importar.')

    filas = filas_de_lectura(lectura)
    grupos_defecto = agrupar_alias(filas, productos_menu(cliente_id), alias_aprendidos(cliente_id))
    grupos, alias_a_clave = _decisiones(grupos_defecto, payload)
    resolutor = ResolutorProductos(cliente_id, grupos, _int_o_none(payload.get('categoria_id')))
    caja = Caja.query.filter_by(activa=True).order_by(Caja.id_caja.asc()).first()
    if not caja:
        raise ValueError('No hay una caja activa para registrar las ventas historicas.')

    importacion = GastronomiaImportacion(
        cliente_id=int(cliente_id),
        usuario_id=int(usuario_id),
        nombre_archivo=(payload.get('nombre_archivo') or '')[:255] or None,
        hash_archivo=token,
        estado='aplicada',
    )
    db.session.add(importacion)
    db.session.flush()

    try:
        resumen = _crear_ventas(importacion, cliente_id, usuario_id, caja, lectura, filas, dias_por_bloque,
                                alias_a_clave, resolutor)
        recordar_alias(cliente_id, alias_a_clave, resolutor)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {**importacion.to_dict(), 'productos_creados': resolutor.creados, **resumen}


def _crear_ventas(importacion, cliente_id, usuario_id, caja, lectura, filas, dias_por_bloque,
                  alias_a_clave, resolutor) -> dict:
    metodo = metodo_efectivo()
    filas_por_fecha: dict[date, list[dict]] = defaultdict(list)
    for fila in filas:
        if fila['bloque'] in dias_por_bloque and fila['monto'] is not None and fila['monto'] > 0:
            filas_por_fecha[dias_por_bloque[fila['bloque']]].append(fila)

    sesiones, pedidos, total = [], 0, Decimal('0.00')
    for dia in sorted(filas_por_fecha):
        etiqueta = f'Importacion historica #{importacion.id_importacion}'
        if importacion.nombre_archivo:
            etiqueta += f' ({importacion.nombre_archivo})'
        sesion = abrir_sesion_historica(caja.id_caja, usuario_id, dia, etiqueta)
        total_dia = Decimal('0.00')
        for orden, fila in enumerate(filas_por_fecha[dia]):
            clave = alias_a_clave.get(clave_alias(fila['nombre']))
            producto = resolutor.producto_para(clave)
            bloque = lectura.bloques[fila['bloque']]
            pedido, venta = crear_venta_historica(
                cliente_id=cliente_id,
                usuario_id=usuario_id,
                sesion=sesion,
                metodo=metodo,
                producto=producto,
                fila=fila,
                fecha=utc_desde_local(dia, HORA_PRIMERA_VENTA, orden * MINUTOS_ENTRE_VENTAS),
                nota_origen=f'Importado de Excel - hoja "{bloque.hoja}", fila {fila["fila"]}: {fila["nombre"]}',
                nota_item=_nota_item(fila['nombre']),
            )
            db.session.add(GastronomiaImportacionRegistro(
                importacion_id=importacion.id_importacion,
                pedido_id=pedido.id_pedido,
                venta_id=venta.id_venta,
            ))
            total_dia += Decimal(str(venta.total))
            pedidos += 1
        cerrar_sesion_historica(sesion, total_dia)
        sesiones.append(sesion.id_sesion)
        total += total_dia

    fechas = sorted(filas_por_fecha)
    importacion.sesiones_ids = sesiones
    importacion.dias = len(fechas)
    importacion.pedidos = pedidos
    importacion.total = total
    importacion.fecha_desde = fechas[0] if fechas else None
    importacion.fecha_hasta = fechas[-1] if fechas else None
    return {'sesiones': len(sesiones)}


def _dias_confirmados(lectura, dias_payload: list[dict]) -> dict[int, date]:
    """indice de bloque -> fecha elegida. Sin payload usa las fechas deducidas."""
    deducidos = {dia['indice']: dia['fecha'] for dia in resolver_dias(lectura.bloques, lectura.totales_diarios)[0]}
    elegidos = {int(item.get('indice')): item for item in dias_payload if item.get('indice') is not None}
    hoy = today_local()
    resultado = {}
    for indice in range(len(lectura.bloques)):
        decision = elegidos.get(indice, {})
        if decision and not decision.get('incluir', True):
            continue
        texto = decision.get('fecha') or deducidos.get(indice)
        if not texto:
            raise ValueError(f'Falta la fecha del bloque que empieza en la fila {lectura.bloques[indice].fila_inicio}.')
        try:
            fecha = date.fromisoformat(str(texto))
        except ValueError as exc:
            raise ValueError(f'Fecha invalida: {texto}') from exc
        if fecha > hoy:
            raise ValueError(f'La fecha {fecha.strftime("%d/%m/%Y")} es futura.')
        resultado[indice] = fecha
    return resultado


def _decisiones(grupos_defecto: list[dict], payload: dict) -> tuple[dict[str, dict], dict[str, str]]:
    grupos = {grupo['clave']: dict(grupo) for grupo in grupos_defecto}
    alias_a_clave = {alias['alias']: grupo['clave'] for grupo in grupos_defecto for alias in grupo['alias']}
    for decision in payload.get('grupos') or []:
        clave = str(decision.get('clave') or '')
        if not clave:
            continue
        grupo = grupos.setdefault(clave, {'clave': clave, 'alias': []})
        accion = decision.get('accion')
        if accion in {'crear', 'existente', 'varios'}:
            grupo['accion'] = accion
        for campo in ('nombre', 'precio', 'producto_id'):
            if decision.get(campo) not in (None, ''):
                grupo[campo] = decision[campo]
    for alias, clave in (payload.get('alias') or {}).items():
        if alias in alias_a_clave and clave in grupos:
            alias_a_clave[alias] = clave
    return grupos, alias_a_clave


def _nota_item(nombre: str) -> str:
    return analizar_nombre(nombre).get('extras') or ''


def _int_o_none(valor) -> int | None:
    try:
        return int(valor) if valor not in (None, '') else None
    except (TypeError, ValueError):
        return None
