"""Cobertura del POS con filtros actuales y tiempos del mismo servicio que atiende el GET."""
from collections import Counter
from datetime import datetime, timedelta
from math import ceil
from statistics import median
from time import perf_counter

from sqlalchemy import case, func

from app import db
from gastronomia.models import GastronomiaPedido as Pedido, GastronomiaProducto as Producto
from gastronomia.sugerencias_models import GastronomiaSugerenciaPedido as Exposicion
from gastronomia.services.channel_price_service import normalizar_canal_precio
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.aprendizaje import pagos_validos
from gastronomia.services.sugerencias.consulta_pos import consultar
from gastronomia.services.sugerencias.pos import config_para_pos


def _tiempos(valores):
    ordenados = sorted(valores)
    if not ordenados:
        return {'minimo_ms': None, 'mediana_ms': None, 'p95_ms': None, 'maximo_ms': None}
    return dict(zip(('minimo_ms', 'mediana_ms', 'p95_ms', 'maximo_ms'), (
        round(ordenados[0], 3), round(median(ordenados), 3),
        round(ordenados[ceil(.95 * len(ordenados)) - 1], 3), round(ordenados[-1], 3),
    )))


def cobertura_registrada(cliente_id, ahora):
    desde = ahora - timedelta(days=C.VENTANA_DIAS)
    pagados = pagos_validos(cliente_id).filter(
        Pedido.origen_pedido == 'pos',
    ).subquery()
    total, expuestos = (db.session.query(
        func.count(func.distinct(pagados.c.pedido_id)),
        func.count(func.distinct(case((Exposicion.id.isnot(None), pagados.c.pedido_id)))),
    ).select_from(pagados).outerjoin(Exposicion,
        (Exposicion.cliente_id == cliente_id) & (Exposicion.pedido_id == pagados.c.pedido_id)
        & (Exposicion.mostrada_en <= ahora),
    ).filter(pagados.c.fecha_pago >= desde, pagados.c.fecha_pago <= ahora).one())
    return {
        'desde_utc': desde.isoformat(), 'hasta_utc': ahora.isoformat(),
        'pedidos_pos_cobrados': total, 'pedidos_con_exposicion': expuestos,
        'porcentaje': round(100 * expuestos / total, 2) if total else None,
        'nota': 'Exposición registrada en pedidos POS cobrados, sin encargos ni ventas anuladas. '
                'El denominador incluye períodos desactivados y usuarios sin franja; no mide calidad ni conversión.',
    }


def medir_pos(cliente_id, frecuencias, *, muestra=20, repeticiones=3, canal_precio=None, ahora=None):
    if not 1 <= muestra <= 100 or not 1 <= repeticiones <= 5:
        raise ValueError('Muestra entre 1 y 100; repeticiones entre 1 y 5.')
    canal = normalizar_canal_precio(canal_precio)
    ahora = ahora or datetime.utcnow()
    # Frecuencias de los mismos tickets válidos que ya leyó el diagnóstico matemático.
    populares = sorted(frecuencias, key=lambda p: (-frecuencias[p], p))
    # Consulta por tramos: un catálogo grande no se convierte en un IN sin límite.
    elegidos = []
    for inicio in range(0, len(populares), 200):
        lote = populares[inicio:inicio + 200]
        productos = {p.id_producto: p for p in Producto.query.filter(
            Producto.cliente_id == cliente_id, Producto.id_producto.in_(lote),
            Producto.activo.is_(True), Producto.disponible.is_(True), Producto.visible.is_(True),
        )}
        for numero in lote:
            p = productos.get(numero)
            if p and (not p.control_stock_venta or (p.stock_disponible or 0) > 0):
                elegidos.append((p.id_producto, p.nombre, frecuencias[numero]))
            if len(elegidos) == muestra:
                break
        if len(elegidos) == muestra:
            break
    config = config_para_pos(cliente_id)
    tiempos, estados, filas, con_sugerencias = [], Counter(), [], 0
    for numero, nombre, pedidos in elegidos:
        duraciones, resultados, estados_producto = [], [], Counter()
        for _ in range(repeticiones):
            inicio = perf_counter()
            try:
                resultado = consultar(cliente_id, [numero], canal_precio=canal)
                cantidad = min(resultado['max'], len(resultado['sugerencias']))
                estado = resultado['estado']
            except Exception as exc:
                db.session.rollback()
                cantidad, estado = 0, f'error:{type(exc).__name__}'
            duracion = (perf_counter() - inicio) * 1000
            duraciones.append(duracion)
            resultados.append(cantidad)
            estados_producto[estado] += 1
            estados[estado] += 1
            con_sugerencias += cantidad > 0
        tiempos.extend(duraciones)
        filas.append({
            'id_producto': numero, 'nombre': nombre, 'pedidos_historial': pedidos,
            'sugerencias_por_consulta': resultados, 'estados': dict(estados_producto), **_tiempos(duraciones),
        })
    return {
        'canal_precio': canal or 'normal', 'configuracion': config,
        'origenes_evaluados': len(filas), 'repeticiones': repeticiones,
        'consultas': len(tiempos), 'consultas_con_sugerencias': con_sugerencias,
        'cobertura_muestra_porcentaje': round(100 * con_sugerencias / len(tiempos), 2) if tiempos else None,
        'estados': dict(estados), **_tiempos(tiempos), 'productos': filas,
        'nota': 'Carritos simulados de un producto: los más pedidos disponibles hoy, '
                'con asociaciones publicadas, stock, reglas, canal, fatiga y configuración actuales. '
                'No reconstruye escaneos ni mide exposición real. Tiempo del servicio compartido con el GET '
                '(configuración y candidatos), sin autenticación, HTTP, red ni renderizado. '
                'El presupuesto cooperativo no interrumpe una consulta SQL bloqueada.',
    }
