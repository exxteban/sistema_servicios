"""Punto único por el que el resto del sistema habla con el proveedor activo.

Ninguna ruta, ni el POS, ni el job preguntan qué proveedor está configurado:
llaman a estas funciones y el switch queda de este lado.

Lo que actúa sobre un documento que ya salió (enviar, consultar, avanzar,
cancelar, inutilizar) pasa antes por `_de_otro_proveedor`: un documento sólo
lo sigue el proveedor que lo transmitió (ver `pertenencia.py`).

Emitir y generar reciben la venta, no el documento, pero también pasan: con
la API activa, "Reintentar emisión" sobre una factura que el motor propio
había mandado se la daba a la API como si fuera nueva (2026-10-05, 0000204).
"""
from facturacion_electronica.services.proveedores import obtener_proveedor
from facturacion_electronica.services.proveedores.pertenencia import error_de_otro_proveedor


def _de_otro_proveedor(documento):
    from facturacion_electronica.services.config_service import obtener_configuracion

    return error_de_otro_proveedor(documento, obtener_configuracion().proveedor)


def _documento_de_otro_proveedor(venta):
    """(documento, error) si la venta ya tiene un DE del otro proveedor; si no, (None, None)."""
    from facturacion_electronica.services.documento_consulta import obtener_documento

    documento = obtener_documento(venta.id_venta) if venta is not None else None
    error = _de_otro_proveedor(documento)
    return (documento, error) if error else (None, None)


def emitir_para_pos(venta):
    documento, error = _documento_de_otro_proveedor(venta)
    if error:
        return documento, error
    return obtener_proveedor().emitir(venta)


def generar_documento(venta):
    documento, error = _documento_de_otro_proveedor(venta)
    if error:
        return documento, error
    return obtener_proveedor().generar(venta)


def firmar_documento(documento):
    return obtener_proveedor().firmar(documento)


def generar_qr_documento(documento):
    return obtener_proveedor().generar_qr(documento)


def enviar_documento(documento, forzar_fecha=False):
    error = _de_otro_proveedor(documento)
    if error:
        return documento, error
    return obtener_proveedor().enviar(documento, forzar_fecha=forzar_fecha)


def consultar_documento(documento):
    error = _de_otro_proveedor(documento)
    if error:
        return None, error
    return obtener_proveedor().consultar(documento)


def cancelar_documento(documento, motivo):
    error = _de_otro_proveedor(documento)
    if error:
        return documento, error
    return obtener_proveedor().cancelar(documento, motivo)


def inutilizar_documento(documento, motivo):
    error = _de_otro_proveedor(documento)
    if error:
        return documento, error
    return obtener_proveedor().inutilizar(documento, motivo)


def construir_contexto_kude(venta, documento):
    return obtener_proveedor().kude(venta, documento)


def avanzar_documento(documento):
    # El job ya filtra por proveedor (`filtro_documentos_del_proveedor`); esto
    # cubre a quien llame directo.
    error = _de_otro_proveedor(documento)
    if error:
        return error
    return obtener_proveedor().avanzar(documento)


def kude_pdf(documento):
    return obtener_proveedor().kude_pdf(documento)


def xml_documento(documento):
    return obtener_proveedor().xml_documento(documento)


def emitir_nota_credito(devolucion, motivo):
    return obtener_proveedor().emitir_nota_credito(devolucion, motivo)


def emitir_nota_credito_correccion(venta, motivo, descripcion=None):
    return obtener_proveedor().emitir_nota_credito_correccion(venta, motivo, descripcion)


def sincronizar_emisor(config):
    return obtener_proveedor(config).sincronizar_emisor(config)


def capacidades(config=None):
    """Qué puede hacer el proveedor activo, para las rutas y la pantalla."""
    proveedor = obtener_proveedor(config)
    return {
        'herramientas_propias': proveedor.permite_herramientas_propias,
        'numeracion_local': proveedor.usa_numeracion_local,
        'notas_credito': proveedor.emite_notas_credito,
        'inutilizacion': proveedor.permite_inutilizar,
    }
