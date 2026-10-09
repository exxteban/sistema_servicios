"""Qué se puede hacer con el documento electrónico de una venta, ahora mismo.

Vive acá y no dentro de la plantilla por dos motivos que ya mordieron antes:

- Las condiciones estaban repartidas en los `{% if %}` de la vista previa, y
  llevarlas al detalle de venta habría sido copiarlas. Dos copias de una regla
  fiscal se desincronizan: la pantalla termina ofreciendo un botón que el
  servicio rechaza, y el usuario no entiende por qué.
- La ventana de 48h de la cancelación **no** se miraba en la pantalla, sólo en
  `cancelar_documento`. Así el botón aparecía siempre y fallaba recién al
  apretarlo. Acá se resuelve antes, y cuando el plazo venció se ofrece el
  camino que sí corresponde: la nota de crédito.
"""
from datetime import datetime, timedelta

from facturacion_electronica import (
    ESTADO_APROBADO,
    ESTADO_ENVIADO,
    ESTADO_ERROR,
    ESTADO_FIRMADO,
    ESTADO_GENERADO,
    ESTADO_RECHAZADO,
)

# Estados en los que el numero se reservo pero el DE nunca llego a SIFEN.
ESTADOS_NUMERO_QUEMADO = (ESTADO_GENERADO, ESTADO_FIRMADO, ESTADO_RECHAZADO, ESTADO_ERROR)

# Estados con un KuDE que se le puede volver a dar al cliente. 'firmado' entra
# porque en la API es PENDING_BATCH: el POS ya lo imprime en ese estado. Un
# cancelado o rechazado no: ese papel ya no respalda nada.
ESTADOS_KUDE_REIMPRIMIBLE = (ESTADO_FIRMADO, ESTADO_ENVIADO, ESTADO_APROBADO)


def _numero_definitivamente_perdido(documento, venta):
    """True si ese número ya no va a poder usarse nunca.

    Es la diferencia entre "todavía no salió" y "no va a salir", y decide si
    se ofrece inutilizar. Importa mucho: los estados `generado` y `firmado`
    son, casi siempre, un documento que el job va a transmitir en la próxima
    pasada. Ofrecer el botón ahí es invitar a quemar un número que iba a salir
    bien tres minutos después, y el número quemado no se recupera.

    Nadie tiene que averiguar si el documento llegó a SIFEN: el sistema lo
    sabe, y sólo entonces pide la decisión.
    """
    from facturacion_electronica import ESTADOS_TRANSMITIDOS, SIN_REINTENTO
    from facturacion_electronica.services.guarda import fuera_de_plazo_de_transmision, venta_anulada

    if documento.estado in ESTADOS_TRANSMITIDOS:
        # Salió hacia SIFEN (aprobado, cancelado...): el número está usado, no
        # perdido. Con la venta anulada después de cancelar la factura, esto
        # ofrecía inutilizar un número que SIFEN ya tiene registrado.
        return False
    if documento.estado == ESTADO_RECHAZADO:
        # SIFEN lo vio y no lo aceptó, pero el número no se pierde por eso:
        # se corrige y se reenvía con el mismo (el motor propio regenera el DE
        # conservando el número y la API tiene `correct/`). Se pierde recién
        # cuando ya no se puede reenviar: la venta se anuló o pasaron las 720h.
        return venta_anulada(venta) or fuera_de_plazo_de_transmision(venta)
    if documento.reintentar_despues == SIN_REINTENTO:
        # El job lo declaró definitivo (720h vencidas).
        return True
    if venta_anulada(venta):
        # La venta ya no existe comercialmente: su DE no se va a transmitir.
        return True
    return False


def _acciones_sin_documento(venta, puede_operar):
    """La venta no se facturó. ¿Se puede facturar ahora? Devuelve None si no.

    El caso real: se vendió sin factura y el cliente la pide después —al rato,
    al otro día, cuando la contadora se la reclama—. El circuito ya existía
    (`emitir_completo` no pregunta si la venta es de hoy), pero el botón sólo
    estaba en la vista previa de Facturación electrónica, que además pide
    permiso de configuración: desde la venta no había ningún camino, y había
    que conocer la URL.

    El límite no es nuestro: la factura declara la fecha de la **venta**
    (`dFeEmiDE`), no la de hoy, y SIFEN sólo acepta transmitir dentro de las
    72h de esa fecha. Pasado ese plazo no hay forma de facturar esa venta, así
    que tampoco se ofrece el botón: mejor que no aparezca a que aparezca y
    falle después de quemar un número.
    """
    from facturacion_electronica.services.guarda import fuera_de_plazo_de_envio, venta_anulada

    if not puede_operar:
        # Con documento el panel muestra el estado aunque no haya permiso; sin
        # documento no hay estado que mostrar, así que no se dibuja nada.
        return None
    if venta_anulada(venta) or (venta.estado or '').strip().lower() != 'completada':
        return None

    if fuera_de_plazo_de_envio(venta):
        return None

    return {
        'documento': None,
        'notas': [],
        'devoluciones': [],
        'devoluciones_pendientes': [],
        'puede_operar': bool(puede_operar),
        'puede_emitir': bool(puede_operar),
        'puede_corregir_rechazo': False,
        'puede_cancelar': False,
        'puede_anular_con_nc': False,
        'plazo_cancelacion_vencido': False,
        'puede_acreditar_devolucion': False,
        'puede_inutilizar': False,
        'envio_en_curso': False,
        'tiene_kude': False,
        'tiene_xml': False,
    }


def acciones_para_venta(venta, puede_operar=False):
    """Estado del DE y acciones disponibles, para la pantalla de la venta.

    `puede_operar` es el permiso de facturación electrónica ya resuelto por
    quien llama: sin él se muestra el estado pero ningún botón, para no
    ofrecerle a un cajero una acción que la ruta le va a negar.

    Devuelve None cuando no hay nada que mostrar ni que ofrecer: ni documento
    emitido, ni posibilidad de emitirlo. Así la plantilla no dibuja un panel
    vacío en las miles de ventas viejas sin factura.

    Con la venta ya facturada devuelve el estado y sus acciones. **Sin
    documento pero todavía facturable** devuelve `puede_emitir`: es el caso de
    "vendí y recién ahora me piden la factura", que hasta ahora existía en el
    código pero no tenía botón en ninguna pantalla.
    """
    from facturacion_electronica.services.emision_service import (
        HORAS_LIMITE_CANCELACION,
        fecha_emision,
        notas_credito,
        obtener_documento,
    )
    from facturacion_electronica.services.nota_credito import resumen_devoluciones
    from facturacion_electronica.services.proveedores.fachada import capacidades

    if venta is None:
        return None

    documento = obtener_documento(venta.id_venta)
    if documento is None:
        return _acciones_sin_documento(venta, puede_operar)

    caps = capacidades()
    aprobado = documento.estado == ESTADO_APROBADO
    numero_perdido = bool(documento.numero) and _numero_definitivamente_perdido(documento, venta)
    rechazado_corregible = documento.estado == ESTADO_RECHAZADO and not numero_perdido

    # El plazo del evento de cancelacion corre desde la emision del DE, no
    # desde hoy ni desde que se genero el XML.
    emitido_el = fecha_emision(documento)
    dentro_del_plazo = True
    if emitido_el is not None:
        vencido = datetime.utcnow() - emitido_el > timedelta(hours=HORAS_LIMITE_CANCELACION)
        dentro_del_plazo = not vencido

    devoluciones = resumen_devoluciones(venta.id_venta) if caps['notas_credito'] else []
    pendientes_de_acreditar = [
        fila for fila in devoluciones
        if not fila['anulada'] and (
            fila['nota'] is None or fila['nota'].estado in (ESTADO_ERROR, ESTADO_RECHAZADO)
        )
    ]

    return {
        'documento': documento,
        'notas': notas_credito(venta.id_venta),
        'devoluciones': devoluciones,
        'devoluciones_pendientes': pendientes_de_acreditar,
        'puede_operar': bool(puede_operar),
        # Ya tiene documento: emitir de nuevo es "reintentar", y eso lo maneja
        # el job o la vista previa, no un botón más en la pantalla de la venta.
        'puede_emitir': False,
        # Rechazado todavía a tiempo: se corrige lo que dice SIFEN y se reenvía
        # con el mismo número. Es el botón de reintento de la emisión.
        'puede_corregir_rechazo': bool(puede_operar and rechazado_corregible),
        # Dentro de las 48h el camino barato es el evento de cancelacion.
        'puede_cancelar': bool(puede_operar and aprobado and dentro_del_plazo),
        # Pasado ese plazo (o si se prefiere), la NC por el total.
        'puede_anular_con_nc': bool(puede_operar and aprobado and caps['notas_credito']),
        'plazo_cancelacion_vencido': bool(aprobado and not dentro_del_plazo),
        'puede_acreditar_devolucion': bool(
            puede_operar and aprobado and caps['notas_credito'] and pendientes_de_acreditar
        ),
        'puede_inutilizar': bool(puede_operar and caps['inutilizacion'] and numero_perdido),
        # Todavía en juego: el job lo va a mandar en la próxima pasada. Se
        # informa para que nadie crea que quedó colgado. El rechazado no: el
        # job no lo toca, espera a que alguien lo corrija.
        'envio_en_curso': bool(
            documento.estado in ESTADOS_NUMERO_QUEMADO
            and documento.estado != ESTADO_RECHAZADO
            and not _numero_definitivamente_perdido(documento, venta)
        ),
        'tiene_kude': bool(documento.qr_url or documento.api_documento_id),
        'puede_reimprimir_kude': bool(
            (documento.qr_url or documento.api_documento_id)
            and documento.estado in ESTADOS_KUDE_REIMPRIMIBLE
        ),
        'tiene_xml': bool(documento.xml_firmado or documento.api_documento_id),
    }


def documentos_fe_de_ventas(venta_ids):
    """{id_venta: documento} para un listado de ventas; {} con el módulo apagado.

    Una sola consulta para toda la página (una por fila serían decenas). La
    usan el historial y el reporte de ventas del día: la columna "Nº Factura"
    tiene que mostrar la factura electrónica, no sólo `numero_factura` (la
    factura externa cargada a mano).
    """
    from app.utils.modulos import _modulo_activo
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO
    from facturacion_electronica.services.emision_service import facturas_de_ventas

    if not venta_ids or not _modulo_activo(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, False):
        return {}
    return facturas_de_ventas(venta_ids)


__all__ = ['acciones_para_venta', 'documentos_fe_de_ventas', 'ESTADOS_NUMERO_QUEMADO']
