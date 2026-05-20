from app.models import Configuracion, MetodoPago
from app.services.clientes_fidelizacion import obtener_beneficios_aplicados_venta
from cobranzas.services.cuotas_service import obtener_plan_credito_vigente

from .parte1 import _resolver_metodo_credito_tienda


def _as_float(value, default=0.0):
    try:
        return float(value or 0)
    except Exception:
        return float(default)


def _nombre_metodo_credito():
    metodo = _resolver_metodo_credito_tienda(MetodoPago.query.all(), solo_activos=False)
    nombre = str(getattr(metodo, 'nombre', '') or '').strip() or 'Credito Tienda'
    return f'{nombre} (financiado)'


def _agregar_pago_resumen(items, nombre, monto, orden=999):
    nombre_norm = str(nombre or '').strip().lower()
    for item in items:
        if str(item.get('nombre') or '').strip().lower() != nombre_norm:
            continue
        item['monto'] = _as_float(item.get('monto')) + _as_float(monto)
        return
    items.append({
        'nombre': nombre,
        'monto': _as_float(monto),
        'referencias': [],
        'orden': int(orden),
    })


def build_sales_ticket_context(
    venta,
    *,
    detalles,
    pagos,
    pagos_resumen,
    preview=False,
    embedded=False,
):
    empresa = {
        'nombre': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or ''
    }

    total_pagado = sum(_as_float(getattr(pago, 'monto', 0)) for pago in (pagos or []))
    total = _as_float(getattr(venta, 'total', 0))
    vuelto = max(0.0, total_pagado - total)
    subtotal = _as_float(getattr(venta, 'subtotal', venta.total))
    descuento = _as_float(getattr(venta, 'descuento_monto', 0))
    descuento_manual = _as_float(getattr(venta, 'descuento_manual_monto', 0))
    descuento_fidelizacion = _as_float(getattr(venta, 'descuento_fidelizacion_monto', 0))
    beneficio_fidelizacion_tipo = str(getattr(venta, 'beneficio_fidelizacion_tipo', '') or '').strip()
    beneficio_fidelizacion_descripcion = str(getattr(venta, 'beneficio_fidelizacion_descripcion', '') or '').strip()
    moneda_simbolo = 'Gs' if not preview else '₲'
    footer_text = Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra'
    paper_width_mm = Configuracion.obtener_int('ticket_paper_width_mm', 58)
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58

    tipo_venta = str(getattr(venta, 'tipo_venta', 'contado') or 'contado').strip().lower() or 'contado'
    cuenta = getattr(venta, 'cuenta_por_cobrar', None)
    monto_financiado = _as_float(getattr(cuenta, 'monto_total', None))
    if monto_financiado <= 0:
        monto_financiado = _as_float(getattr(venta, 'saldo_pendiente', 0))
    es_venta_credito = tipo_venta == 'credito' or monto_financiado > 0

    pagos_resumen_render = [dict(item) for item in (pagos_resumen or [])]
    if es_venta_credito and monto_financiado > 0:
        _agregar_pago_resumen(pagos_resumen_render, _nombre_metodo_credito(), monto_financiado)
    pagos_resumen_render.sort(key=lambda item: (int(item.get('orden', 999)), str(item.get('nombre') or '').lower()))

    resumen_credito_plan = {
        'modo': 'cuenta_corriente',
        'cantidad_cuotas': 0,
        'tasa_interes_pct': 0.0,
        'interes_total': 0.0,
        'total_con_interes': 0.0,
        'cuota_estimada': 0.0,
    }
    if es_venta_credito and cuenta is not None:
        plan_vigente = obtener_plan_credito_vigente(cuenta)
        if plan_vigente is not None:
            cuotas = list(getattr(plan_vigente, 'cuotas', []) or [])
            resumen_credito_plan = {
                'modo': str(getattr(plan_vigente, 'modo', 'cuenta_corriente') or 'cuenta_corriente').strip().lower(),
                'cantidad_cuotas': int(getattr(plan_vigente, 'cantidad_cuotas', 0) or 0),
                'tasa_interes_pct': _as_float(getattr(plan_vigente, 'tasa_periodica_pct', 0)),
                'interes_total': _as_float(getattr(plan_vigente, 'monto_total_interes', 0)),
                'total_con_interes': _as_float(getattr(plan_vigente, 'monto_total_con_interes', 0)),
                'cuota_estimada': _as_float(getattr(cuotas[0], 'monto_programado', 0)) if cuotas else 0.0,
            }

    beneficios_aplicados = obtener_beneficios_aplicados_venta(getattr(venta, 'id_venta', 0) or 0)
    beneficio_aplicado_texto = ', '.join(
        item.get('resumen') or ''
        for item in beneficios_aplicados
        if (item.get('resumen') or '').strip()
    )

    return dict(
        venta=venta,
        detalles=detalles,
        pagos=pagos,
        pagos_resumen=pagos_resumen_render,
        empresa=empresa,
        subtotal=subtotal,
        descuento=descuento,
        descuento_manual=descuento_manual,
        descuento_fidelizacion=descuento_fidelizacion,
        total_pagado=total_pagado,
        vuelto=vuelto,
        preview=preview,
        embedded=embedded,
        moneda_simbolo=moneda_simbolo,
        footer_text=footer_text,
        paper_width_mm=paper_width_mm,
        es_venta_credito=es_venta_credito,
        cobro_label='Cobrado ahora' if es_venta_credito else 'Pagado',
        detalle_pago_label='Detalle de pago' if es_venta_credito else 'Pagos',
        monto_financiado=monto_financiado,
        resumen_credito_plan=resumen_credito_plan,
        beneficios_aplicados=beneficios_aplicados,
        beneficio_aplicado_texto=beneficio_aplicado_texto,
        beneficio_fidelizacion_tipo=beneficio_fidelizacion_tipo,
        beneficio_fidelizacion_descripcion=beneficio_fidelizacion_descripcion,
    )
