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
