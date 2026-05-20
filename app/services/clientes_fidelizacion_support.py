from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from app import db
from app.models import Cliente, ClienteFidelizacionMovimiento, Configuracion


CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS = 'clientes_fidelizacion_beneficio_vigencia_dias'
CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS = 'clientes_fidelizacion_compras_ventana_dias'


def decimal_safe(valor, default):
    if valor is None:
        return default
    if isinstance(valor, Decimal):
        return valor
    try:
        texto = str(valor).strip()
        if not texto:
            return default
        return Decimal(texto.replace(',', '.'))
    except (InvalidOperation, ValueError, TypeError):
        return default


def decimal_config(clave, default='0'):
    return decimal_safe(Configuracion.obtener(clave, default), default=Decimal(str(default)))


def formatear_monto(valor):
    return '{:,.0f}'.format(float(decimal_safe(valor, default=Decimal('0')))).replace(',', '.')


def formatear_decimal(valor):
    valor = decimal_safe(valor, default=Decimal('0'))
    texto = format(valor.normalize() if valor != 0 else Decimal('0'), 'f')
    return texto.rstrip('0').rstrip('.') if '.' in texto else texto


def formatear_fecha(valor):
    return valor.strftime('%d/%m/%Y') if valor else ''


def vigencia_dias_config(default=30):
    return max(1, Configuracion.obtener_int(CONFIG_FIDELIZACION_BENEFICIO_VIGENCIA_DIAS, default=default))


def compras_ventana_dias_config(default=365):
    return max(1, Configuracion.obtener_int(CONFIG_FIDELIZACION_COMPRAS_VENTANA_DIAS, default=default))


def calcular_fecha_vencimiento_beneficio(vigencia_dias, fecha_base=None):
    if isinstance(fecha_base, datetime):
        fecha_base = fecha_base.date()
    elif not isinstance(fecha_base, date):
        fecha_base = datetime.utcnow().date()
    return fecha_base + timedelta(days=max(1, int(vigencia_dias or 1)))


def agrupar_resumenes(snapshots, resumen_builder):
    acumulado = {}
    orden = []
    for snapshot in snapshots:
        fecha_vencimiento = snapshot.get('fecha_vencimiento')
        key = (
            (snapshot.get('tipo') or '').strip(),
            str(decimal_safe(snapshot.get('valor'), default=Decimal('0'))),
            (snapshot.get('descripcion') or '').strip(),
            fecha_vencimiento.isoformat() if fecha_vencimiento else '',
        )
        if key not in acumulado:
            acumulado[key] = {
                'cantidad': 0,
                'resumen': resumen_builder(snapshot),
                'fecha_vencimiento': fecha_vencimiento,
                'fecha_vencimiento_texto': formatear_fecha(fecha_vencimiento),
            }
            orden.append(key)
        acumulado[key]['cantidad'] += 1
    return [acumulado[key] for key in orden]


def sincronizar_beneficios_vencidos(id_cliente=None, hoy=None, resumen_builder=None):
    hoy = hoy or datetime.utcnow().date()
    query = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.delta_consumos_disponibles > 0,
        ClienteFidelizacionMovimiento.beneficio_fecha_vencimiento.isnot(None),
        ClienteFidelizacionMovimiento.beneficio_fecha_vencimiento < hoy,
    )
    if id_cliente is not None:
        query = query.filter(ClienteFidelizacionMovimiento.id_cliente == int(id_cliente))
    expiran = query.order_by(
        ClienteFidelizacionMovimiento.id_cliente.asc(),
        ClienteFidelizacionMovimiento.beneficio_fecha_vencimiento.asc(),
        ClienteFidelizacionMovimiento.id_movimiento.asc(),
    ).all()
    cambios = 0
    for original in expiran:
        ya_vencido = ClienteFidelizacionMovimiento.query.filter(
            ClienteFidelizacionMovimiento.id_movimiento_origen == int(original.id_movimiento),
            ClienteFidelizacionMovimiento.tipo_movimiento.in_(('canje_manual', 'canje_venta', 'reversion_venta', 'beneficio_vencido')),
        ).first()
        if ya_vencido:
            continue
        cliente = Cliente.query.filter(Cliente.id_cliente == int(original.id_cliente)).with_for_update().first()
        if not cliente:
            continue
        cliente.fidelizacion_consumos_disponibles = int(cliente.fidelizacion_consumos_disponibles or 0) - 1
        snapshot = {
            'tipo': (original.beneficio_tipo or 'consumo_libre').strip(),
            'valor': original.beneficio_valor,
            'descripcion': (original.beneficio_descripcion or '').strip(),
            'fecha_vencimiento': original.beneficio_fecha_vencimiento,
        }
        resumen = resumen_builder(snapshot) if resumen_builder else 'Beneficio de fidelizacion'
        db.session.add(ClienteFidelizacionMovimiento(
            id_cliente=int(cliente.id_cliente),
            tipo_movimiento='beneficio_vencido',
            delta_consumos_disponibles=-1,
            referencia_tipo='cliente',
            referencia_id=int(cliente.id_cliente),
            id_movimiento_origen=int(original.id_movimiento),
            beneficio_tipo=original.beneficio_tipo,
            beneficio_valor=original.beneficio_valor,
            beneficio_descripcion=original.beneficio_descripcion,
            beneficio_fecha_vencimiento=original.beneficio_fecha_vencimiento,
            descripcion=f'Beneficio vencido: {resumen}',
        ))
        cambios += 1
    if cambios:
        db.session.flush()
    return cambios
