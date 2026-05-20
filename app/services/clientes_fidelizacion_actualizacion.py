from decimal import Decimal

from sqlalchemy.orm import aliased

from app import db
from app.models import ClienteFidelizacionMovimiento
from app.services.clientes_fidelizacion_support import decimal_safe


TIPOS_BLOQUEO_BENEFICIO_ACTIVO = (
    'canje_manual',
    'canje_venta',
    'reversion_venta',
    'beneficio_vencido',
)


def actualizar_beneficios_activos_a_config(beneficio_tipo, beneficio_valor, beneficio_descripcion):
    """Ajusta beneficios disponibles a la regla global vigente."""
    beneficio_tipo = (beneficio_tipo or 'consumo_libre').strip() or 'consumo_libre'
    beneficio_valor = decimal_safe(beneficio_valor, default=Decimal('0'))
    beneficio_descripcion = (beneficio_descripcion or '').strip()[:255]

    hijo = aliased(ClienteFidelizacionMovimiento)
    tiene_hijo = db.session.query(hijo.id_movimiento).filter(
        hijo.id_movimiento_origen == ClienteFidelizacionMovimiento.id_movimiento,
        hijo.tipo_movimiento.in_(TIPOS_BLOQUEO_BENEFICIO_ACTIVO),
    ).exists()

    beneficios = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.delta_consumos_disponibles > 0,
        ~tiene_hijo,
    ).all()

    actualizados = 0
    for beneficio in beneficios:
        valor_actual = decimal_safe(getattr(beneficio, 'beneficio_valor', 0), default=Decimal('0'))
        tipo_actual = (getattr(beneficio, 'beneficio_tipo', '') or 'consumo_libre').strip() or 'consumo_libre'
        descripcion_actual = (getattr(beneficio, 'beneficio_descripcion', '') or '').strip()
        if (
            tipo_actual == beneficio_tipo
            and valor_actual == beneficio_valor
            and descripcion_actual == beneficio_descripcion
        ):
            continue
        beneficio.beneficio_tipo = beneficio_tipo
        beneficio.beneficio_valor = beneficio_valor
        beneficio.beneficio_descripcion = beneficio_descripcion
        actualizados += 1

    if actualizados:
        db.session.commit()
    return actualizados
