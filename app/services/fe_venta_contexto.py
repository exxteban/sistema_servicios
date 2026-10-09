"""Contexto del panel de factura electronica en el detalle de una venta.

Mismo criterio que el sistema padre: sin el permiso de configuracion se muestra
el estado pero ningun boton, para no ofrecer una accion que va a terminar en
un redirect. Que se puede hacer lo decide `acciones_para_venta`.
"""
from app.models import Configuracion


def contexto_factura_electronica_venta(venta, usuario):
    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO, MOTIVOS_NOTA_CREDITO
    from facturacion_electronica.services.acciones import acciones_para_venta

    fe = None
    if Configuracion.obtener_bool(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, default=False):
        fe = acciones_para_venta(
            venta,
            puede_operar=usuario.es_admin() or usuario.tiene_permiso('editar_configuracion'),
        )
    return {'fe': fe, 'fe_motivos_nc': MOTIVOS_NOTA_CREDITO}


def datos_fe_modal(venta, usuario):
    """Lo que el modal de detalle del Historial / reporte del dia muestra de la FE.

    Mismas claves que el padre (`reportes.detalle_venta`): numero, estado, que
    acciones permite `acciones_para_venta` y a que URL se postea cada una, para
    poder cancelar, anular con nota de credito o emitir desde el Historial sin
    abrir la venta. None con el modulo apagado.
    """
    from flask import url_for

    from facturacion_electronica import CLAVE_FACTURACION_ELECTRONICA_ACTIVO
    from facturacion_electronica.services.acciones import acciones_para_venta

    if not Configuracion.obtener_bool(CLAVE_FACTURACION_ELECTRONICA_ACTIVO, default=False):
        return None
    acciones = acciones_para_venta(
        venta,
        puede_operar=usuario.es_admin() or usuario.tiene_permiso('editar_configuracion'),
    )
    if acciones is None:
        return None
    documento = acciones['documento']
    return {
        'numero': documento.numero_formateado if documento else None,
        'estado': documento.estado if documento else None,
        'puede_operar': acciones['puede_operar'],
        'puede_emitir': acciones['puede_emitir'],
        'puede_corregir_rechazo': acciones['puede_corregir_rechazo'],
        'motivo_rechazo': documento.respuesta_mensaje if documento else None,
        'puede_cancelar': acciones['puede_cancelar'],
        'puede_anular_con_nc': acciones['puede_anular_con_nc'],
        'puede_inutilizar': acciones['puede_inutilizar'],
        'envio_en_curso': acciones['envio_en_curso'],
        'plazo_cancelacion_vencido': acciones['plazo_cancelacion_vencido'],
        'devoluciones_pendientes': len(acciones['devoluciones_pendientes']),
        'notas': [
            {'numero': nota.numero_formateado, 'estado': nota.estado}
            for nota in acciones['notas']
        ],
        'url_cancelar': url_for('facturacion_electronica.cancelar', venta_id=venta.id_venta),
        'url_anular_nc': url_for(
            'facturacion_electronica.anular_con_nota_credito', venta_id=venta.id_venta),
        'url_inutilizar': url_for('facturacion_electronica.inutilizar', venta_id=venta.id_venta),
        'url_emitir': url_for('facturacion_electronica.emitir_completo', venta_id=venta.id_venta),
        'url_kude': url_for('facturacion_electronica.kude', venta_id=venta.id_venta)
        if acciones.get('puede_reimprimir_kude') else None,
    }


def datos_venta_modal(venta, usuario):
    """Estado de la venta y si el usuario puede anularla desde el modal."""
    return {
        'estado': venta.estado,
        'puede_anular': bool(
            venta.estado == 'completada'
            and (usuario.es_admin() or usuario.tiene_permiso('anular_venta'))
        ),
    }


def puede_ver_detalle_venta(usuario):
    """El Historial pide `ver_ventas`; el modal no puede pedir otra cosa."""
    return any(
        usuario.tiene_permiso(codigo)
        for codigo in ('ver_reporte_ventas', 'ver_detalle_venta', 'ver_ventas')
    )
