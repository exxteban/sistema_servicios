"""Interfaz que ve el resto del sistema."""

from abc import ABC, abstractmethod

NO_DISPONIBLE = 'Esta operación no está disponible para el proveedor seleccionado.'


class ProveedorFE(ABC):
    # Vista previa XML y el circuito manual generar→firmar→QR→enviar son del
    # motor propio. El resto del sistema pregunta estas banderas, no el nombre.
    permite_herramientas_propias = False
    # El correlativo por establecimiento/punto lo lleva el emisor en los dos
    # modos: la API externa también exige `document_number` al dar de alta.
    usa_numeracion_local = True
    # Por defecto no: la pantalla ofrece el botón de acreditar sólo cuando el
    # proveedor activo lo sostiene. El motor propio lo pone en True; la API
    # sigue en False hasta que su borde acepte `document_type` 5.
    emite_notas_credito = False
    # El evento de inutilización lo emiten los dos proveedores, cada uno por
    # su camino. Es bandera propia y no `permite_herramientas_propias`: el
    # número quemado no es parte del circuito manual generar→firmar→QR→enviar,
    # y colgarlo de esa bandera dejaba al modo API sin forma de justificar el
    # hueco del timbrado ante la DNIT.
    permite_inutilizar = False

    @abstractmethod
    def emitir(self, venta):
        """Devuelve (documento, error)."""

    @abstractmethod
    def consultar(self, documento):
        """Devuelve (respuesta, error)."""

    @abstractmethod
    def cancelar(self, documento, motivo):
        """Devuelve (documento, error)."""

    def inutilizar(self, documento, motivo):
        """Informa a SIFEN un número quemado. Devuelve (documento, error).

        No es abstracto: en modo API el evento lo emite el proveedor y de este
        lado sólo se lee el estado que informa.
        """
        return documento, NO_DISPONIBLE

    @abstractmethod
    def kude(self, venta, documento):
        """Devuelve el contexto para imprimir el comprobante."""

    @abstractmethod
    def faltantes_configuracion(self, config):
        """Etiquetas de los campos requeridos ausentes. **Nunca pega a la red.**

        Es una compuerta: la llaman cada carga del POS y cada pasada del job.
        Si preguntarle al proveedor pudiera fallar, una caída pasajera del otro
        lado apagaría el POS y el envío automático sin que nadie se entere.
        Lo que haya que consultar afuera va en `faltantes_readiness`.
        """

    def faltantes_readiness(self, config):
        """Lo anterior más lo que sólo sabe el proveedor. **Puede pegar a la red.**

        Para la pantalla de configuración y para el momento de emitir, donde
        esperar está bien y el dato evita quemar un correlativo. No va en
        ninguna compuerta.
        """
        return self.faltantes_configuracion(config)

    def avanzar(self, documento):
        """Un paso del job automático. Devuelve el error, o None si avanzó."""
        return NO_DISPONIBLE

    # --- Descargas del comprobante ---------------------------------------
    # El XML firmado es lo que necesita un cliente empresa para su crédito de
    # IVA; el PDF oficial sólo existe si lo genera el proveedor.

    def kude_pdf(self, documento):
        """Devuelve (bytes_pdf, error)."""
        return None, NO_DISPONIBLE

    def xml_documento(self, documento):
        """Devuelve (xml, error)."""
        return None, NO_DISPONIBLE

    def emitir_nota_credito(self, devolucion, motivo):
        """Emite la NC de una devolución. Devuelve (documento, error)."""
        return None, NO_DISPONIBLE

    def emitir_nota_credito_correccion(self, venta, motivo, descripcion=None):
        """NC que anula una factura mal emitida, sin devolución detrás.

        Devuelve (documento, error).
        """
        return None, NO_DISPONIBLE

    def sincronizar_emisor(self, config):
        """Trae los datos fiscales desde el proveedor. Devuelve (resumen, error)."""
        return None, NO_DISPONIBLE

    # --- Sólo motor propio ------------------------------------------------

    def generar(self, venta):
        return None, NO_DISPONIBLE

    def firmar(self, documento):
        return documento, NO_DISPONIBLE

    def generar_qr(self, documento):
        return documento, NO_DISPONIBLE

    def enviar(self, documento, forzar_fecha=False):
        return documento, NO_DISPONIBLE
