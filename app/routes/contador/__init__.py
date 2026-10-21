"""Área "Contador/a": lo que necesita el profesional de afuera para liquidar.

Portada de sistema_silvio_cel. Tiene su propio apartado en el menú lateral
porque no es parte de la caja del dueño. El rol "Contador/a"
(`ver_area_contador`) entra acá sin ver la caja ni los reportes del negocio;
también entra quien ya ve reportes o caja. Tiene el resumen de IVA del mes
con su cierre e informe, los talonarios de factura en papel, y la carga de la
factura de los gastos, del número de una venta y de la nota de crédito en papel.

Todo es IVA paraguayo (timbrado, RUC, SIFEN): en una instalación con otra
moneda (p. ej. R$ en Brasil) el área no aparece.
"""
from flask import Blueprint

from app.services.contador_permisos import PERMISO_AREA_CONTADOR, instalacion_paraguaya

contador_bp = Blueprint('contador', __name__)


def puede_ver_area_contador(usuario):
    if not instalacion_paraguaya():
        return False
    return bool(usuario.es_admin()
                or usuario.tiene_permiso(PERMISO_AREA_CONTADOR)
                or usuario.tiene_permiso('ver_reportes')
                or usuario.tiene_permiso('ver_caja'))


def puede_gestionar_talonarios(usuario):
    if not instalacion_paraguaya():
        return False
    return bool(usuario.es_admin() or usuario.tiene_permiso('editar_configuracion'))


def puede_corregir_numero_factura(usuario):
    if not instalacion_paraguaya():
        return False
    return bool(usuario.es_admin() or usuario.tiene_permiso('anular_venta')
                or usuario.tiene_permiso('editar_configuracion'))


def puede_cargar_factura_de_gasto(usuario):
    if not instalacion_paraguaya():
        return False
    return bool(usuario.es_admin() or usuario.tiene_permiso('registrar_pago_gasto_corriente')
                or usuario.tiene_permiso('editar_gastos_corrientes'))


@contador_bp.app_context_processor
def _permisos_en_plantillas():
    # Funciones, no booleanos: se evalúan sólo en las plantillas que las usan.
    return {
        'puede_ver_area_contador': puede_ver_area_contador,
        'puede_gestionar_talonarios': puede_gestionar_talonarios,
        'puede_corregir_numero_factura': puede_corregir_numero_factura,
        'puede_cargar_factura_de_gasto': puede_cargar_factura_de_gasto,
    }


from . import gastos, notas_credito, resumen_iva, talonarios  # noqa: E402,F401

__all__ = ['contador_bp', 'instalacion_paraguaya', 'puede_cargar_factura_de_gasto', 'puede_corregir_numero_factura',
           'puede_gestionar_talonarios', 'puede_ver_area_contador']
