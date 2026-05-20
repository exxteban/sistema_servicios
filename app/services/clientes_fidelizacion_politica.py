from datetime import datetime, timedelta

from app.models import ClienteFidelizacionMovimiento, Configuracion
from app.services.clientes_fidelizacion_support import compras_ventana_dias_config


CONFIG_FIDELIZACION_MODO_GENERACION = 'clientes_fidelizacion_modo_generacion'
CONFIG_FIDELIZACION_MAX_BENEFICIOS_ACTIVOS = 'clientes_fidelizacion_max_beneficios_activos'
CONFIG_FIDELIZACION_MAX_BENEFICIOS_VENTANA = 'clientes_fidelizacion_max_beneficios_ventana'

MODO_ACUMULATIVO = 'acumulativo'
MODO_UNA_VEZ_VENTANA = 'una_vez_ventana'

MODOS_GENERACION = {
    MODO_ACUMULATIVO: 'Acumulativo: cada X compras genera Y beneficios',
    MODO_UNA_VEZ_VENTANA: 'Una vez por ventana: si alcanza X compras genera Y beneficios una sola vez',
}


def normalizar_modo_generacion(valor):
    valor = (valor or MODO_ACUMULATIVO).strip()
    return valor if valor in MODOS_GENERACION else MODO_ACUMULATIVO


def obtener_tope_config(clave):
    return max(0, Configuracion.obtener_int(clave, default=0))


def resolver_cantidad_beneficios_a_otorgar(cliente, config):
    cantidad = int(config.get('premios_por_objetivo') or 0)
    if cantidad <= 0:
        return 0
    if config.get('modo_generacion') == MODO_UNA_VEZ_VENTANA and _metas_generadas_en_ventana(cliente):
        return 0

    max_activos = int(config.get('max_beneficios_activos') or 0)
    if max_activos > 0:
        disponibles = _beneficios_disponibles_actuales(cliente.id_cliente)
        cantidad = min(cantidad, max(0, max_activos - disponibles))

    max_ventana = int(config.get('max_beneficios_ventana') or 0)
    if max_ventana > 0:
        generados = _beneficios_generados_en_ventana(cliente.id_cliente)
        cantidad = min(cantidad, max(0, max_ventana - generados))

    return max(0, cantidad)


def _desde_ventana():
    return datetime.utcnow() - timedelta(days=compras_ventana_dias_config())


def _metas_generadas_en_ventana(cliente):
    return ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(cliente.id_cliente),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'premio_meta',
        ClienteFidelizacionMovimiento.fecha_movimiento >= _desde_ventana(),
    ).first() is not None


def _beneficios_generados_en_ventana(id_cliente):
    return ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(id_cliente),
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.fecha_movimiento >= _desde_ventana(),
    ).count()


def _beneficios_disponibles_actuales(id_cliente):
    originales = ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_cliente == int(id_cliente),
        ClienteFidelizacionMovimiento.id_movimiento_origen.is_(None),
        ClienteFidelizacionMovimiento.tipo_movimiento == 'beneficio_otorgado',
        ClienteFidelizacionMovimiento.delta_consumos_disponibles > 0,
    ).all()
    return sum(1 for item in originales if not _tiene_hijo_consumo(item.id_movimiento))


def _tiene_hijo_consumo(id_movimiento):
    return ClienteFidelizacionMovimiento.query.filter(
        ClienteFidelizacionMovimiento.id_movimiento_origen == int(id_movimiento),
        ClienteFidelizacionMovimiento.tipo_movimiento.in_(
            ('canje_manual', 'canje_venta', 'reversion_venta', 'beneficio_vencido')
        ),
    ).first() is not None
