import re
from datetime import datetime
from types import SimpleNamespace

from flask import current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from jinja2 import TemplateError, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

from app import db
from app.models import Configuracion, Reparacion
from app.models.reparacion_seguimiento import ReparacionSeguimiento, SeguimientoAcceso
from app.services.whatsapp.verificacion_service import generar_codigo
from app.utils.public_url import build_public_url
from app.utils.seguimiento_utils import cifrar_token, descifrar_token, generar_qr_svg, generar_token, hash_token

from .base import REPARACION_TICKET_FOOTER_DEFAULT, _get_reparacion_or_404_safe, reparaciones_bp


def _normalize_repair_ticket_template_signature(template_html: str) -> str:
    return re.sub(r'\s+', '', (template_html or '').strip()).lower()


def _should_use_builtin_repair_ticket_template(template_html: str) -> bool:
    """
    Detecta copias guardadas de la plantilla estándar de reparación para que
    las mejoras del template oficial apliquen sin obligar a reconfigurar.
    """
    normalized = _normalize_repair_ticket_template_signature(template_html)
    if not normalized:
        return False

    markers = (
        '<title>ticketreparacion#{{reparacion.id_reparacion}}</title>',
        '<divclass="title">serviciotécnico</div>',
        '<div>comprobantederecepción</div>',
        '<div>ticket#{{reparacion.id_reparacion}}</div>',
        "{{seguimiento_url}}</p>",
    )
    return all(marker in normalized for marker in markers)


def _render_custom_repair_ticket(template_html: str, **ctx) -> str:
    """Renderiza plantillas configurables sin exponer objetos de Flask/SQLAlchemy."""
    reparacion = ctx['reparacion']
    cliente = getattr(reparacion, 'cliente', None)
    reparacion_segura = SimpleNamespace(
        id_reparacion=reparacion.id_reparacion,
        fecha_ingreso=reparacion.fecha_ingreso,
        estado=reparacion.estado,
        estado_display=reparacion.estado_display,
        tipo_equipo=reparacion.tipo_equipo,
        marca_modelo=reparacion.marca_modelo,
        imei_serie=reparacion.imei_serie,
        falla_reportada=reparacion.falla_reportada,
        accesorios=reparacion.accesorios,
        cliente=SimpleNamespace(
            nombre=getattr(cliente, 'nombre', ''),
            telefono=getattr(cliente, 'telefono', ''),
            ruc_ci=getattr(cliente, 'ruc_ci', ''),
        ),
    )
    entorno = SandboxedEnvironment(autoescape=True)
    plantilla = entorno.from_string(template_html)
    return plantilla.render(
        reparacion=reparacion_segura,
        empresa=dict(ctx.get('empresa') or {}),
        footer_text=ctx.get('footer_text') or '',
        qr_svg=Markup(ctx.get('qr_svg') or ''),
        seguimiento_url=ctx.get('seguimiento_url') or '',
        codigo_bot=ctx.get('codigo_bot') or '',
        preview=bool(ctx.get('preview')),
        embedded=bool(ctx.get('embedded')),
        thermal_mode=bool(ctx.get('thermal_mode')),
        paper_width_mm=ctx.get('paper_width_mm') or 58,
    )


@reparaciones_bp.route('/<int:id>/ticket')
@login_required
def ticket(id):
    if not current_user.tiene_permiso('ver_reparaciones'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    preview = request.args.get('preview') == '1'
    embedded = request.args.get('embedded') == '1'
    thermal_mode = request.args.get('thermal') != '0'
    reparacion = _get_reparacion_or_404_safe(id)

    seguimiento = ReparacionSeguimiento.query.filter_by(
        id_reparacion=reparacion.id_reparacion
    ).first()

    if not seguimiento:
        token = generar_token()
        seguimiento = ReparacionSeguimiento(
            id_reparacion=reparacion.id_reparacion,
            token_hash=hash_token(token),
            token_cifrado=cifrar_token(token)
        )
        db.session.add(seguimiento)
        db.session.commit()
    else:
        # A reprint preserves the original QR link.
        # Rotation only happens through the explicit POST action.
        token = descifrar_token(seguimiento.token_cifrado)

    codigo_bot = None
    if reparacion.cliente and reparacion.cliente.telefono:
        codigo_bot = generar_codigo(reparacion.cliente.telefono, reparacion.id_reparacion)

    if token is None:
        # El token original no se puede reconstruir desde su hash. Para reimpresiones
        # it remains valid and can only be replaced through an explicit rotation.
        seguimiento_url = ''
    else:
        seguimiento_url = build_public_url('seguimiento.ver_seguimiento', token=token)
    qr_svg = None
    if seguimiento_url:
        try:
            qr_svg = generar_qr_svg(seguimiento_url)
        except ImportError:
            qr_svg = None
            flash('No se pudo generar el código QR. Instale: pip install segno', 'warning')
    elif not preview:
        flash('Esta es una reimpresión. El QR original sigue activo; rote el enlace solo si necesita reemplazarlo.', 'info')

    base_nombre = Configuracion.obtener('nombre_empresa', '') or ''
    base_ruc = Configuracion.obtener('ruc_empresa', '') or ''
    base_direccion = Configuracion.obtener('direccion_empresa', '') or ''
    base_telefono = Configuracion.obtener('telefono_empresa', '') or ''
    empresa = {
        'nombre': Configuracion.obtener('repair_nombre_empresa', base_nombre or 'RYJCELL') or base_nombre or 'RYJCELL',
        'ruc': Configuracion.obtener('repair_ruc_empresa', base_ruc) or base_ruc,
        'direccion': Configuracion.obtener('repair_direccion_empresa', base_direccion) or base_direccion,
        'telefono': Configuracion.obtener('repair_telefono_empresa', base_telefono) or base_telefono,
    }
    footer_text = (
        Configuracion.obtener('repair_ticket_footer_text', REPARACION_TICKET_FOOTER_DEFAULT)
        or REPARACION_TICKET_FOOTER_DEFAULT
    )
    template_html = (Configuracion.obtener('repair_ticket_template_html', '') or '').strip()
    paper_width_mm = Configuracion.obtener_int('repair_ticket_paper_width_mm', 58)
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58
    ctx = {
        'reparacion': reparacion,
        'empresa': empresa,
        'footer_text': footer_text,
        'qr_svg': qr_svg,
        'seguimiento_url': seguimiento_url,
        'codigo_bot': codigo_bot,
        'preview': preview,
        'embedded': embedded,
        'thermal_mode': thermal_mode,
        'paper_width_mm': paper_width_mm,
    }

    if template_html and not _should_use_builtin_repair_ticket_template(template_html):
        try:
            return _render_custom_repair_ticket(template_html, **ctx)
        except TemplateError as e:
            pos = None
            m = re.search(r'at (\d+)\s*$', str(e))
            if m:
                try:
                    pos = int(m.group(1))
                except Exception:
                    pos = None
            if pos is not None:
                snippet = template_html[max(0, pos - 120):pos + 120]
                current_app.logger.error('Error en repair_ticket_template_html cerca de: %r', snippet)
            current_app.logger.exception(
                'Error de sintaxis en repair_ticket_template_html; usando plantilla por defecto'
            )

    return render_template('reparaciones/ticket.html', **ctx)


@reparaciones_bp.route('/config/ticket/preview', methods=['POST'])
@login_required
def config_ticket_preview():
    if not (current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'success': False, 'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'success': False, 'error': 'Sin permisos', 'modo_demo': False}), 403

    payload = request.get_json(silent=True) or {}
    id_reparacion = payload.get('id_reparacion')
    template_html = payload.get('ticket_template_html') or ''
    footer_text = (payload.get('ticket_footer_text') or REPARACION_TICKET_FOOTER_DEFAULT).strip()
    footer_text = footer_text or REPARACION_TICKET_FOOTER_DEFAULT
    try:
        paper_width_mm = int(payload.get('paper_width_mm') or 58)
    except (TypeError, ValueError):
        paper_width_mm = 58
    if paper_width_mm not in (48, 58, 80):
        paper_width_mm = 58

    empresa = {
        'nombre': (payload.get('nombre_empresa') or '').strip(),
        'ruc': (payload.get('ruc_empresa') or '').strip(),
        'direccion': (payload.get('direccion_empresa') or '').strip(),
        'telefono': (payload.get('telefono_empresa') or '').strip(),
    }

    reparacion = None
    if id_reparacion not in (None, '', 0, '0'):
        try:
            reparacion = db.session.get(Reparacion, int(id_reparacion))
        except Exception:
            reparacion = None

    if not reparacion:
        reparacion = Reparacion.query.order_by(Reparacion.id_reparacion.desc()).first()

    if not reparacion:
        reparacion = SimpleNamespace(
            id_reparacion=1,
            fecha_ingreso=datetime.utcnow(),
            estado='pendiente',
            estado_display='Pendiente',
            cliente=SimpleNamespace(nombre='Cliente de ejemplo'),
            tipo_equipo='Celular',
            marca_modelo='Samsung A54',
            imei_serie='356789123456789',
            falla_reportada='No enciende y presenta daño por humedad.',
            accesorios='Cargador y funda'
        )

    seguimiento_url = 'https://seguimiento.example.com/reparacion/vista-previa'
    qr_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120" viewBox="0 0 120 120">'
        '<rect width="120" height="120" fill="#fff"/>'
        '<rect x="8" y="8" width="26" height="26" fill="#000"/>'
        '<rect x="86" y="8" width="26" height="26" fill="#000"/>'
        '<rect x="8" y="86" width="26" height="26" fill="#000"/>'
        '<rect x="48" y="18" width="10" height="10" fill="#000"/>'
        '<rect x="62" y="18" width="10" height="10" fill="#000"/>'
        '<rect x="48" y="34" width="24" height="10" fill="#000"/>'
        '<rect x="44" y="52" width="12" height="12" fill="#000"/>'
        '<rect x="64" y="52" width="14" height="14" fill="#000"/>'
        '<rect x="48" y="72" width="30" height="10" fill="#000"/>'
        '<rect x="86" y="86" width="26" height="26" fill="#000"/>'
        '</svg>'
    )
    ctx = {
        'reparacion': reparacion,
        'empresa': empresa,
        'footer_text': footer_text,
        'qr_svg': qr_svg,
        'seguimiento_url': seguimiento_url,
        'codigo_bot': '123456',
        'preview': True,
        'embedded': False,
        'thermal_mode': False,
        'paper_width_mm': paper_width_mm,
    }

    try:
        if template_html.strip() and not _should_use_builtin_repair_ticket_template(template_html):
            html = _render_custom_repair_ticket(template_html, **ctx)
        else:
            html = render_template('reparaciones/ticket.html', **ctx)
        return jsonify({'success': True, 'html': html})
    except TemplateSyntaxError as e:
        pos = None
        m = re.search(r'at (\d+)\s*$', str(e))
        if m:
            try:
                pos = int(m.group(1))
            except Exception:
                pos = None
        if pos is not None:
            snippet = template_html[max(0, pos - 120):pos + 120]
            return jsonify({'success': False, 'error': f'{e} | cerca de: {snippet}'}), 400
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@reparaciones_bp.route('/<int:id>/rotar_token', methods=['POST'])
@login_required
def rotar_token(id):
    if not current_user.tiene_permiso('editar_reparacion'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta accin est deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para rotar el token.', 'danger')
        return redirect(url_for('main.dashboard'))

    reparacion = _get_reparacion_or_404_safe(id)

    seguimiento_actual = ReparacionSeguimiento.query.filter_by(
        id_reparacion=reparacion.id_reparacion
    ).first()

    token = generar_token()
    ahora = datetime.utcnow()
    if seguimiento_actual:
        seguimiento_actual.token_hash = hash_token(token)
        seguimiento_actual.token_cifrado = cifrar_token(token)
        seguimiento_actual.created_at = ahora
        seguimiento_actual.revoked_at = None
        seguimiento_actual.last_accessed_at = None
        seguimiento_actual.access_count = 0
    else:
        nuevo_seguimiento = ReparacionSeguimiento(
            id_reparacion=reparacion.id_reparacion,
            token_hash=hash_token(token),
            token_cifrado=cifrar_token(token),
            created_at=ahora
        )
        db.session.add(nuevo_seguimiento)
    db.session.commit()

    flash('Token de seguimiento rotado exitosamente. Imprima un nuevo ticket.', 'success')
    return redirect(url_for('reparaciones.detalle', id=id))


@reparaciones_bp.route('/<int:id>/accesos')
@login_required
def ver_accesos(id):
    if not current_user.tiene_permiso('ver_reparaciones'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta accin est deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))

    reparacion = _get_reparacion_or_404_safe(id)

    seguimiento = ReparacionSeguimiento.query.filter_by(
        id_reparacion=reparacion.id_reparacion,
        revoked_at=None
    ).first()

    accesos = []
    ips_unicas = 0

    if seguimiento:
        accesos = seguimiento.accesos.order_by(
            SeguimientoAcceso.accessed_at.desc()
        ).limit(50).all()

        ips_unicas = db.session.query(SeguimientoAcceso.ip_address).filter(
            SeguimientoAcceso.id_seguimiento == seguimiento.id
        ).distinct().count()

    return render_template(
        'reparaciones/accesos.html',
        reparacion=reparacion,
        seguimiento=seguimiento,
        accesos=accesos,
        ips_unicas=ips_unicas
    )
