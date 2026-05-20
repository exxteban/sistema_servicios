from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app import db
from app.models import Cliente, CuentaPorCobrar, DetalleVenta, PagoCuentaCobrar, Venta
from cobranzas.models import CuotaCreditoVenta, PlanCreditoVenta
from cobranzas.services.cuotas_service import sincronizar_plan_credito


def _decimal_positivo(value) -> Decimal:
    try:
        numero = Decimal(str(value or 0))
    except Exception:
        numero = Decimal('0')
    if numero < 0:
        return Decimal('0')
    return numero


def _fecha_referencia(fecha=None) -> date:
    if isinstance(fecha, date):
        return fecha
    return date.today()


def _obtener_plan_credito_vigente(cuenta: CuentaPorCobrar) -> PlanCreditoVenta | None:
    if cuenta is None or getattr(cuenta, 'id_cuenta_cobrar', None) is None:
        return None
    return (
        PlanCreditoVenta.query
        .options(joinedload(PlanCreditoVenta.cuotas))
        .filter(
            PlanCreditoVenta.id_cuenta_cobrar == int(cuenta.id_cuenta_cobrar),
            PlanCreditoVenta.estado.notin_(('anulado', 'refinanciado')),
        )
        .order_by(PlanCreditoVenta.id_plan_credito_venta.desc())
        .first()
    )


def _refrescar_plan_credito_para_vista(cuenta: CuentaPorCobrar) -> PlanCreditoVenta | None:
    if cuenta is None or getattr(cuenta, 'id_cuenta_cobrar', None) is None:
        return None

    plan_credito = _obtener_plan_credito_vigente(cuenta)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        sincronizar_plan_credito(plan_credito)
    sincronizar_saldos_cuenta(cuenta)
    db.session.flush()
    return plan_credito


def resolver_estado_cuenta(cuenta: CuentaPorCobrar, fecha=None) -> tuple[Decimal, str, int]:
    if (cuenta.estado or '').strip().lower() == 'anulada':
        return Decimal('0'), 'anulada', 0

    plan_credito = _obtener_plan_credito_vigente(cuenta)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        fecha_ref = _fecha_referencia(fecha)
        saldo_total = sum((_decimal_positivo(cuota.saldo_pendiente) for cuota in plan_credito.cuotas), Decimal('0'))
        if saldo_total <= Decimal('0'):
            return Decimal('0'), 'pagada', 0

        cuotas_vencidas = [
            cuota for cuota in plan_credito.cuotas
            if _decimal_positivo(cuota.saldo_pendiente) > Decimal('0')
            and cuota.fecha_vencimiento
            and cuota.fecha_vencimiento < fecha_ref
        ]
        if cuotas_vencidas:
            dias_vencido = max((fecha_ref - cuota.fecha_vencimiento).days for cuota in cuotas_vencidas)
            return saldo_total, 'vencida', dias_vencido
        return saldo_total, 'pendiente', 0

    saldo_pendiente = _decimal_positivo(cuenta.monto_total) - _decimal_positivo(cuenta.monto_cobrado)
    if saldo_pendiente <= Decimal('0'):
        return Decimal('0'), 'pagada', 0

    fecha_ref = _fecha_referencia(fecha)
    fecha_vencimiento = getattr(cuenta, 'fecha_vencimiento', None)
    if fecha_vencimiento and fecha_vencimiento < fecha_ref:
        return saldo_pendiente, 'vencida', (fecha_ref - fecha_vencimiento).days
    return saldo_pendiente, 'pendiente', 0


def _estado_badge(estado: str) -> tuple[str, str]:
    estado_normalizado = (estado or '').strip().lower()
    if estado_normalizado == 'pagada':
        return 'Pagada', 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    if estado_normalizado == 'vencida':
        return 'Vencida', 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
    if estado_normalizado == 'anulada':
        return 'Anulada', 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200'
    return 'Pendiente', 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'


def _resumen_productos_venta(venta: Venta | None, *, max_items_visible: int = 3) -> dict:
    if venta is None:
        return {
            'items': [],
            'texto': 'Sin detalle de productos',
            'cantidad_productos': 0,
            'cantidad_unidades': 0,
        }

    detalles_query = getattr(venta, 'detalles', None)
    if detalles_query is None:
        return {
            'items': [],
            'texto': 'Sin detalle de productos',
            'cantidad_productos': 0,
            'cantidad_unidades': 0,
        }

    detalles = (
        detalles_query
        .options(joinedload(DetalleVenta.producto))
        .order_by(DetalleVenta.id_detalle_venta.asc())
        .all()
    )

    items = []
    total_unidades = 0
    for detalle in detalles:
        cantidad = int(detalle.cantidad or 0)
        total_unidades += cantidad
        if detalle.producto and getattr(detalle.producto, 'nombre', None):
            nombre_producto = detalle.producto.nombre
        else:
            nombre_producto = f'Producto #{int(detalle.id_producto)}'
        items.append(f'{nombre_producto} x{cantidad}')

    if not items:
        texto = 'Sin detalle de productos'
    elif len(items) <= max_items_visible:
        texto = ', '.join(items)
    else:
        restantes = len(items) - max_items_visible
        texto = f"{', '.join(items[:max_items_visible])} +{restantes} mas"

    return {
        'items': items,
        'texto': texto,
        'cantidad_productos': len(items),
        'cantidad_unidades': total_unidades,
    }


def construir_vista_cuenta(cuenta: CuentaPorCobrar, *, incluir_productos: bool = False) -> dict:
    saldo_pendiente, estado_resuelto, dias_vencido = resolver_estado_cuenta(cuenta)
    estado_label, estado_classes = _estado_badge(estado_resuelto)
    cliente = getattr(cuenta, 'cliente', None)
    venta = getattr(cuenta, 'venta', None)
    plan_credito = construir_vista_plan_credito(_obtener_plan_credito_vigente(cuenta))
    monto_sugerido_cobro = float(saldo_pendiente)
    sugerencia_cobro = {
        'origen': 'saldo_cuenta',
        'monto': monto_sugerido_cobro,
        'etiqueta': 'Saldo libre sobre la cuenta',
    }
    if plan_credito and plan_credito.get('proxima_cuota'):
        proxima_cuota = plan_credito['proxima_cuota']
        monto_sugerido_cobro = min(
            float(proxima_cuota.get('saldo_pendiente') or 0),
            float(saldo_pendiente),
        )
        sugerencia_cobro = {
            'origen': 'proxima_cuota',
            'monto': monto_sugerido_cobro,
            'etiqueta': f"Cuota #{int(proxima_cuota.get('numero_cuota') or 0)}",
        }
    productos_venta = _resumen_productos_venta(venta) if incluir_productos else None
    return {
        'cuenta': cuenta,
        'cliente': cliente,
        'venta': venta,
        'productos_venta': productos_venta,
        'plan_credito': plan_credito,
        'estado_resuelto': estado_resuelto,
        'estado_label': estado_label,
        'estado_classes': estado_classes,
        'dias_vencido': dias_vencido,
        'esta_vencida': estado_resuelto == 'vencida',
        'tiene_saldo': saldo_pendiente > 0,
        'monto_total': float(_decimal_positivo(cuenta.monto_total)),
        'monto_cobrado': float(_decimal_positivo(cuenta.monto_cobrado)),
        'saldo_pendiente': float(saldo_pendiente),
        'monto_sugerido_cobro': monto_sugerido_cobro,
        'sugerencia_cobro': sugerencia_cobro,
    }


def construir_vista_cuota(cuota: CuotaCreditoVenta) -> dict:
    return {
        'cuota': cuota,
        'numero_cuota': int(cuota.numero_cuota or 0),
        'fecha_vencimiento': cuota.fecha_vencimiento,
        'capital_programado': float(_decimal_positivo(getattr(cuota, 'capital_programado', 0))),
        'interes_programado': float(_decimal_positivo(getattr(cuota, 'interes_programado', 0))),
        'saldo_capital': float(_decimal_positivo(getattr(cuota, 'saldo_capital', 0))),
        'monto_programado': float(_decimal_positivo(cuota.monto_programado)),
        'monto_cobrado': float(_decimal_positivo(cuota.monto_cobrado)),
        'saldo_pendiente': float(_decimal_positivo(cuota.saldo_pendiente)),
        'estado': (cuota.estado or '').strip().lower(),
        'dias_vencido': int(cuota.dias_vencido or 0),
    }


def construir_vista_plan_credito(plan_credito: PlanCreditoVenta | None) -> dict | None:
    if plan_credito is None:
        return None
    cuotas = [construir_vista_cuota(cuota) for cuota in plan_credito.cuotas]
    cuotas_pendientes = [cuota for cuota in cuotas if cuota['saldo_pendiente'] > 0]
    proxima_cuota = cuotas_pendientes[0] if cuotas_pendientes else None
    return {
        'plan': plan_credito,
        'modo': (plan_credito.modo or '').strip().lower(),
        'cantidad_cuotas': int(plan_credito.cantidad_cuotas or 0),
        'frecuencia_dias': int(plan_credito.frecuencia_dias or 0),
        'tasa_periodica_pct': float(_decimal_positivo(getattr(plan_credito, 'tasa_periodica_pct', 0))),
        'sistema_amortizacion': (getattr(plan_credito, 'sistema_amortizacion', '') or 'frances').strip().lower(),
        'monto_total_financiado': float(_decimal_positivo(plan_credito.monto_total_financiado)),
        'monto_total_interes': float(_decimal_positivo(getattr(plan_credito, 'monto_total_interes', 0))),
        'monto_total_con_interes': float(_decimal_positivo(getattr(plan_credito, 'monto_total_con_interes', 0))),
        'monto_anticipo': float(_decimal_positivo(plan_credito.monto_anticipo)),
        'monto_cobrado': float(_decimal_positivo(plan_credito.monto_cobrado)),
        'saldo_pendiente': float(_decimal_positivo(plan_credito.saldo_pendiente)),
        'estado': (plan_credito.estado or '').strip().lower(),
        'cuotas': cuotas,
        'cuotas_pagadas': sum(1 for cuota in cuotas if cuota['estado'] == 'pagada'),
        'cuotas_vencidas': sum(1 for cuota in cuotas if cuota['estado'] == 'vencida'),
        'cuotas_pendientes': sum(1 for cuota in cuotas if cuota['saldo_pendiente'] > 0),
        'proxima_cuota': proxima_cuota,
    }


def construir_vista_pago(pago: PagoCuentaCobrar, *, incluir_productos: bool = False) -> dict:
    estado = 'anulado' if pago.esta_anulado() else 'activo'
    estado_label, estado_classes = _estado_badge(estado)
    if estado == 'activo':
        estado_label = 'Activo'
        estado_classes = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
    detalle_aplicacion = pago.get_detalle_aplicacion() if hasattr(pago, 'get_detalle_aplicacion') else {}
    productos_venta = None
    if incluir_productos:
        cuenta = getattr(pago, 'cuenta', None)
        venta = getattr(cuenta, 'venta', None) if cuenta is not None else None
        if venta is None and cuenta is not None and getattr(cuenta, 'id_venta', None):
            venta = db.session.get(Venta, int(cuenta.id_venta))
        productos_venta = _resumen_productos_venta(venta)
    return {
        'pago': pago,
        'estado': estado,
        'estado_label': estado_label,
        'estado_classes': estado_classes,
        'productos_venta': productos_venta,
        'detalle_aplicacion': detalle_aplicacion,
        'cuota_principal': detalle_aplicacion.get('cuota_principal') if detalle_aplicacion else None,
        'cuotas_aplicadas': detalle_aplicacion.get('cuotas_aplicadas') if detalle_aplicacion else [],
    }


def sincronizar_saldos_cuenta(cuenta: CuentaPorCobrar) -> CuentaPorCobrar:
    plan_credito = _obtener_plan_credito_vigente(cuenta)
    if plan_credito and (plan_credito.modo or '').strip().lower() == 'cuotas':
        total_plan = _decimal_positivo(getattr(plan_credito, 'monto_total_con_interes', 0))
        if total_plan <= Decimal('0'):
            total_plan = _decimal_positivo(plan_credito.monto_total_financiado)
        cuenta.monto_total = total_plan
        cuenta.monto_cobrado = _decimal_positivo(plan_credito.monto_cobrado)
        cuotas_abiertas = [
            cuota for cuota in plan_credito.cuotas
            if _decimal_positivo(cuota.saldo_pendiente) > Decimal('0')
        ]
        cuotas_abiertas.sort(key=lambda cuota: (cuota.fecha_vencimiento or date.max, cuota.numero_cuota, cuota.id_cuota_credito))
        cuenta.fecha_vencimiento = cuotas_abiertas[0].fecha_vencimiento if cuotas_abiertas else None

    monto_total = _decimal_positivo(cuenta.monto_total)
    monto_cobrado = _decimal_positivo(cuenta.monto_cobrado)
    saldo_pendiente, estado, dias_vencido = resolver_estado_cuenta(cuenta)
    cuenta.monto_total = monto_total
    cuenta.monto_cobrado = monto_cobrado
    cuenta.saldo_pendiente = saldo_pendiente
    cuenta.estado = estado
    cuenta.dias_vencido = dias_vencido

    venta = db.session.get(Venta, cuenta.id_venta)
    if venta is not None:
        venta.saldo_pendiente = saldo_pendiente

    cliente = db.session.get(Cliente, cuenta.id_cliente)
    if cliente is not None:
        saldo_cliente = (
            db.session.query(func.sum(CuentaPorCobrar.saldo_pendiente))
            .filter(
                CuentaPorCobrar.id_cliente == cuenta.id_cliente,
                CuentaPorCobrar.estado != 'anulada',
            )
            .scalar()
        )
        cliente.saldo_pendiente = _decimal_positivo(saldo_cliente)

    return cuenta


def anular_cuenta_por_cobrar(cuenta: CuentaPorCobrar) -> CuentaPorCobrar:
    if cuenta is None:
        raise ValueError('Cuenta por cobrar no encontrada')
    if (cuenta.estado or '').strip().lower() == 'anulada':
        return cuenta

    pagos_activos = cuenta.pagos.filter(PagoCuentaCobrar.estado != 'anulado').count()
    if pagos_activos > 0:
        raise ValueError('La venta tiene cobros de credito activos. Anule esos cobros antes de anular la venta')

    for plan in cuenta.planes_credito.filter(PlanCreditoVenta.estado != 'anulado').all():
        plan.estado = 'anulado'
        plan.monto_cobrado = Decimal('0')
        plan.saldo_pendiente = Decimal('0')
        for cuota in plan.cuotas:
            cuota.estado = 'anulado'
            cuota.monto_cobrado = Decimal('0')
            cuota.saldo_pendiente = Decimal('0')
            cuota.dias_vencido = 0

    cuenta.monto_cobrado = Decimal('0')
    cuenta.saldo_pendiente = Decimal('0')
    cuenta.fecha_vencimiento = None
    cuenta.estado = 'anulada'
    cuenta.dias_vencido = 0
    return sincronizar_saldos_cuenta(cuenta)


def construir_resumen_cobranzas(limit_cuentas: int = 8) -> dict:
    hoy = date.today()
    base_query = CuentaPorCobrar.query.filter(CuentaPorCobrar.estado != 'anulada')
    total_cuentas = base_query.count()
    cuentas_abiertas = base_query.filter(CuentaPorCobrar.saldo_pendiente > 0).count()
    cuentas_vencidas = base_query.filter(
        CuentaPorCobrar.saldo_pendiente > 0,
        CuentaPorCobrar.fecha_vencimiento.isnot(None),
        CuentaPorCobrar.fecha_vencimiento < hoy,
    ).count()
    saldo_total = base_query.with_entities(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0)).scalar() or 0
    cobrado_total = base_query.with_entities(func.coalesce(func.sum(CuentaPorCobrar.monto_cobrado), 0)).scalar() or 0

    cuentas_destacadas = []
    if limit_cuentas > 0:
        cuentas = (
            CuentaPorCobrar.query.options(
                joinedload(CuentaPorCobrar.cliente),
                joinedload(CuentaPorCobrar.venta),
            )
            .filter(CuentaPorCobrar.estado != 'anulada')
            .order_by(CuentaPorCobrar.fecha_vencimiento.asc(), CuentaPorCobrar.id_cuenta_cobrar.desc())
            .limit(limit_cuentas)
            .all()
        )
        cuentas_destacadas = [construir_vista_cuenta(cuenta) for cuenta in cuentas]

    return {
        'modulo_listo': True,
        'mensaje': 'Resumen operativo de cuentas por cobrar y cobros registrados.',
        'total_cuentas': total_cuentas,
        'cuentas_abiertas': cuentas_abiertas,
        'cuentas_vencidas': cuentas_vencidas,
        'saldo_total': float(_decimal_positivo(saldo_total)),
        'cobrado_total': float(_decimal_positivo(cobrado_total)),
        'cuentas_destacadas': cuentas_destacadas,
        'tiene_cuentas': total_cuentas > 0,
    }


def listar_cuentas_por_cobrar(*, page: int = 1, per_page: int = 20, filtro_estado: str = 'abiertas', busqueda: str = '') -> dict:
    hoy = date.today()
    filtro_estado = (filtro_estado or 'abiertas').strip().lower()
    busqueda = (busqueda or '').strip()

    query = CuentaPorCobrar.query.options(
        joinedload(CuentaPorCobrar.cliente),
        joinedload(CuentaPorCobrar.venta),
    ).filter(CuentaPorCobrar.estado != 'anulada')

    if busqueda:
        condiciones = [Cliente.nombre.ilike(f'%{busqueda}%')]
        if hasattr(Cliente, 'ruc_ci'):
            condiciones.append(Cliente.ruc_ci.ilike(f'%{busqueda}%'))
        if busqueda.isdigit():
            numero = int(busqueda)
            condiciones.extend([
                CuentaPorCobrar.id_cuenta_cobrar == numero,
                CuentaPorCobrar.id_venta == numero,
                CuentaPorCobrar.id_cliente == numero,
            ])
        query = query.join(CuentaPorCobrar.cliente).filter(or_(*condiciones))

    if filtro_estado == 'vencidas':
        query = query.filter(
            CuentaPorCobrar.saldo_pendiente > 0,
            CuentaPorCobrar.fecha_vencimiento.isnot(None),
            CuentaPorCobrar.fecha_vencimiento < hoy,
        )
    elif filtro_estado == 'pagadas':
        query = query.filter(CuentaPorCobrar.saldo_pendiente <= 0)
    elif filtro_estado == 'pendientes':
        query = query.filter(
            CuentaPorCobrar.saldo_pendiente > 0,
            or_(CuentaPorCobrar.fecha_vencimiento.is_(None), CuentaPorCobrar.fecha_vencimiento >= hoy),
        )
    elif filtro_estado == 'todas':
        pass
    else:
        filtro_estado = 'abiertas'
        query = query.filter(CuentaPorCobrar.saldo_pendiente > 0)

    paginacion = query.order_by(
        CuentaPorCobrar.fecha_vencimiento.asc(),
        CuentaPorCobrar.id_cuenta_cobrar.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)

    return {
        'items': [construir_vista_cuenta(cuenta) for cuenta in paginacion.items],
        'paginacion': paginacion,
        'filtro_estado': filtro_estado,
        'busqueda': busqueda,
    }


def obtener_detalle_cuenta(id_cuenta: int) -> dict | None:
    cuenta = (
        CuentaPorCobrar.query.options(
            joinedload(CuentaPorCobrar.cliente),
            joinedload(CuentaPorCobrar.venta).joinedload(Venta.vendedor),
        )
        .filter(CuentaPorCobrar.id_cuenta_cobrar == int(id_cuenta))
        .first()
    )
    if cuenta is None:
        return None
    plan_credito_model = _refrescar_plan_credito_para_vista(cuenta)

    pagos = (
        PagoCuentaCobrar.query.options(
            joinedload(PagoCuentaCobrar.metodo),
            joinedload(PagoCuentaCobrar.usuario),
            joinedload(PagoCuentaCobrar.usuario_anulacion),
            joinedload(PagoCuentaCobrar.cuenta).joinedload(CuentaPorCobrar.venta),
        )
        .filter(PagoCuentaCobrar.id_cuenta_cobrar == int(id_cuenta))
        .order_by(PagoCuentaCobrar.fecha_pago.desc(), PagoCuentaCobrar.id_pago_cuenta.desc())
        .all()
    )
    plan_credito = construir_vista_plan_credito(plan_credito_model)

    pagos_activos = [pago for pago in pagos if not pago.esta_anulado()]
    return {
        'cuenta': construir_vista_cuenta(cuenta, incluir_productos=True),
        'pagos': [construir_vista_pago(pago, incluir_productos=True) for pago in pagos],
        'plan_credito': plan_credito,
        'cuotas': plan_credito['cuotas'] if plan_credito else [],
        'cantidad_pagos': len(pagos),
        'cantidad_pagos_activos': len(pagos_activos),
        'total_cobrado_activo': float(sum((_decimal_positivo(pago.monto) for pago in pagos_activos), Decimal('0'))),
    }


def obtener_detalle_cliente_cobranzas(id_cliente: int) -> dict | None:
    cliente = db.session.get(Cliente, int(id_cliente))
    if cliente is None:
        return None

    cuentas = (
        CuentaPorCobrar.query.options(joinedload(CuentaPorCobrar.venta))
        .filter(
            CuentaPorCobrar.id_cliente == int(id_cliente),
            CuentaPorCobrar.estado != 'anulada',
        )
        .order_by(CuentaPorCobrar.fecha_vencimiento.asc(), CuentaPorCobrar.id_cuenta_cobrar.desc())
        .all()
    )
    for cuenta in cuentas:
        _refrescar_plan_credito_para_vista(cuenta)
    cuentas_vista = [construir_vista_cuenta(cuenta, incluir_productos=True) for cuenta in cuentas]

    pagos = (
        PagoCuentaCobrar.query.options(
            joinedload(PagoCuentaCobrar.metodo),
            joinedload(PagoCuentaCobrar.usuario),
            joinedload(PagoCuentaCobrar.cuenta).joinedload(CuentaPorCobrar.venta),
        )
        .join(CuentaPorCobrar, PagoCuentaCobrar.id_cuenta_cobrar == CuentaPorCobrar.id_cuenta_cobrar)
        .filter(CuentaPorCobrar.id_cliente == int(id_cliente))
        .order_by(PagoCuentaCobrar.fecha_pago.desc(), PagoCuentaCobrar.id_pago_cuenta.desc())
        .limit(20)
        .all()
    )

    total_cuentas = len(cuentas_vista)
    cuentas_abiertas = sum(1 for item in cuentas_vista if item['tiene_saldo'])
    cuentas_vencidas = sum(1 for item in cuentas_vista if item['esta_vencida'])
    cuentas_pagadas = sum(1 for item in cuentas_vista if item['estado_resuelto'] == 'pagada')
    saldo_total = sum((item['saldo_pendiente'] for item in cuentas_vista), 0.0)
    cobrado_total = sum((item['monto_cobrado'] for item in cuentas_vista), 0.0)

    return {
        'cliente': cliente,
        'cuentas': cuentas_vista,
        'pagos': [construir_vista_pago(pago, incluir_productos=True) for pago in pagos],
        'resumen': {
            'total_cuentas': total_cuentas,
            'cuentas_abiertas': cuentas_abiertas,
            'cuentas_vencidas': cuentas_vencidas,
            'cuentas_pagadas': cuentas_pagadas,
            'saldo_total': saldo_total,
            'cobrado_total': cobrado_total,
            'credito_disponible': float(getattr(cliente, 'credito_disponible', 0) or 0),
        },
    }


def obtener_resumen_credito_cliente(id_cliente: int) -> dict | None:
    cliente = db.session.get(Cliente, int(id_cliente))
    if cliente is None:
        return None

    hoy = date.today()
    base_query = CuentaPorCobrar.query.filter(
        CuentaPorCobrar.id_cliente == int(id_cliente),
        CuentaPorCobrar.estado != 'anulada',
    )
    cuentas_abiertas = base_query.filter(CuentaPorCobrar.saldo_pendiente > 0).count()
    cuentas_vencidas = base_query.filter(
        CuentaPorCobrar.saldo_pendiente > 0,
        CuentaPorCobrar.fecha_vencimiento.isnot(None),
        CuentaPorCobrar.fecha_vencimiento < hoy,
    ).count()
    saldo_total = base_query.with_entities(func.coalesce(func.sum(CuentaPorCobrar.saldo_pendiente), 0)).scalar() or 0
    cuenta_prioritaria = (
        base_query.filter(CuentaPorCobrar.saldo_pendiente > 0)
        .order_by(
            CuentaPorCobrar.fecha_vencimiento.asc(),
            CuentaPorCobrar.id_cuenta_cobrar.desc(),
        )
        .first()
    )

    return {
        'cliente': cliente,
        'cliente_id': int(cliente.id_cliente),
        'saldo_total': float(_decimal_positivo(saldo_total)),
        'cuentas_abiertas': int(cuentas_abiertas),
        'cuentas_vencidas': int(cuentas_vencidas),
        'limite_credito': float(_decimal_positivo(getattr(cliente, 'limite_credito', 0))),
        'credito_disponible': float(getattr(cliente, 'credito_disponible', 0) or 0),
        'tiene_deuda': bool(cuentas_abiertas > 0 and _decimal_positivo(saldo_total) > 0),
        'cuenta_prioritaria_id': int(cuenta_prioritaria.id_cuenta_cobrar) if cuenta_prioritaria else None,
    }
