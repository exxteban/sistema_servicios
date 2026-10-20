"""Flags de pasteleria/cafeteria en la configuracion de Gastronomia.

Todos nacen apagados: con el flag en falso el sistema se comporta igual que
antes. Solo root los enciende (ver plan_pasteleria.md).
"""
from app import db


FLAG_ENCARGOS = 'encargos_activo'
FLAG_VENTA_POR_PESO = 'venta_por_peso_activa'
FLAG_PRODUCCION_DIARIA = 'produccion_diaria_activa'
FLAG_VENTA_RAPIDA = 'venta_rapida_activa'
FLAG_PROPINA = 'propina_activa'

PASTELERIA_FLAGS = (
    FLAG_ENCARGOS,
    FLAG_VENTA_POR_PESO,
    FLAG_PRODUCCION_DIARIA,
    FLAG_VENTA_RAPIDA,
    FLAG_PROPINA,
)


class PasteleriaFlagsMixin:
    """Columnas de flags para `GastronomiaClienteConfig` (todas `False` por defecto)."""

    encargos_activo = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    venta_por_peso_activa = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    produccion_diaria_activa = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    venta_rapida_activa = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    propina_activa = db.Column(db.Boolean, nullable=False, default=False, server_default='0')


OPCION_DEVOLVER_TODO = 'devolver_todo'
OPCION_RETENER_TODO = 'retener_todo'
OPCION_RETENER_PARCIAL = 'retener_parcial'
OPCIONES_CANCELACION = (OPCION_DEVOLVER_TODO, OPCION_RETENER_TODO, OPCION_RETENER_PARCIAL)
OPCIONES_CANCELACION_DEFAULT = ','.join(OPCIONES_CANCELACION)
FOTOS_ENCARGO_DEFAULT = 5


class PasteleriaParametrosMixin:
    """Parametros de encargos para `GastronomiaClienteConfig` (el default reproduce el comportamiento base)."""

    encargos_anticipo_horas = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    encargos_max_por_dia = db.Column(db.Integer, nullable=True)
    encargos_max_fotos = db.Column(
        db.Integer, nullable=False, default=FOTOS_ENCARGO_DEFAULT, server_default=str(FOTOS_ENCARGO_DEFAULT),
    )
    encargos_cancelacion_opciones = db.Column(
        db.String(120),
        nullable=False,
        default=OPCIONES_CANCELACION_DEFAULT,
        server_default=OPCIONES_CANCELACION_DEFAULT,
    )
