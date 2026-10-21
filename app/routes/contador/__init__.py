"""Área "Contador/a": lo que necesita el profesional de afuera para liquidar.

Portada de sistema_silvio_cel. Tiene su propio apartado en el menú lateral
porque no es parte de la caja del dueño. El rol "Contador/a"
(`ver_area_contador`) entra acá sin ver la caja ni los reportes del negocio;
también entra quien ya ve reportes o caja. Por ahora tiene el resumen de IVA
del mes; los talonarios, las notas de crédito en papel, la factura de los
gastos y el cierre del mes llegan en las fases siguientes.

Todo es IVA paraguayo (timbrado, RUC, SIFEN): en una instalación con otra
moneda (p. ej. R$ en Brasil) el área no aparece.
"""
from flask import Blueprint

from app.services.contador_permisos import PERMISO_AREA_CONTADOR
from app.utils.helpers import config_moneda

contador_bp = Blueprint('contador', __name__)

SIMBOLOS_GUARANI = ('₲', 'Gs', 'Gs.')


def instalacion_paraguaya():
    moneda = config_moneda()
    return moneda.get('locale') == 'es-PY' and moneda.get('simbolo') in SIMBOLOS_GUARANI


def puede_ver_area_contador(usuario):
    if not instalacion_paraguaya():
        return False
    return bool(usuario.es_admin()
                or usuario.tiene_permiso(PERMISO_AREA_CONTADOR)
                or usuario.tiene_permiso('ver_reportes')
                or usuario.tiene_permiso('ver_caja'))


@contador_bp.app_context_processor
def _permisos_en_plantillas():
    # Funciones, no booleanos: se evalúan sólo en las plantillas que las usan.
    return {'puede_ver_area_contador': puede_ver_area_contador}


from . import resumen_iva  # noqa: E402,F401

__all__ = ['contador_bp', 'instalacion_paraguaya', 'puede_ver_area_contador']
