from app.models import Caja, Cliente, CuentaPorCobrar, GastoCorriente, Producto, Venta
from app.services.ia_backoffice.cobranzas_tools import cobranzas_resumen
from app.services.ia_backoffice.drilldown_shared import (
    _comparacion,
    _hallazgo,
    _money,
    _puede_ver_caja,
    _puede_ver_clientes,
    _puede_ver_cobranzas,
    _puede_ver_gastos,
    _puede_ver_inventario,
    _puede_ver_ventas,
)
from app.services.ia_backoffice.inventario_tools import inventario_resumen
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.services.ia_backoffice.ventas_tools import ventas_ganancia_periodo, ventas_resumen_periodo


def comparar_periodos_negocio(args: dict | None = None, usuario=None) -> dict:
    data = args or {}
    actual_args = {'periodo': data.get('periodo_actual') or data.get('periodo') or 'mes'}
    if data.get('desde_actual') or data.get('hasta_actual'):
        actual_args.update({
            'periodo': 'custom',
            'desde': data.get('desde_actual'),
            'hasta': data.get('hasta_actual'),
        })
    rango_actual = resolver_rango(actual_args)
    if data.get('desde_anterior') or data.get('hasta_anterior'):
        anterior_args = {
            'periodo': 'custom',
            'desde': data.get('desde_anterior'),
            'hasta': data.get('hasta_anterior'),
        }
    elif data.get('periodo_anterior'):
        anterior_args = {'periodo': data.get('periodo_anterior')}
    else:
        anterior_args = {
            'periodo': 'custom',
            'desde': rango_actual['anterior_desde'].isoformat(),
            'hasta': rango_actual['anterior_hasta'].isoformat(),
        }
    rango_anterior = resolver_rango(anterior_args)
    resultado = {
        'periodo_actual': rango_actual['periodo_label'],
        'periodo_anterior': rango_anterior['periodo_label'],
        'comparaciones': {},
    }

    if _puede_ver_ventas(usuario):
        ventas_actual = ventas_resumen_periodo(actual_args, usuario)
        ventas_anterior = ventas_resumen_periodo(anterior_args, usuario)
        margen_actual = ventas_ganancia_periodo(actual_args, usuario)
        margen_anterior = ventas_ganancia_periodo(anterior_args, usuario)
        resultado['comparaciones']['ventas'] = {
            'ventas_totales': _comparacion(ventas_actual.get('total_ventas'), ventas_anterior.get('total_ventas')),
            'cantidad_ventas': _comparacion(ventas_actual.get('cantidad_ventas'), ventas_anterior.get('cantidad_ventas')),
            'ticket_promedio': _comparacion(ventas_actual.get('ticket_promedio'), ventas_anterior.get('ticket_promedio')),
            'ganancia_estimada': _comparacion(margen_actual.get('ganancia_bruta_estimada'), margen_anterior.get('ganancia_bruta_estimada')),
            'margen_pct': _comparacion(margen_actual.get('margen_bruto_pct'), margen_anterior.get('margen_bruto_pct')),
        }

    if _puede_ver_cobranzas(usuario):
        cob_actual = cobranzas_resumen(actual_args, usuario)
        cob_anterior = cobranzas_resumen(anterior_args, usuario)
        resultado['comparaciones']['cobranzas'] = {
            'cobrado_total': _comparacion(cob_actual.get('total_cobrado'), cob_anterior.get('total_cobrado')),
            'cantidad_pagos': _comparacion(cob_actual.get('cantidad_pagos'), cob_anterior.get('cantidad_pagos')),
            'promedio_pago': _comparacion(cob_actual.get('promedio_pago'), cob_anterior.get('promedio_pago')),
        }

    if _puede_ver_inventario(usuario):
        inv_actual = inventario_resumen(actual_args, usuario)
        inv_anterior = inventario_resumen(anterior_args, usuario)
        resultado['comparaciones']['inventario'] = {
            'stock_total': _comparacion(inv_actual.get('stock_total'), inv_anterior.get('stock_total')),
            'valor_stock': _comparacion(inv_actual.get('valor_stock_estimado'), inv_anterior.get('valor_stock_estimado')),
            'productos_stock_bajo': _comparacion(inv_actual.get('productos_stock_bajo'), inv_anterior.get('productos_stock_bajo')),
            'productos_sin_stock': _comparacion(inv_actual.get('productos_sin_stock'), inv_anterior.get('productos_sin_stock')),
        }

    return resultado


def hallazgos_operativos_priorizados(args: dict | None = None, usuario=None) -> dict:
    data = args or {}
    rango = resolver_rango({'periodo': data.get('periodo') or '30d', 'desde': data.get('desde'), 'hasta': data.get('hasta')})
    top_n = normalizar_top_n(data.get('top_n'), default=7, maximo=15)
    hallazgos = []

    if _puede_ver_inventario(usuario):
        productos_stock_bajo = (
            Producto.query
            .filter(Producto.activo.is_(True), Producto.stock_actual <= Producto.stock_minimo)
            .order_by(Producto.stock_actual.asc(), Producto.nombre.asc())
            .limit(top_n)
            .all()
        )
        for producto in productos_stock_bajo:
            hallazgos.append(
                _hallazgo(
                    'alta',
                    'inventario',
                    'Producto con stock bajo',
                    f'{producto.nombre} tiene stock {int(producto.stock_actual or 0)} y minimo {int(producto.stock_minimo or 0)}.',
                    {
                        'id_producto': int(producto.id_producto),
                        'codigo': producto.codigo,
                        'stock_actual': int(producto.stock_actual or 0),
                        'stock_minimo': int(producto.stock_minimo or 0),
                    },
                    'Revisar reposicion o traslado urgente.',
                )
            )

    if _puede_ver_cobranzas(usuario):
        morosos = (
            CuentaPorCobrar.query
            .join(Cliente, Cliente.id_cliente == CuentaPorCobrar.id_cliente)
            .filter(CuentaPorCobrar.saldo_pendiente > 0)
            .order_by(CuentaPorCobrar.saldo_pendiente.desc(), CuentaPorCobrar.fecha_vencimiento.asc())
            .limit(top_n)
            .all()
        )
        for cuenta in morosos:
            hallazgos.append(
                _hallazgo(
                    'alta' if _money(cuenta.saldo_pendiente) >= 500000 else 'media',
                    'cobranzas',
                    'Cuenta por cobrar pendiente',
                    f'{cuenta.cliente.nombre if cuenta.cliente else "Cliente"} debe {_money(cuenta.saldo_pendiente)}.',
                    {
                        'id_cuenta_cobrar': int(cuenta.id_cuenta_cobrar),
                        'id_cliente': int(cuenta.id_cliente),
                        'cliente': cuenta.cliente.nombre if cuenta.cliente else '',
                        'saldo_pendiente': _money(cuenta.saldo_pendiente),
                        'fecha_vencimiento': cuenta.fecha_vencimiento.isoformat() if cuenta.fecha_vencimiento else None,
                    },
                    'Priorizar gestion de cobro y confirmar compromiso de pago.',
                )
            )

    if _puede_ver_ventas(usuario):
        ventas = ventas_resumen_periodo({'periodo': data.get('periodo') or '30d', 'desde': data.get('desde'), 'hasta': data.get('hasta')}, usuario)
        if _money(ventas.get('total_ventas')) <= 0:
            hallazgos.append(
                _hallazgo(
                    'alta',
                    'ventas',
                    'Sin ventas en el periodo',
                    f'No se registran ventas en {rango["periodo_label"]}.',
                    {'periodo': rango['periodo_label']},
                    'Revisar demanda, operacion comercial y disponibilidad de stock.',
                )
            )

    if _puede_ver_gastos(usuario):
        gastos_periodo = (
            GastoCorriente.query
            .filter(
                GastoCorriente.fecha_gasto >= rango['desde'],
                GastoCorriente.fecha_gasto <= rango['hasta'],
            )
            .all()
        )
        total_gastos = sum(_money(item.monto) for item in gastos_periodo)
        if total_gastos > 0 and _puede_ver_ventas(usuario):
            ventas = ventas_resumen_periodo({'periodo': data.get('periodo') or '30d', 'desde': data.get('desde'), 'hasta': data.get('hasta')}, usuario)
            ventas_totales = _money(ventas.get('total_ventas'))
            ratio = round((total_gastos / ventas_totales) * 100, 2) if ventas_totales else None
            if ratio is None or ratio >= 35:
                hallazgos.append(
                    _hallazgo(
                        'media',
                        'gastos',
                        'Gastos corrientes altos',
                        f'Los gastos suman {_money(total_gastos)} en {rango["periodo_label"]}.',
                        {'total_gastos': _money(total_gastos), 'ratio_vs_ventas_pct': ratio},
                        'Auditar gastos fijos y variables con mayor impacto.',
                    )
                )

    if _puede_ver_clientes(usuario):
        clientes_inactivos = (
            Cliente.query
            .filter(Cliente.activo.is_(True))
            .order_by(Cliente.fecha_ultima_compra.asc().nullsfirst(), Cliente.nombre.asc())
            .limit(top_n)
            .all()
        )
        for cliente in clientes_inactivos[:3]:
            if cliente.fecha_ultima_compra is None:
                continue
            hallazgos.append(
                _hallazgo(
                    'baja',
                    'clientes',
                    'Cliente sin compra reciente',
                    f'{cliente.nombre} no compra desde {cliente.fecha_ultima_compra.isoformat()}.',
                    {
                        'id_cliente': int(cliente.id_cliente),
                        'cliente': cliente.nombre,
                        'fecha_ultima_compra': cliente.fecha_ultima_compra.isoformat(),
                    },
                    'Evaluar accion de reactivacion o seguimiento comercial.',
                )
            )

    if _puede_ver_caja(usuario):
        cajas_abiertas = Caja.query.filter(Caja.abierta.is_(True)).count()
        if cajas_abiertas > 1:
            hallazgos.append(
                _hallazgo(
                    'media',
                    'caja',
                    'Multiples cajas abiertas',
                    f'Hay {int(cajas_abiertas)} cajas abiertas simultaneamente.',
                    {'cajas_abiertas': int(cajas_abiertas)},
                    'Verificar si todas requieren seguir operativas o corresponde cierre.',
                )
            )

    hallazgos_ordenados = sorted(hallazgos, key=lambda item: (-item['score'], item['area'], item['titulo']))
    return {
        'periodo_analisis': rango['periodo_label'],
        'cantidad_hallazgos': len(hallazgos_ordenados),
        'hallazgos': hallazgos_ordenados[:top_n],
    }
