from sqlalchemy import func, or_

from app.models import Cliente, ClienteFidelizacionMovimiento
from app.services.clientes_fidelizacion import (
    BENEFICIO_TIPOS,
    beneficio_es_pos_aplicable,
    beneficio_resumen_config,
    fidelizacion_config,
)
from app.services.clientes_fidelizacion_politica import MODOS_GENERACION


def fidelizacion_resumen(args: dict | None = None, usuario=None) -> dict:
    del usuario
    payload = dict(args or {})
    top_n = max(1, min(int(payload.get('top_n') or 10), 30))

    config = fidelizacion_config()
    resumen_clientes = Cliente.query.with_entities(
        func.count(Cliente.id_cliente),
        func.coalesce(func.sum(Cliente.fidelizacion_compras_acumuladas), 0),
        func.coalesce(func.sum(Cliente.fidelizacion_consumos_disponibles), 0),
        func.coalesce(func.sum(Cliente.fidelizacion_consumos_canjeados), 0),
    ).filter(
        Cliente.id_cliente != 1,
        Cliente.activo.is_(True),
        or_(
            Cliente.fidelizacion_compras_acumuladas != 0,
            Cliente.fidelizacion_consumos_disponibles != 0,
            Cliente.fidelizacion_consumos_canjeados != 0,
        ),
    ).first()

    beneficio_snapshot = {
        'tipo': config.get('beneficio_tipo') or 'consumo_libre',
        'valor': config.get('beneficio_valor'),
        'descripcion': config.get('beneficio_descripcion') or '',
    }

    clientes_con_saldo = int((resumen_clientes[0] if resumen_clientes else 0) or 0)
    compras_acumuladas_total = int((resumen_clientes[1] if resumen_clientes else 0) or 0)
    beneficios_disponibles_total = int((resumen_clientes[2] if resumen_clientes else 0) or 0)
    beneficios_canjeados_total = int((resumen_clientes[3] if resumen_clientes else 0) or 0)

    clientes_listado = (
        Cliente.query.with_entities(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.fidelizacion_compras_acumuladas,
            Cliente.fidelizacion_consumos_disponibles,
            Cliente.fidelizacion_consumos_canjeados,
        )
        .filter(
            Cliente.id_cliente != 1,
            Cliente.activo.is_(True),
            or_(
                Cliente.fidelizacion_compras_acumuladas != 0,
                Cliente.fidelizacion_consumos_disponibles != 0,
                Cliente.fidelizacion_consumos_canjeados != 0,
            ),
        )
        .order_by(Cliente.fidelizacion_consumos_disponibles.desc(), Cliente.nombre.asc())
        .limit(top_n)
        .all()
    )

    return {
        'activa': bool(config.get('activa')),
        'estado_label': 'Activo' if config.get('activa') else 'Pausado',
        'regla': {
            'compras_requeridas': int(config.get('compras_requeridas') or 0),
            'premios_por_objetivo': int(config.get('premios_por_objetivo') or 0),
            'compras_ventana_dias': int(config.get('compras_ventana_dias') or 0),
            'modo_generacion': config.get('modo_generacion') or '',
            'modo_generacion_label': MODOS_GENERACION.get(config.get('modo_generacion') or '', 'Sin definir'),
            'max_beneficios_activos': int(config.get('max_beneficios_activos') or 0),
            'max_beneficios_ventana': int(config.get('max_beneficios_ventana') or 0),
        },
        'beneficio': {
            'tipo': config.get('beneficio_tipo') or 'consumo_libre',
            'tipo_label': BENEFICIO_TIPOS.get(config.get('beneficio_tipo') or '', 'Consumo o servicio libre'),
            'resumen': beneficio_resumen_config(config),
            'vigencia_dias': int(config.get('beneficio_vigencia_dias') or 0),
            'pos_aplicable': beneficio_es_pos_aplicable(beneficio_snapshot),
        },
        'metricas': {
            'clientes_con_saldo': clientes_con_saldo,
            'compras_acumuladas_total': compras_acumuladas_total,
            'beneficios_disponibles_total': beneficios_disponibles_total,
            'beneficios_canjeados_total': beneficios_canjeados_total,
            'movimientos_total': int(ClienteFidelizacionMovimiento.query.count()),
        },
        'clientes': [
            {
                'id_cliente': int(row.id_cliente or 0),
                'nombre': (row.nombre or '').strip() or f'Cliente {int(row.id_cliente or 0)}',
                'compras_acumuladas': int(row.fidelizacion_compras_acumuladas or 0),
                'beneficios_disponibles': int(row.fidelizacion_consumos_disponibles or 0),
                'beneficios_canjeados': int(row.fidelizacion_consumos_canjeados or 0),
            }
            for row in clientes_listado
        ],
        'flujo': [
            'Cada venta completada de un cliente valido suma una compra acumulada.',
            'Al llegar al objetivo, el sistema descuenta las compras usadas y libera los beneficios configurados.',
            'Los beneficios se pueden canjear manualmente y algunos tambien aplican en POS como descuento o saldo a favor.',
            'El historial guarda compras, liberaciones, canjes, vencimientos y reversiones por anulacion.',
        ],
        'nota': 'Resumen de fidelizacion en solo lectura usando la configuracion global y el saldo acumulado actual.',
    }
