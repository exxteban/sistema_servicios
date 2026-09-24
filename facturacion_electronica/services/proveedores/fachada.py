"""Punto único por el que el resto del sistema habla con el proveedor activo.

Ninguna ruta, ni el POS, ni el job preguntan qué proveedor está configurado:
llaman a estas funciones y el switch queda de este lado.
"""
from facturacion_electronica.services.proveedores import obtener_proveedor


def emitir_para_pos(venta):
    return obtener_proveedor().emitir(venta)


def generar_documento(venta):
    return obtener_proveedor().generar(venta)


def firmar_documento(documento):
    return obtener_proveedor().firmar(documento)


def generar_qr_documento(documento):
    return obtener_proveedor().generar_qr(documento)


def enviar_documento(documento, forzar_fecha=False):
    return obtener_proveedor().enviar(documento, forzar_fecha=forzar_fecha)


def consultar_documento(documento):
    return obtener_proveedor().consultar(documento)


def cancelar_documento(documento, motivo):
    return obtener_proveedor().cancelar(documento, motivo)


def inutilizar_documento(documento, motivo):
    return obtener_proveedor().inutilizar(documento, motivo)


def construir_contexto_kude(venta, documento):
    return obtener_proveedor().kude(venta, documento)


def avanzar_documento(documento):
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
