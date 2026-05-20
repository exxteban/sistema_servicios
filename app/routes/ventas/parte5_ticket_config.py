from .parte1 import *


def _normalize_ticket_paper_width_mm(value, default=58):
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return normalized if normalized in (48, 58, 80) else default


@ventas_bp.route('/config/ticket', methods=['GET', 'POST'])
@login_required
def config_ticket():
    if not (current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para editar el ticket.', 'danger')
        return redirect(url_for('main.dashboard'))

    from pathlib import Path
    repair_footer_default = (
        'Este documento es el único comprobante para el retiro del equipo. '
        'Una vez aceptado el presupuesto, los equipos deben ser retirados dentro de los 30 días; '
        'en caso contrario, el equipo será considerado como abandono y la empresa se hará cargo del mismo.'
    )
    ticket_path = Path(current_app.root_path) / 'templates' / 'ventas' / 'ticket.html'
    repair_ticket_path = Path(current_app.root_path) / 'templates' / 'reparaciones' / 'ticket.html'
    try:
        default_template_html = ticket_path.read_text(encoding='utf-8')
    except Exception:
        default_template_html = ''
    try:
        default_repair_template_html = repair_ticket_path.read_text(encoding='utf-8')
    except Exception:
        default_repair_template_html = ''

    if request.method == 'POST':
        ticket_scope = (request.form.get('ticket_scope') or 'venta').strip().lower()
        nombre = (request.form.get('nombre_empresa') or '').strip()
        ruc = (request.form.get('ruc_empresa') or '').strip()
        direccion = (request.form.get('direccion_empresa') or '').strip()
        telefono = (request.form.get('telefono_empresa') or '').strip()
        footer_text = (request.form.get('ticket_footer_text') or '').strip()
        template_html = request.form.get('ticket_template_html') or ''
        paper_width_mm = _normalize_ticket_paper_width_mm(request.form.get('paper_width_mm') or 58)

        if ticket_scope == 'reparacion':
            Configuracion.establecer('repair_nombre_empresa', nombre, 'Nombre de la empresa para ticket de reparación')
            Configuracion.establecer('repair_ruc_empresa', ruc, 'RUC de la empresa para ticket de reparación')
            Configuracion.establecer(
                'repair_direccion_empresa',
                direccion,
                'Dirección de la empresa para ticket de reparación'
            )
            Configuracion.establecer(
                'repair_telefono_empresa',
                telefono,
                'Teléfono de la empresa para ticket de reparación'
            )
            Configuracion.establecer(
                'repair_ticket_footer_text',
                footer_text,
                'Texto del pie del ticket de reparación'
            )
            Configuracion.establecer(
                'repair_ticket_template_html',
                template_html,
                'Plantilla HTML del ticket de reparación'
            )
            Configuracion.establecer(
                'repair_ticket_paper_width_mm',
                str(paper_width_mm),
                'Ancho de papel del ticket de reparación en milímetros'
            )
            flash('Ticket de reparación actualizado correctamente.', 'success')
            return redirect(url_for('ventas.config_ticket', tab='reparacion'))

        Configuracion.establecer('nombre_empresa', nombre, 'Nombre de la empresa')
        Configuracion.establecer('ruc_empresa', ruc, 'RUC de la empresa')
        Configuracion.establecer('direccion_empresa', direccion, 'Dirección fiscal')
        Configuracion.establecer('telefono_empresa', telefono, 'Teléfono de contacto')
        Configuracion.establecer('ticket_footer_text', footer_text, 'Texto del pie del ticket')
        Configuracion.establecer('ticket_template_html', template_html, 'Plantilla HTML del ticket')
        Configuracion.establecer('ticket_paper_width_mm', str(paper_width_mm), 'Ancho de papel del ticket en milímetros')

        flash('Ticket de venta actualizado correctamente.', 'success')
        return redirect(url_for('ventas.config_ticket', tab='venta'))

    last_sale = Venta.query.order_by(Venta.id_venta.desc()).first()
    last_repair = Reparacion.query.order_by(Reparacion.id_reparacion.desc()).first()
    id_venta_preview = last_sale.id_venta if last_sale else ''
    id_reparacion_preview = last_repair.id_reparacion if last_repair else ''
    base_nombre = Configuracion.obtener('nombre_empresa', '') or ''
    base_ruc = Configuracion.obtener('ruc_empresa', '') or ''
    base_direccion = Configuracion.obtener('direccion_empresa', '') or ''
    base_telefono = Configuracion.obtener('telefono_empresa', '') or ''
    selected_tab = (request.args.get('tab') or 'venta').strip().lower()
    if selected_tab not in ('venta', 'reparacion'):
        selected_tab = 'venta'

    venta_data = {
        'nombre_empresa': Configuracion.obtener('nombre_empresa', '') or '',
        'ruc_empresa': Configuracion.obtener('ruc_empresa', '') or '',
        'direccion_empresa': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono_empresa': Configuracion.obtener('telefono_empresa', '') or '',
        'ticket_footer_text': Configuracion.obtener('ticket_footer_text', 'Gracias por su compra') or 'Gracias por su compra',
        'ticket_template_html': Configuracion.obtener('ticket_template_html', '') or '',
        'paper_width_mm': _normalize_ticket_paper_width_mm(Configuracion.obtener_int('ticket_paper_width_mm', 58)),
    }
    reparacion_data = {
        'nombre_empresa': Configuracion.obtener('repair_nombre_empresa', base_nombre or 'RYJCELL') or base_nombre or 'RYJCELL',
        'ruc_empresa': Configuracion.obtener('repair_ruc_empresa', base_ruc) or base_ruc,
        'direccion_empresa': Configuracion.obtener('repair_direccion_empresa', base_direccion) or base_direccion,
        'telefono_empresa': Configuracion.obtener('repair_telefono_empresa', base_telefono) or base_telefono,
        'ticket_footer_text': (
            Configuracion.obtener('repair_ticket_footer_text', repair_footer_default)
            or repair_footer_default
        ),
        'ticket_template_html': Configuracion.obtener('repair_ticket_template_html', '') or '',
        'paper_width_mm': _normalize_ticket_paper_width_mm(Configuracion.obtener_int('repair_ticket_paper_width_mm', 58)),
    }

    return render_template(
        'ventas/ticket_config.html',
        venta_data=venta_data,
        reparacion_data=reparacion_data,
        default_template_html=default_template_html,
        default_repair_template_html=default_repair_template_html,
        id_venta_preview=id_venta_preview,
        id_reparacion_preview=id_reparacion_preview,
        selected_tab=selected_tab,
    )


@ventas_bp.route('/config/ticket/preview', methods=['POST'])
@login_required
def config_ticket_preview():
    if not (current_user.es_admin() or current_user.tiene_permiso('editar_configuracion')):
        if getattr(current_user, 'modo_demo', False):
            return jsonify({'success': False, 'error': 'Modo demo: esta acción está deshabilitada', 'modo_demo': True}), 403
        return jsonify({'success': False, 'error': 'Sin permisos', 'modo_demo': False}), 403

    payload = request.get_json(silent=True) or {}
    id_venta = payload.get('id_venta')
    template_html = payload.get('ticket_template_html') or ''
    footer_text = (payload.get('ticket_footer_text') or 'Gracias por su compra').strip() or 'Gracias por su compra'
    paper_width_mm = _normalize_ticket_paper_width_mm(payload.get('paper_width_mm') or 58)

    empresa = {
        'nombre': (payload.get('nombre_empresa') or '').strip(),
        'ruc': (payload.get('ruc_empresa') or '').strip(),
        'direccion': (payload.get('direccion_empresa') or '').strip(),
        'telefono': (payload.get('telefono_empresa') or '').strip(),
    }

    venta = None
    if id_venta not in (None, '', 0, '0'):
        try:
            venta = db.session.get(Venta, int(id_venta))
        except Exception:
            venta = None

    if not venta:
        venta = Venta.query.order_by(Venta.id_venta.desc()).first()

    if venta:
        detalles = venta.detalles.all()
        pagos = venta.pagos.all()
        total_pagado = sum(float(p.monto) for p in pagos)
        total = float(venta.total or 0)
        vuelto = max(0, total_pagado - total)
        try:
            subtotal = float(getattr(venta, 'subtotal', venta.total) or 0)
        except Exception:
            subtotal = float(total or 0)
        try:
            descuento = float(getattr(venta, 'descuento_monto', 0) or 0)
        except Exception:
            descuento = 0.0
    else:
        from types import SimpleNamespace
        from datetime import datetime
        venta = SimpleNamespace(
            id_venta=1,
            fecha_venta=datetime.utcnow(),
            total=28000,
            subtotal=30000,
            descuento_monto=2000,
            descuento_manual_monto=1500,
            descuento_fidelizacion_monto=500,
            beneficio_fidelizacion_tipo='descuento_monto',
            beneficio_fidelizacion_descripcion='Beneficio ejemplo',
            cliente=SimpleNamespace(nombre='CONSUMIDOR FINAL')
        )
        producto = SimpleNamespace(nombre='Producto de ejemplo')
        detalles = [SimpleNamespace(producto=producto, precio_unitario=28000, subtotal=28000, cantidad=1)]
        pagos = [SimpleNamespace(metodo=SimpleNamespace(nombre='Efectivo'), monto=28000)]
        total_pagado = 28000
        vuelto = 0
        subtotal = 30000
        descuento = 2000

    moneda_simbolo = '₲'
    preview = True
    pagos_resumen = _build_pagos_resumen(pagos)

    ctx = dict(
        venta=venta,
        detalles=detalles,
        pagos=pagos,
        pagos_resumen=pagos_resumen,
        empresa=empresa,
        subtotal=subtotal,
        descuento=descuento,
        descuento_manual=float(getattr(venta, 'descuento_manual_monto', 0) or 0),
        descuento_fidelizacion=float(getattr(venta, 'descuento_fidelizacion_monto', 0) or 0),
        total_pagado=total_pagado,
        vuelto=vuelto,
        preview=preview,
        moneda_simbolo=moneda_simbolo,
        footer_text=footer_text,
        paper_width_mm=paper_width_mm,
        beneficios_aplicados=[],
        beneficio_aplicado_texto='Gs. 500 de descuento · Beneficio ejemplo',
        beneficio_fidelizacion_tipo=str(getattr(venta, 'beneficio_fidelizacion_tipo', '') or ''),
        beneficio_fidelizacion_descripcion=str(getattr(venta, 'beneficio_fidelizacion_descripcion', '') or ''),
    )

    try:
        if template_html.strip() and not _should_use_builtin_sales_ticket_template(template_html):
            html = render_template_string(template_html, **ctx)
        else:
            html = render_template('ventas/ticket.html', **ctx)
        return jsonify({'success': True, 'html': _enforce_ticket_light_background(html)})
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
