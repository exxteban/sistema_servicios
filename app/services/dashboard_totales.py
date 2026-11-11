"""Totales del inicio: lo cobrado en un rango y la comparacion contra ayer.

Portado del sistema del taller. La comparacion es contra ayer HASTA LA MISMA HORA,
no contra el dia entero: a las 10 de la manana, comparar contra todo ayer daria
siempre "menos que ayer" aunque el dia venga mejor.

En servicios solo se muestra a quien ve todas las cajas: un cajero ve lo de su
sesion abierta, y "su sesion de ayer" no existe, asi que compararia contra cero.
Los textos y la ventana de ayer estan en app/services/comparacion_ayer.py.
"""
from app import db
from app.models import PagoCuentaCobrar, PagoVenta, PedidoClientePago, Venta
from app.services.comparacion_ayer import (
    tendencia,
    texto_diferencia_monto,
    texto_diferencia_ventas,
    ventana_ayer_misma_hora,
)
from app.utils.helpers import utc_bounds_for_local_dates


def filtrar_por_sesion(query, *, puede_ver_otras_cajas, sesion_caja, columna_id_sesion):
    if puede_ver_otras_cajas:
        return query
    if sesion_caja:
        return query.filter(columna_id_sesion == sesion_caja.id_sesion)
    return query.filter(False)


def totales_cobrados(start_date, end_date, *, puede_ver_otras_cajas, sesion_caja):
    start_utc, end_utc = utc_bounds_for_local_dates(start_date, end_date)
    return totales_cobrados_entre(
        start_utc, end_utc, puede_ver_otras_cajas=puede_ver_otras_cajas, sesion_caja=sesion_caja,
    )


def totales_cobrados_entre(start_utc, end_utc, *, puede_ver_otras_cajas, sesion_caja):
    def scope(query, columna):
        return filtrar_por_sesion(
            query, puede_ver_otras_cajas=puede_ver_otras_cajas,
            sesion_caja=sesion_caja, columna_id_sesion=columna,
        )

    cobros_ventas_q = (
        db.session.query(db.func.sum(PagoVenta.monto))
        .join(Venta, PagoVenta.id_venta == Venta.id_venta)
        .filter(
            Venta.estado == 'completada',
            Venta.fecha_venta >= start_utc,
            Venta.fecha_venta < end_utc,
        )
    )
    cobrado_en_ventas = float(scope(cobros_ventas_q, Venta.id_sesion_caja).scalar() or 0)

    cobros_creditos_q = db.session.query(db.func.sum(PagoCuentaCobrar.monto)).filter(
        PagoCuentaCobrar.estado != 'anulado',
        PagoCuentaCobrar.fecha_pago >= start_utc,
        PagoCuentaCobrar.fecha_pago < end_utc,
    )
    cobrado_en_creditos = float(scope(cobros_creditos_q, PagoCuentaCobrar.id_sesion_caja).scalar() or 0)

    cobros_pedidos_q = db.session.query(db.func.sum(PedidoClientePago.monto)).filter(
        PedidoClientePago.estado == 'activo',
        PedidoClientePago.fecha_pago >= start_utc,
        PedidoClientePago.fecha_pago < end_utc,
    )
    cobrado_en_pedidos = float(scope(cobros_pedidos_q, PedidoClientePago.id_sesion_caja).scalar() or 0)

    return {
        'total_cobrado': cobrado_en_ventas + cobrado_en_creditos + cobrado_en_pedidos,
        'cobrado_en_ventas': cobrado_en_ventas,
        'cobrado_en_creditos': cobrado_en_creditos,
        'cobrado_en_pedidos': cobrado_en_pedidos,
    }


def contar_ventas_entre(start_utc, end_utc):
    return Venta.query.filter(
        Venta.estado == 'completada',
        Venta.fecha_venta >= start_utc,
        Venta.fecha_venta < end_utc,
    ).count()


def comparacion_vs_ayer(*, ventas_hoy, total_cobrado_hoy, puede_ver_otras_cajas, ahora_utc=None):
    """Textos "vs ayer" de las tarjetas. Vacio = la tarjeta muestra su subtitulo de siempre.

    `ventas_hoy` / `total_cobrado_hoy` en None significan que el usuario no ve ese
    numero (o que el rango elegido no es "hoy"), y entonces no se compara.
    """
    resultado = {
        'ventas_hoy_comparacion': '',
        'cobrado_hoy_comparacion': '',
        'cobrado_hoy_tendencia': '',
    }
    if not puede_ver_otras_cajas:
        return resultado
    inicio, fin = ventana_ayer_misma_hora(ahora_utc)
    if ventas_hoy is not None:
        resultado['ventas_hoy_comparacion'] = texto_diferencia_ventas(
            ventas_hoy, contar_ventas_entre(inicio, fin),
        )
    if total_cobrado_hoy is not None:
        ayer = totales_cobrados_entre(inicio, fin, puede_ver_otras_cajas=True, sesion_caja=None)
        resultado['cobrado_hoy_comparacion'] = texto_diferencia_monto(total_cobrado_hoy, ayer['total_cobrado'])
        resultado['cobrado_hoy_tendencia'] = tendencia(total_cobrado_hoy, ayer['total_cobrado'])
    return resultado
