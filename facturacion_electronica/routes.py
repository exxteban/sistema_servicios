import json

from flask import Blueprint, Response, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.venta import Venta
from facturacion_electronica import (
    ESTADO_CANCELADO,
    MOTIVOS_NOTA_CREDITO,
    TIPO_FACTURA,
    TIPOS_CONTRIBUYENTE,
    TIPOS_EMITIBLES,
)
from facturacion_electronica.models import DocumentoElectronico
from facturacion_electronica.services.acciones import acciones_para_venta
from facturacion_electronica.services.kude_service import ancho_papel_kude
from facturacion_electronica.services.nota_credito import resumen_devoluciones
from facturacion_electronica.services.proveedores import PROVEEDORES
from facturacion_electronica.services.reintento import emitir_o_reintentar, puede_reintentar
from facturacion_electronica.services import (
    ajustar_secuencia,
    cancelar_documento,
    capacidades,
    construir_contexto_kude,
    construir_data_venta,
    construir_params_emisor,
    consultar_documento,
    emitir_nota_credito,
    emitir_nota_credito_correccion,
    emitir_para_pos,
    enviar_documento,
    firmar_documento,
    generar_documento,
    generar_qr_documento,
    generar_xml,
    geo,
    inutilizar_documento,
    guardar_configuracion,
    hay_documentos_transmitidos,
    kude_pdf,
    listar_secuencias,
    NOMBRE_TIPO,
    notas_credito,
    obtener_configuracion,
    obtener_documento,
    peek_proximo_numero,
    sincronizar_emisor,
    validar_configuracion,
    validar_readiness,
    xml_documento,
)


facturacion_electronica_bp = Blueprint(
    'facturacion_electronica',
    __name__,
    template_folder='templates',
)


def _puede_configurar():
    return current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')


def _puede_imprimir_kude():
    """El POS abre el KuDE tras emitir: el cajero no administra el emisor."""
    if _puede_configurar():
        return True
    return current_user.tiene_permiso('crear_venta') or current_user.tiene_permiso('ver_detalle_venta')


def _documento_descargable(venta_id):
    """El documento cuyo comprobante se pide: la factura, o la nota de crédito
    si vino su id.

    `obtener_documento` devuelve sólo la factura a propósito, así que sin este
    rodeo la NC quedaba sin XML ni PDF descargables — y el comprador los
    necesita igual que los de la factura. El id se valida contra la venta para
    que nadie se baje el comprobante de otra con sólo cambiar el número.
    """
    documento_id = request.args.get('documento', type=int)
    if not documento_id:
        return obtener_documento(venta_id)
    documento = db.session.get(DocumentoElectronico, documento_id)
    if documento is None or documento.id_venta != venta_id:
        return None
    return documento


def _solo_motor_propio():
    """Corta las pantallas del circuito manual (generar/firmar/QR/enviar): sólo
    existen en el motor propio. La numeración NO entra acá — el correlativo lo
    lleva el emisor con cualquier proveedor."""
    if capacidades()['herramientas_propias']:
        return None
    flash('Esta operación corresponde al motor propio.', 'warning')
    return redirect(url_for('facturacion_electronica.configuracion'))


@facturacion_electronica_bp.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if not _puede_configurar():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción esta deshabilitada.', 'warning')
        else:
            flash('No tenés permisos para configurar facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        _config, error_cert = guardar_configuracion(
            request.form,
            archivo_cert=request.files.get('certificado'),
        )
        if error_cert:
            flash(error_cert, 'warning')
        else:
            flash('Configuración de facturación electrónica guardada.', 'success')
        return redirect(url_for('facturacion_electronica.configuracion'))

    config = obtener_configuracion()
    return render_template(
        'facturacion_electronica/configuracion.html',
        config=config,
        tipos_contribuyente=TIPOS_CONTRIBUYENTE,
        # La pantalla sí espera: es el único lugar donde el usuario puede
        # hacer algo con "falta el certificado en la API".
        faltantes=validar_readiness(config),
        departamentos=geo.departamentos(config.proveedor),
        secuencias=listar_secuencias(),
        hay_documentos=hay_documentos_transmitidos(),
        proveedores=PROVEEDORES,
        capacidades=capacidades(config),
    )


@facturacion_electronica_bp.route('/proveedor/sincronizar', methods=['POST'])
@login_required
def sincronizar_proveedor():
    """Trae los datos fiscales del emisor desde el proveedor activo.

    Nuestra copia sólo sirve para imprimir; la verdad fiscal es la del
    proveedor. Cargar los mismos datos dos veces a mano termina, tarde o
    temprano, con la factura diciendo una cosa y el papel otra.
    """
    if not _puede_configurar():
        flash('No tenés permisos para configurar facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    resumen, error = sincronizar_emisor(obtener_configuracion())
    if error:
        flash(f'No se pudieron traer los datos del emisor: {error}', 'danger')
    else:
        flash(resumen, 'success')
    return redirect(url_for('facturacion_electronica.configuracion'))


@facturacion_electronica_bp.route('/numeracion/ajustar', methods=['POST'])
@login_required
def ajustar_numeracion():
    """Fija el correlativo a mano (reset previo a producción o siembra inicial)."""
    if not _puede_configurar():
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción esta deshabilitada.', 'warning')
        else:
            flash('No tenés permisos para configurar facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    establecimiento = request.form.get('establecimiento')
    punto = request.form.get('punto')
    ultimo_numero = request.form.get('ultimo_numero')
    tipo_documento = request.form.get('tipo_documento', type=int) or TIPO_FACTURA
    if tipo_documento not in TIPOS_EMITIBLES:
        tipo_documento = TIPO_FACTURA
    forzar = request.form.get('forzar') is not None

    seq, error = ajustar_secuencia(
        establecimiento, punto, ultimo_numero, forzar=forzar, tipo_documento=tipo_documento,
    )

    if error:
        flash(error, 'danger')
    else:
        nombre = NOMBRE_TIPO.get(seq.tipo_documento, 'documento')
        flash(
            f'Correlativo de {nombre} {seq.establecimiento}-{seq.punto} fijado en '
            f'{seq.ultimo_numero:07d}. El próximo documento saldrá con el '
            f'{seq.ultimo_numero + 1:07d}.',
            'success',
        )

    return redirect(url_for('facturacion_electronica.configuracion'))


@facturacion_electronica_bp.route('/vista-previa')
@login_required
def vista_previa():
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    # La pantalla sirve con cualquier proveedor (estado, CDC, KuDE, descargas);
    # lo que es del motor propio es la vista del payload TIPS y el paso a paso.
    capacidades_fe = capacidades()
    venta_id = (request.args.get('venta') or '').strip()
    venta = Venta.query.get(venta_id) if venta_id.isdigit() else None
    documento_json = None
    xml_generado = None
    xml_error = None

    if venta_id and venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
    elif venta is not None and capacidades_fe['herramientas_propias']:
        config = obtener_configuracion()
        params = construir_params_emisor(config)
        numero_preview = obtener_documento(venta.id_venta)
        numero_preview = numero_preview.numero if numero_preview and numero_preview.numero else \
            peek_proximo_numero(config.establecimiento, config.punto_expedicion)
        data = construir_data_venta(venta, config, numero=numero_preview)
        documento_json = json.dumps(
            {'params': params, 'data': data}, indent=2, ensure_ascii=False, default=str
        )
        if request.args.get('generar'):
            xml_generado, xml_error = generar_xml(params, data)

    return render_template(
        'facturacion_electronica/vista_previa.html',
        venta_id=venta_id,
        venta=venta,
        documento_json=documento_json,
        xml_generado=xml_generado,
        xml_error=xml_error,
        documento=obtener_documento(venta.id_venta) if venta is not None else None,
        puede_reintentar=puede_reintentar(obtener_documento(venta.id_venta), venta) if venta else False,
        # La misma regla que la pantalla de la venta: un DE firmado o rechazado a
        # tiempo todavía sale; ofrecer quemar su número acá era la trampa.
        acciones=acciones_para_venta(venta, puede_operar=True) if venta is not None else None,
        capacidades=capacidades_fe,
        notas=notas_credito(venta.id_venta) if venta is not None else [],
        devoluciones=(
            resumen_devoluciones(venta.id_venta)
            if venta is not None and capacidades_fe['notas_credito'] else []
        ),
        motivos_nc=MOTIVOS_NOTA_CREDITO,
    )


@facturacion_electronica_bp.route('/nota-credito/<int:devolucion_id>', methods=['POST'])
@login_required
def nota_credito(devolucion_id):
    """Emite la nota de crédito de una devolución ya registrada.

    No registra la devolución ni toca la caja: eso ya pasó. Acá sólo se emite
    el documento fiscal que la respalda ante SIFEN.
    """
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    from app.models.devolucion import Devolucion

    devolucion = db.session.get(Devolucion, devolucion_id)
    if devolucion is None:
        flash(f'No se encontró la devolución {devolucion_id}.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa'))

    documento, error = emitir_nota_credito(devolucion, request.form.get('motivo'))
    if error:
        flash(f'No se pudo emitir la nota de crédito: {error}', 'danger')
    else:
        flash(
            f'Nota de crédito {documento.numero_formateado} emitida por la devolución '
            f'#{devolucion.id_devolucion}.',
            'success',
        )
    return redirect(url_for(
        'facturacion_electronica.vista_previa', venta=devolucion.id_venta,
    ))


@facturacion_electronica_bp.route('/anular-con-nota-credito/<int:venta_id>', methods=['POST'])
@login_required
def anular_con_nota_credito(venta_id):
    """Anula una factura mal emitida con una NC por el total, sin devolución.

    Es la salida cuando ya pasaron las 48h del evento de cancelación. No mueve
    plata ni stock: la NC respalda la corrección fiscal, y revertir el cobro es
    anular la venta después.
    """
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    venta = db.session.get(Venta, venta_id)
    if venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa'))

    documento, error = emitir_nota_credito_correccion(
        venta, request.form.get('motivo'), request.form.get('descripcion'),
    )
    if error:
        flash(f'No se pudo emitir la nota de crédito de anulación: {error}', 'danger')
    else:
        flash(
            f'Nota de crédito {documento.numero_formateado} emitida por el total de la '
            'factura. Cuando SIFEN la apruebe vas a poder anular la venta.',
            'success',
        )
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/emitir-completo/<int:venta_id>', methods=['POST'])
@login_required
def emitir_completo(venta_id):
    """Emisión en un paso, sea cual sea el proveedor (lo mismo que hace el POS)."""
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    venta = Venta.query.get(venta_id)
    if venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa'))

    _documento, error = emitir_o_reintentar(venta)
    if error:
        flash(f'No se pudo emitir: {error}', 'danger')
    else:
        flash(f'Documento electrónico emitido. Estado: {_documento.estado}.', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/emitir/<int:venta_id>', methods=['POST'])
@login_required
def emitir(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    bloqueo = _solo_motor_propio()
    if bloqueo is not None:
        return bloqueo

    venta = Venta.query.get(venta_id)
    if venta is None:
        flash(f'No se encontró la venta {venta_id}.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa'))

    faltantes = validar_configuracion(obtener_configuracion())
    if faltantes:
        flash('Configuración de facturación electrónica incompleta: ' + ', '.join(faltantes), 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    documento, error = generar_documento(venta)
    if error:
        flash(f'No se pudo generar el documento: {error}', 'danger')
    else:
        flash(f'Documento generado y guardado. CDC: {documento.cdc}', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/firmar/<int:venta_id>', methods=['POST'])
@login_required
def firmar(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    bloqueo = _solo_motor_propio()
    if bloqueo is not None:
        return bloqueo

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('Primero generá el documento para esta venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    _doc, error = firmar_documento(documento)
    if error:
        flash(f'No se pudo firmar: {error}', 'danger')
    else:
        flash('Documento firmado correctamente.', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/qr/<int:venta_id>', methods=['POST'])
@login_required
def generar_qr(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    bloqueo = _solo_motor_propio()
    if bloqueo is not None:
        return bloqueo

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('Primero generá el documento para esta venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    _doc, error = generar_qr_documento(documento)
    if error:
        flash(f'No se pudo generar el QR: {error}', 'danger')
    else:
        flash('QR generado. Ya podés ver el KuDE.', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/enviar/<int:venta_id>', methods=['POST'])
@login_required
def enviar(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    bloqueo = _solo_motor_propio()
    if bloqueo is not None:
        return bloqueo

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('Primero generá el documento para esta venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    _doc, error = enviar_documento(documento)
    if error:
        flash(f'No se pudo enviar a SIFEN: {error}', 'danger')
    else:
        flash(f'Enviado a SIFEN. Estado: {_doc.estado}.', 'success')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/consultar/<int:venta_id>', methods=['POST'])
@login_required
def consultar(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('No hay documento para esta venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    respuesta, error = consultar_documento(documento)
    if error:
        flash(f'No se pudo consultar SIFEN: {error}', 'danger')
    else:
        flash(f'Respuesta de SIFEN: {respuesta}', 'info')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/cancelar/<int:venta_id>', methods=['POST'])
@login_required
def cancelar(venta_id):
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('No hay documento electrónico para esa venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    motivo = (request.form.get('motivo') or '').strip()
    doc, error = cancelar_documento(documento, motivo)
    if error:
        flash(f'No se pudo cancelar la factura: {error}', 'danger')
    elif doc is not None and doc.estado == ESTADO_CANCELADO:
        flash('Factura electrónica cancelada en SIFEN. Podés volver a facturar la venta.', 'success')
    else:
        # La API externa deja la baja en CANCELLATION_PENDING hasta que SIFEN
        # contesta, y mientras tanto el DE sigue vigente: decirle que ya puede
        # volver a facturar era mentira, porque la re-emisión se niega con
        # "ya está aprobado" y nadie entendía por qué.
        flash('Cancelación pedida. SIFEN todavía no la confirmó, así que la factura sigue '
              'vigente por ahora; recién cuando la baja quede firme vas a poder volver a '
              'facturar la venta. El sistema vuelve a consultarla solo cada pocos minutos.',
              'info')
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/inutilizar/<int:venta_id>', methods=['POST'])
@login_required
def inutilizar(venta_id):
    """Informa a SIFEN el número quemado de una venta que nunca se transmitió."""
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = obtener_documento(venta_id)
    if documento is None:
        flash('No hay documento electrónico para esa venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    motivo = (request.form.get('motivo') or '').strip()
    doc, error = inutilizar_documento(documento, motivo)
    if error:
        flash(f'No se pudo inutilizar el número: {error}', 'danger')
    else:
        flash(
            f'Número {doc.numero_formateado} inutilizado en SIFEN. El hueco del timbrado '
            'queda justificado y la venta se puede volver a facturar con un número nuevo.',
            'success',
        )
    return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))


@facturacion_electronica_bp.route('/kude/<int:venta_id>')
@login_required
def kude(venta_id):
    if not _puede_imprimir_kude():
        flash('No tenés permisos para imprimir el KuDE.', 'danger')
        return redirect(url_for('main.dashboard'))

    venta = Venta.query.get(venta_id)
    # Con `?documento=<id>` imprime esa nota de crédito en vez de la factura:
    # el comprador necesita el papel de la NC igual que el de la factura.
    documento = _documento_descargable(venta_id)
    if venta is None or documento is None:
        flash('No hay documento electrónico para esa venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    contexto = construir_contexto_kude(venta, documento)
    if contexto is None:
        flash('El KuDE del proveedor seleccionado aún no está disponible.', 'warning')
        return redirect(url_for('facturacion_electronica.configuracion'))
    contexto.update(preview=request.args.get('preview') is not None, paper_width_mm=ancho_papel_kude())
    return render_template('facturacion_electronica/kude.html', **contexto)


@facturacion_electronica_bp.route('/descargar/xml/<int:venta_id>')
@login_required
def descargar_xml(venta_id):
    """XML firmado del DE: es lo que un cliente empresa necesita para su IVA."""
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = _documento_descargable(venta_id)
    if documento is None:
        flash('No hay documento electrónico para esa venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))
    xml, error = xml_documento(documento)
    if error:
        flash(f'No se pudo obtener el XML: {error}', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    nombre = f'{documento.cdc or f"venta-{venta_id}"}.xml'
    return Response(xml, mimetype='application/xml', headers={
        'Content-Disposition': f'attachment; filename="{nombre}"',
    })


@facturacion_electronica_bp.route('/descargar/kude/<int:venta_id>')
@login_required
def descargar_kude_pdf(venta_id):
    """KuDE oficial en PDF, cuando lo genera el proveedor (A4, no la térmica)."""
    if not _puede_configurar():
        flash('No tenés permisos para facturación electrónica.', 'danger')
        return redirect(url_for('main.dashboard'))

    documento = _documento_descargable(venta_id)
    if documento is None:
        flash('No hay documento electrónico para esa venta.', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))
    pdf, error = kude_pdf(documento)
    if error:
        flash(f'No se pudo obtener el KuDE en PDF: {error}', 'warning')
        return redirect(url_for('facturacion_electronica.vista_previa', venta=venta_id))

    nombre = f'{documento.cdc or f"venta-{venta_id}"}.pdf'
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{nombre}"',
    })


@facturacion_electronica_bp.route('/estado-pos/<int:venta_id>', methods=['GET'])
@login_required
def estado_pos(venta_id):
    """¿Ya hay un DE emitido para esta venta? Lo usa el POS si el POST se abortó."""
    if not _puede_imprimir_kude():
        return jsonify({'success': False, 'error': 'Sin permiso para imprimir el KuDE.'}), 403
    documento = obtener_documento(venta_id)
    if documento is None or not (documento.cdc or documento.api_documento_id):
        return jsonify({'success': False})
    return jsonify({
        'success': True,
        'cdc': documento.cdc,
        'kude_url': url_for('facturacion_electronica.kude', venta_id=venta_id),
    })


@facturacion_electronica_bp.route('/emitir-pos/<int:venta_id>', methods=['POST'])
@login_required
def emitir_pos(venta_id):
    """Emite la factura electrónica de una venta ya registrada (llamado desde el POS).

    Devuelve JSON. No revierte la venta: si falla, el POS cae al ticket normal.
    """
    venta = Venta.query.get(venta_id)
    if venta is None:
        return jsonify({'success': False, 'error': f'No se encontró la venta {venta_id}.'}), 404

    faltantes = validar_configuracion(obtener_configuracion())
    if faltantes:
        return jsonify({
            'success': False,
            'error': 'Configuración de facturación electrónica incompleta: ' + ', '.join(faltantes),
        }), 400

    documento, error = emitir_para_pos(venta)
    if error:
        return jsonify({'success': False, 'error': error}), 502

    return jsonify({
        'success': True,
        'cdc': documento.cdc,
        'kude_url': url_for('facturacion_electronica.kude', venta_id=venta_id),
    })
