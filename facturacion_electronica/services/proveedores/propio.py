"""Adaptador del circuito existente; la implementación fiscal sigue intacta."""

from facturacion_electronica import ESTADO_ENVIADO
from facturacion_electronica.services.emision_service import (
    cancelar_documento,
    consultar_documento,
    emitir_nota_credito,
    emitir_nota_credito_correccion,
    emitir_para_pos,
    inutilizar_documento,
    enviar_documento,
    firmar_documento,
    generar_documento,
    generar_nota_credito,
    generar_qr_documento,
)
from facturacion_electronica.services.envio_lote import lote_recien_enviado
from facturacion_electronica.services.kude_service import construir_contexto_kude
from facturacion_electronica.services.proveedores.contrato import ProveedorFE


class ProveedorPropio(ProveedorFE):
    permite_herramientas_propias = True
    emite_notas_credito = True
    permite_inutilizar = True

    def emitir(self, venta):
        return emitir_para_pos(venta)

    def consultar(self, documento):
        return consultar_documento(documento)

    def cancelar(self, documento, motivo):
        return cancelar_documento(documento, motivo)

    def inutilizar(self, documento, motivo):
        return inutilizar_documento(documento, motivo)

    def kude(self, venta, documento):
        return construir_contexto_kude(venta, documento)

    def xml_documento(self, documento):
        """El XML con QR es el que se le entrega al comprador; si todavía no
        está, sirve el firmado."""
        xml = (documento.xml_qr or documento.xml_firmado) if documento else None
        if not xml:
            return None, 'El documento todavía no está firmado.'
        return xml, None

    def faltantes_configuracion(self, config):
        from facturacion_electronica.services.validacion import REQUISITOS
        return [etiqueta for cumple, etiqueta in REQUISITOS if not cumple(config)]

    def generar(self, venta):
        return generar_documento(venta)

    def firmar(self, documento):
        return firmar_documento(documento)

    def generar_qr(self, documento):
        return generar_qr_documento(documento)

    def enviar(self, documento, forzar_fecha=False):
        return enviar_documento(documento, forzar_fecha=forzar_fecha)

    def emitir_nota_credito(self, devolucion, motivo):
        return emitir_nota_credito(devolucion, motivo)

    def emitir_nota_credito_correccion(self, venta, motivo, descripcion=None):
        return emitir_nota_credito_correccion(venta, motivo, descripcion)

    def avanzar(self, documento):
        if not documento.xml:
            error = self._regenerar(documento)
            if error:
                return error

        if not documento.xml_firmado:
            _doc, error = self.firmar(documento)
            if error:
                return error

        if not documento.xml_qr:
            _doc, error = self.generar_qr(documento)
            if error:
                return error

        if documento.estado == ESTADO_ENVIADO:
            if lote_recien_enviado(documento):
                # Sin error: no es un fallo, es esperar lo que pide la DNIT.
                return None
            _respuesta, error = self.consultar(documento)
            return error

        _doc, error = self.enviar(documento)
        return error

    def _regenerar(self, documento):
        """Vuelve a armar el XML de un documento que quedó sin él.

        La nota de crédito va por su propio camino: `generar_documento` mira la
        **factura** de la venta, así que regenerar una NC por ahí dejaba la NC
        intacta y sin XML, y el job la reintentaba en cada pasada para siempre.
        """
        if documento.es_nota_credito:
            from app.models.devolucion import Devolucion
            from app import db

            devolucion = db.session.get(Devolucion, documento.id_devolucion)
            if devolucion is None:
                return 'La devolución de esta nota de crédito ya no existe.'
            _doc, error = generar_nota_credito(devolucion, documento.nc_motivo)
            return error

        venta = documento.venta
        if venta is None:
            return 'La venta asociada ya no existe.'
        _doc, error = self.generar(venta)
        return error
