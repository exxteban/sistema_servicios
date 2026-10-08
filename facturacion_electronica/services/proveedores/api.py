"""Proveedor de FE contra la API externa (el servicio del compañero).

Reparto de trabajo, tal como lo define su OpenAPI:

- **Ellos**: certificado, CSC, firma, CDC, QR, validación XSD, lotes y el
  diálogo SOAP con SIFEN. Los datos del emisor y el timbrado viven de su lado
  (`GET/PUT /sifen/me/`).
- **Nosotros**: el **número** del documento. `document_number` es obligatorio
  en el alta, así que `SecuenciaNumeracionDE` **sigue encendida** también en
  este modo (el plan suponía lo contrario; el contrato dice esto).

El circuito de un documento es asíncrono: `emitir` da de alta y el job mira
el estado. Nada acá lanza: todo devuelve (…, error) como el resto del módulo.
Perfil/timbrado: `api_perfil`. Copia del DE remoto: `api_documento`.
"""
import json
from datetime import datetime

from app import db
from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_CANCELADO,
    ESTADO_ERROR,
    ESTADO_RECHAZADO,
    ESTADOS_NO_REGENERABLES,
    TIPO_FACTURA as TIPO_DOC_FACTURA,
    TIPO_NOTA_CREDITO,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.config_service import obtener_configuracion
from facturacion_electronica.services.emision_service import (
    HORAS_LIMITE_CANCELACION,
    nota_credito_de_correccion,
    obtener_documento,
)
from facturacion_electronica.services.guarda import (
    error_devolucion_no_acreditable,
    error_original_no_acreditable,
    error_venta_no_facturable,
)
from facturacion_electronica.services.kude_service import construir_contexto_kude
from facturacion_electronica.services.nota_credito import (
    lineas_de_devolucion,
    lineas_de_venta,
    motivo_valido,
)
from facturacion_electronica.services.numeracion_service import reservar_numero
from facturacion_electronica.services.proveedores import api_client
from facturacion_electronica.services.proveedores.api_cancelacion import cancelar_documento
from facturacion_electronica.services.proveedores.api_correccion import corregir_rechazado
from facturacion_electronica.services.proveedores.api_documento import (
    ESTADOS_API,
    adoptar_remoto,
    aplicar_remoto,
    bloqueo_entrega_inicial,
    buscar_remoto,
    clave_idempotencia,
    completar_protocolo,
    descargar_kude_pdf,
    liberar_numero_tomado,
    descargar_xml,
    MENSAJE_SANDBOX,
    transmite,
)
from facturacion_electronica.services.proveedores.api_inutilizacion import inutilizar_numero
from facturacion_electronica.services.proveedores.api_timbrado import resolver_timbrado_nc
from facturacion_electronica.services.proveedores.api_nota_credito import armar_cuerpo_nc, reabrir_nc_rechazada
from facturacion_electronica.services.proveedores.api_payload import construir_emision_api
from facturacion_electronica.services.proveedores.api_perfil import (
    aplicar_perfil_al_config,
    congelar_identidad,
    faltantes_locales,
    faltantes_readiness_api,
    normalizar_codigo,
    obtener_perfil,
    olvidar_perfil,
    resolver_timbrado,
    sincronizar_ambiente,
)
from facturacion_electronica.services.proveedores.contrato import ProveedorFE
from facturacion_electronica.services.validacion import (
    validar_cliente,
    validar_monto_innominado,
    validar_receptor_api,
)

TIPO_FACTURA = TIPO_DOC_FACTURA

# La API acepta la nota de crédito (`document_type=5`) desde su 1.5.0; se
# encendió el 2026-09-26. Necesita un timbrado de tipo 5 cargado en la API. La
# NC a un receptor innominado la frena antes `error_original_no_acreditable`.
API_EMITE_NOTAS_CREDITO = True

NC_NO_HABILITADA = (
    'Las notas de crédito por la API de facturación electrónica todavía no están '
    'habilitadas: el proveedor aún no transmitió ninguna a SIFEN. Mientras tanto, si la '
    f'factura tiene menos de {HORAS_LIMITE_CANCELACION}h se la puede anular en SIFEN; si ya '
    'pasaron, hay que esperar a que se habiliten.'
)


class ProveedorApi(ProveedorFE):
    """Implementación de la interfaz contra la API externa."""

    permite_herramientas_propias = False
    usa_numeracion_local = True
    emite_notas_credito = API_EMITE_NOTAS_CREDITO
    # El número lo ponemos nosotros, así que el hueco del timbrado también es
    # nuestro problema: su API expone el evento en `POST /sifen/inutilizations/`.
    permite_inutilizar = True

    def faltantes_configuracion(self, config):
        """Sin red. La llaman el render del POS y cada pasada del job.

        El certificado y el CSC viven del lado de la API y no se pueden saber
        sin preguntar; preguntarlos acá ataba el POS y el envío automático a
        que su servicio conteste en ese instante.
        """
        return faltantes_locales(config)

    def faltantes_readiness(self, config):
        """Con red: agrega certificado y CSC del perfil remoto."""
        return faltantes_readiness_api(config)

    def sincronizar_emisor(self, config):
        """Trae los datos fiscales de la API a nuestra copia. Devuelve (resumen, error)."""
        perfil, error = obtener_perfil(config, refrescar=True)
        if error:
            return None, error
        return aplicar_perfil_al_config(config, perfil), None

    def emitir(self, venta):
        """Alta del DE en la API: firma, CDC y QR quedan hechos del otro lado."""
        from app.services.caja_transacciones import bloquear_caja_de_venta

        bloquear_caja_de_venta(venta)
        error_venta = error_venta_no_facturable(venta)
        if error_venta:
            documento = obtener_documento(venta.id_venta)
            if documento is not None and documento.api_documento_id:
                return documento, error_venta
            if documento is not None and documento.estado not in ESTADOS_NO_REGENERABLES:
                return self._fallar(documento, error_venta)
            return documento, error_venta

        documento = obtener_documento(venta.id_venta)
        if documento is not None and documento.estado in ESTADOS_NO_REGENERABLES:
            if documento.estado != ESTADO_CANCELADO:
                return documento, f'El documento ya está {documento.estado}; no se puede regenerar.'
            documento = None
        if documento is None:
            from facturacion_electronica.services.data_builder import generar_codigo_seguridad

            documento = DocumentoElectronico(
                id_venta=venta.id_venta,
                codigo_seguridad=generar_codigo_seguridad(),
            )
            db.session.add(documento)

        error_cliente = (
            validar_cliente(venta.cliente)
            or validar_receptor_api(venta.cliente)
            or validar_monto_innominado(venta.cliente, venta.total)
        )
        if error_cliente:
            documento.estado = ESTADO_ERROR
            documento.respuesta_mensaje = error_cliente
            db.session.commit()
            return documento, error_cliente

        error_credito = bloqueo_entrega_inicial(venta)
        if error_credito:
            documento.estado = ESTADO_ERROR
            documento.respuesta_mensaje = error_credito
            db.session.commit()
            return documento, error_credito

        config = obtener_configuracion()
        faltantes = self.faltantes_readiness(config)
        if faltantes:
            documento.estado = ESTADO_ERROR
            documento.respuesta_mensaje = 'Configuración incompleta: ' + ', '.join(faltantes)
            db.session.commit()
            return documento, documento.respuesta_mensaje

        establecimiento = normalizar_codigo(config.establecimiento)
        punto = normalizar_codigo(config.punto_expedicion)
        if not documento.numero:
            numero, error_numero = reservar_numero(establecimiento, punto)
            if error_numero:
                documento.estado = ESTADO_ERROR
                documento.respuesta_mensaje = error_numero
                db.session.commit()
                return documento, error_numero
            documento.numero = numero
        documento.establecimiento = establecimiento
        documento.punto = punto
        documento.tipo_documento = TIPO_FACTURA
        if not documento.fecha_generado:
            documento.fecha_generado = datetime.utcnow()
        clave_idempotencia(documento)
        db.session.commit()

        return self._alta_remota(config, documento, venta)

    def emitir_nota_credito(self, devolucion, motivo):
        """Emite la NC de una devolución contra la factura de esa venta."""
        if not API_EMITE_NOTAS_CREDITO:
            return None, NC_NO_HABILITADA
        if devolucion is None:
            return None, 'No hay devolución para acreditar.'
        error_devolucion = error_devolucion_no_acreditable(devolucion)
        if error_devolucion:
            return None, error_devolucion

        original = obtener_documento(devolucion.id_venta)
        error_original = error_original_no_acreditable(original)
        if error_original:
            return None, error_original

        existente = DocumentoElectronico.query.filter_by(
            id_devolucion=devolucion.id_devolucion, tipo_documento=TIPO_NOTA_CREDITO,
        ).order_by(DocumentoElectronico.id.desc()).first()
        if existente is not None and existente.estado not in (ESTADO_ERROR, ESTADO_RECHAZADO):
            return existente, (f'Esta devolución ya tiene una nota de crédito '
                               f'({existente.estado}).')

        codigo, descripcion = motivo_valido(motivo)
        if codigo is None:
            return None, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

        lineas = lineas_de_devolucion(devolucion)
        if not lineas:
            return None, 'La devolución no tiene ítems.'

        config = obtener_configuracion()
        faltantes = self.faltantes_readiness(config)
        if faltantes:
            return None, 'Configuración incompleta: ' + ', '.join(faltantes)

        documento = existente if existente is not None else DocumentoElectronico(
            id_venta=devolucion.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
            id_devolucion=devolucion.id_devolucion,
        )
        documento.id_documento_asociado = original.id
        documento.nc_motivo = codigo
        documento.nc_motivo_desc = descripcion
        if existente is None:
            db.session.add(documento)

        error_numero = self._asegurar_numero_nc(config, documento)
        if error_numero:
            return documento, error_numero
        if not documento.fecha_generado:
            documento.fecha_generado = datetime.utcnow()
        clave_idempotencia(documento)
        db.session.commit()

        return self._alta_remota_nc(config, documento, lineas, original)

    def emitir_nota_credito_correccion(self, venta, motivo, descripcion=None):
        """NC por el total de una factura mal emitida, sin devolución detrás.

        Es la salida cuando pasaron las 48h y SIFEN ya no admite el evento de
        cancelación. No mueve plata ni stock: la NC respalda la corrección
        fiscal y el cobro se revierte anulando la venta después.

        `descripcion` se acepta por firma —la ruta la manda— pero no viaja ni
        se guarda: el `credit_debit` de su API sólo lleva el motivo del
        catálogo y su descripción fija, y no hay columna donde ponerla sin un
        ALTER en cada instalación. En el motor propio va al texto libre del
        XML; acá no hay texto libre.
        """
        if not API_EMITE_NOTAS_CREDITO:
            return None, NC_NO_HABILITADA
        if venta is None:
            return None, 'La venta ya no existe.'

        original = obtener_documento(venta.id_venta)
        error_original = error_original_no_acreditable(original)
        if error_original:
            return None, error_original

        existente = nota_credito_de_correccion(venta.id_venta)
        if existente is not None and existente.estado == ESTADO_CANCELADO:
            # La NC anterior se dio de baja: la factura volvió a quedar viva y
            # se puede acreditar de nuevo, con número nuevo.
            existente = None
        elif existente is not None and existente.estado not in (ESTADO_ERROR, ESTADO_RECHAZADO):
            return existente, (f'La factura ya tiene una nota de crédito de anulación '
                               f'({existente.estado}); no se puede emitir otra.')

        codigo, descripcion_motivo = motivo_valido(motivo)
        if codigo is None and existente is not None:
            codigo, descripcion_motivo = motivo_valido(existente.nc_motivo)
        if codigo is None:
            return existente, 'Elegí un motivo del catálogo de SIFEN para la nota de crédito.'

        lineas = lineas_de_venta(venta)
        if not lineas:
            return existente, 'La venta no tiene ítems para acreditar.'

        config = obtener_configuracion()
        faltantes = self.faltantes_readiness(config)
        if faltantes:
            return existente, 'Configuración incompleta: ' + ', '.join(faltantes)

        documento = existente if existente is not None else DocumentoElectronico(
            id_venta=venta.id_venta,
            tipo_documento=TIPO_NOTA_CREDITO,
        )
        documento.id_documento_asociado = original.id
        documento.nc_motivo = codigo
        documento.nc_motivo_desc = descripcion_motivo
        if existente is None:
            db.session.add(documento)

        error_numero = self._asegurar_numero_nc(config, documento)
        if error_numero:
            return documento, error_numero
        if not documento.fecha_generado:
            documento.fecha_generado = datetime.utcnow()
        clave_idempotencia(documento)
        db.session.commit()

        return self._alta_remota_nc(config, documento, lineas, original)

    def _alta_remota_nc(self, config, documento, lineas, original):
        """Alta de una NC, venga de una devolución o de la anulación de la factura.

        Recibe las líneas ya armadas: es lo único que cambia entre las dos: la
        de una devolución acredita lo que volvió y la de anulación, la factura
        entera. Todo lo demás —timbrado de tipo 5, identidad congelada,
        idempotencia, recuperación del alta perdida— es idéntico, y tenerlo
        dos veces era garantizar que un arreglo entrara en una sola.
        """
        if not API_EMITE_NOTAS_CREDITO:
            return self._fallar(documento, NC_NO_HABILITADA)
        if documento.api_documento_id and not reabrir_nc_rechazada(documento):
            return self._refrescar(config, documento)

        perfil, error = obtener_perfil(config)
        if error:
            return self._fallar(documento, error)
        sincronizar_ambiente(config, perfil)

        timbrado_id, error = resolver_timbrado_nc(config, perfil)
        if error:
            return self._fallar(documento, error)
        congelar_identidad(documento, config, perfil, timbrado_id)

        venta = documento.venta
        if venta is None:
            return self._fallar(documento, 'La venta asociada ya no existe.')

        cuerpo, error = armar_cuerpo_nc(config, documento, original, venta, lineas, timbrado_id)
        if error:
            return self._fallar(documento, error)
        remoto, error = api_client.solicitar(
            config, 'POST', '/sifen/electronic-documents/',
            json=cuerpo,
            headers={'Idempotency-Key': clave_idempotencia(documento)},
            timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
        )
        if error:
            existente, _error_busqueda = buscar_remoto(config, documento)
            if existente:
                adoptar_remoto(config, documento, existente)
                return documento, None
            return self._fallar(documento, liberar_numero_tomado(documento, error))

        aplicar_remoto(documento, remoto)
        return documento, None

    def _alta_remota(self, config, documento, venta):
        """POST del documento, con recuperación si ya existía del otro lado.

        Una factura que SIFEN rechazó no se refresca y nada más: se corrige y
        se reenvía con el mismo número y CDC (ver `api_correccion`).
        """
        corrige = documento.estado == ESTADO_RECHAZADO and documento.tipo_documento == TIPO_FACTURA
        if documento.api_documento_id and not corrige:
            return self._refrescar(config, documento)

        perfil, error = obtener_perfil(config)
        if error:
            return self._fallar(documento, error)
        sincronizar_ambiente(config, perfil)

        timbrado_id, error = resolver_timbrado(config, perfil)
        if error:
            return self._fallar(documento, error)
        congelar_identidad(documento, config, perfil, timbrado_id)

        cuerpo = construir_emision_api(venta, documento, timbrado_id)
        if corrige:
            return self._corregir(config, documento, cuerpo)
        remoto, error = api_client.solicitar(
            config, 'POST', '/sifen/electronic-documents/',
            json=cuerpo,
            headers={'Idempotency-Key': clave_idempotencia(documento)},
            timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
        )
        if error:
            existente, _error_busqueda = buscar_remoto(config, documento)
            if existente:
                adoptar_remoto(config, documento, existente)
                return documento, None
            return self._fallar(documento, liberar_numero_tomado(documento, error))

        aplicar_remoto(documento, remoto)
        return documento, None

    def _corregir(self, config, documento, cuerpo):
        """Reenvía la factura rechazada. Si falla, sigue rechazada.

        No pasa por `_fallar`: el documento está `REJECTED` del otro lado y
        marcarlo 'error' acá lo metería en la rueda del job sin nada que hacer.
        Si la API dice que ya no se puede corregir (alguien lo corrigió por
        otro lado, o no está más rechazado) se relee para quedar en su estado.
        """
        remoto, error = corregir_rechazado(config, documento, cuerpo)
        if error:
            if 'document_not_correctable' in error:
                self._refrescar(config, documento)
            documento.respuesta_mensaje = f'No se pudo corregir y reenviar: {error}'[:2000]
            db.session.commit()
            return documento, error
        # El lote viejo es el del rechazo; el nuevo lo informa la API al procesarlo.
        documento.api_lote_id = None
        aplicar_remoto(documento, remoto)
        return documento, None

    def _asegurar_numero_nc(self, config, documento):
        """Reserva el correlativo de la NC si todavía no lo tiene.

        Va acá y no en el alta porque los dos caminos —la emisión manual y el
        reintento del job— tienen que pasar por el mismo lugar: cuando sólo lo
        hacía la emisión, un fallo al reservar dejaba el documento sin número
        y el reintento posteaba `document_number: None`.
        """
        establecimiento = normalizar_codigo(config.establecimiento)
        punto = normalizar_codigo(config.punto_expedicion)
        if not documento.numero:
            numero, error_numero = reservar_numero(establecimiento, punto, TIPO_NOTA_CREDITO)
            if error_numero:
                documento.estado = ESTADO_ERROR
                documento.respuesta_mensaje = error_numero
                db.session.commit()
                return error_numero
            documento.numero = numero
        documento.establecimiento = establecimiento
        documento.punto = punto
        return None

    def _reintentar_nota_credito(self, config, documento):
        """Segundo intento de una NC que no llegó a existir del otro lado.

        Repite las mismas precondiciones que la emisión manual: entre el
        primer intento y éste pudieron anular la devolución o pedir la baja de
        la factura, y el job no puede ser la puerta de atrás que igual la emite.
        """
        from app.models.devolucion import Devolucion

        original = db.session.get(DocumentoElectronico, documento.id_documento_asociado or 0)
        error_original = error_original_no_acreditable(original)
        if error_original:
            return error_original

        if documento.id_devolucion is None:
            # NC de anulación: no hay devolución detrás y las líneas son la
            # factura entera. Sin esta rama el job la daba por huérfana en cada
            # pasada ("la devolución ya no existe") y nunca la reintentaba.
            venta = documento.venta
            if venta is None:
                return 'La venta asociada ya no existe.'
            lineas = lineas_de_venta(venta)
            if not lineas:
                return 'La venta no tiene ítems para acreditar.'
        else:
            devolucion = db.session.get(Devolucion, documento.id_devolucion)
            error_devolucion = error_devolucion_no_acreditable(devolucion)
            if error_devolucion:
                return error_devolucion
            lineas = lineas_de_devolucion(devolucion)

        error_numero = self._asegurar_numero_nc(config, documento)
        if error_numero:
            return error_numero

        _documento, error = self._alta_remota_nc(config, documento, lineas, original)
        return error

    def _fallar(self, documento, error):
        documento.estado = ESTADO_ERROR
        documento.respuesta_mensaje = error
        db.session.commit()
        return documento, error

    def _refrescar(self, config, documento):
        """Relee el documento en la API y persiste el estado. (documento, error)."""
        if not documento.api_documento_id:
            return documento, 'El documento todavía no fue dado de alta en la API.'
        remoto, error = api_client.solicitar(
            config, 'GET', f'/sifen/electronic-documents/{documento.api_documento_id}/'
        )
        if error:
            return documento, error
        estado = adoptar_remoto(config, documento, remoto)
        if estado == ESTADO_APROBADO:
            completar_protocolo(config, documento)
        return documento, None

    def consultar(self, documento):
        """Refresca el estado contra la API. Devuelve (respuesta, error)."""
        if documento is None:
            return None, 'No hay documento para consultar.'
        config = obtener_configuracion()
        if not documento.api_documento_id:
            existente, error = buscar_remoto(config, documento)
            if error:
                return None, error
            if existente is None:
                return None, 'El documento todavía no fue dado de alta en la API.'
            adoptar_remoto(config, documento, existente)
            return existente, None
        _documento, error = self._refrescar(config, documento)
        if error:
            return None, error
        return json.loads(documento.respuesta_raw or '{}'), None

    def cancelar(self, documento, motivo):
        config = obtener_configuracion()
        return cancelar_documento(
            config, documento, motivo,
            refrescar=lambda doc: self._refrescar(config, doc),
        )

    def inutilizar(self, documento, motivo):
        """Informa el número quemado con el evento de inutilización de la API."""
        if documento is None:
            return documento, 'No hay documento para inutilizar.'
        config = obtener_configuracion()
        return inutilizar_numero(
            config, documento, motivo,
            refrescar=lambda doc: self._refrescar(config, doc),
        )

    def kude(self, venta, documento):
        """Se imprime el KuDE propio: el del proveedor es un PDF A4 y la caja
        tiene una térmica de 80mm. El PDF oficial se descarga aparte."""
        return construir_contexto_kude(venta, documento)

    def kude_pdf(self, documento):
        return descargar_kude_pdf(obtener_configuracion(), documento)

    def xml_documento(self, documento):
        return descargar_xml(obtener_configuracion(), documento)

    def avanzar(self, documento):
        """Un paso del circuito asíncrono. Devuelve el error, o None si avanzó."""
        config = obtener_configuracion()

        if not documento.api_documento_id or documento.estado == ESTADO_RECHAZADO:  # corrección
            venta = documento.venta
            if venta is None:
                return 'La venta asociada ya no existe.'
            if documento.tipo_documento == TIPO_NOTA_CREDITO:
                return self._reintentar_nota_credito(config, documento)
            _documento, error = self.emitir(venta)
            return error

        _documento, error = self._refrescar(config, documento)
        if error:
            return error

        estado_api = (documento.respuesta_codigo or '').upper()

        if estado_api in ('DRAFT', 'PREPARING'):
            _respuesta, error = api_client.solicitar(
                config, 'POST',
                f'/sifen/electronic-documents/{documento.api_documento_id}/prepare/',
                json={'confirm': True}, timeout=api_client.TIMEOUT_EMISION_SEGUNDOS,
            )
            return error

        if estado_api == 'PENDING_BATCH' and not transmite(documento):
            _documento, error = self._fallar(documento, MENSAJE_SANDBOX)
            return error

        if estado_api == 'RETRYABLE_ERROR':
            return documento.respuesta_mensaje or 'La API marcó el documento como error reintentable.'

        return None


__all__ = ['ProveedorApi', 'obtener_perfil', 'resolver_timbrado', 'olvidar_perfil', 'ESTADOS_API']
