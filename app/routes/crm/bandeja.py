"""
CRM - Bandeja unificada de conversaciones
"""
import logging
from datetime import datetime, timedelta

from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_, desc, func, and_
from sqlalchemy.orm import joinedload

from app import db
from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje, WhatsAppAsignacionConversacion
from app.models.crm_contacto import CrmContacto, crm_contacto_etiquetas
from app.models.crm_etiqueta import CrmEtiqueta
from app.routes.crm import crm_bp, usuario_puede_ver_bandeja_jefe

logger = logging.getLogger(__name__)


def _bloquear_si_no_es_jefe():
    if usuario_puede_ver_bandeja_jefe(current_user):
        return None
    if request.path.startswith('/crm/api/'):
        return jsonify({'error': 'Sin permisos', 'mensaje': 'La bandeja general está reservada para jefatura'}), 403
    return redirect(url_for('crm.panel_asesor'))


def _build_bandeja_payload(
    *,
    estado: str = 'todas',
    id_etiqueta: int | None = None,
    id_asesor: int | None = None,
    busqueda: str = '',
    solo_activas: bool = True,
    pagina: int = 1,
    por_pagina: int = 30,
):
    por_pagina = min(int(por_pagina or 30), 100)
    pagina = max(1, int(pagina or 1))

    query = WhatsAppConversacion.query.options(
        joinedload(WhatsAppConversacion.asignacion).joinedload(WhatsAppAsignacionConversacion.asesor)
    )

    if solo_activas:
        ahora = datetime.utcnow()
        limite_bot = ahora - timedelta(hours=8)
        query = query.filter(
            WhatsAppConversacion.activa == True,
            or_(
                WhatsAppConversacion.modo.in_(['asesor', 'derivacion']),
                and_(
                    WhatsAppConversacion.modo == 'bot',
                    WhatsAppConversacion.ultima_actividad >= limite_bot,
                ),
            ),
        )

    if estado and estado != 'todas':
        query = query.filter_by(modo=estado)

    if busqueda:
        like = f'%{busqueda}%'
        query = query.filter(
            or_(
                WhatsAppConversacion.telefono.like(like),
                WhatsAppConversacion.nombre_contacto.like(like),
            )
        )

    if id_etiqueta:
        query = query.join(
            CrmContacto, CrmContacto.telefono == WhatsAppConversacion.telefono
        ).filter(
            CrmContacto.etiquetas.any(CrmEtiqueta.id == id_etiqueta)
        )

    if id_asesor:
        query = query.join(
            WhatsAppAsignacionConversacion,
            WhatsAppAsignacionConversacion.id_conversacion == WhatsAppConversacion.id
        ).filter(
            WhatsAppAsignacionConversacion.id_asesor == id_asesor,
            WhatsAppAsignacionConversacion.estado.in_(['pendiente', 'activa'])
        )

    query = query.order_by(desc(WhatsAppConversacion.ultima_actividad))
    total = query.count()
    conversaciones = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    telefonos = [c.telefono for c in conversaciones]
    contactos = (
        CrmContacto.query.filter(CrmContacto.telefono.in_(telefonos)).all()
        if telefonos
        else []
    )
    contacto_by_tel = {c.telefono: c for c in contactos}

    etiquetas_by_contacto_id: dict[int, list[CrmEtiqueta]] = {}
    contacto_ids = [c.id for c in contactos if c.id is not None]
    if contacto_ids:
        rows = (
            db.session.query(crm_contacto_etiquetas.c.id_contacto, CrmEtiqueta)
            .join(CrmEtiqueta, CrmEtiqueta.id == crm_contacto_etiquetas.c.id_etiqueta)
            .filter(crm_contacto_etiquetas.c.id_contacto.in_(contacto_ids))
            .all()
        )
        for id_contacto, etiqueta in rows:
            etiquetas_by_contacto_id.setdefault(int(id_contacto), []).append(etiqueta)

    ultimo_msg_by_conv_id: dict[int, WhatsAppMensaje] = {}
    conv_ids = [c.id for c in conversaciones if c.id is not None]
    if conv_ids:
        subq = (
            db.session.query(
                WhatsAppMensaje.id_conversacion.label('id_conversacion'),
                func.max(WhatsAppMensaje.created_at).label('max_created_at')
            )
            .filter(WhatsAppMensaje.id_conversacion.in_(conv_ids))
            .group_by(WhatsAppMensaje.id_conversacion)
            .subquery()
        )
        ultimos = (
            db.session.query(WhatsAppMensaje)
            .join(
                subq,
                (WhatsAppMensaje.id_conversacion == subq.c.id_conversacion)
                & (WhatsAppMensaje.created_at == subq.c.max_created_at)
            )
            .all()
        )
        for m in ultimos:
            ultimo_msg_by_conv_id[int(m.id_conversacion)] = m

    items = []
    for conv in conversaciones:
        contacto = contacto_by_tel.get(conv.telefono)
        ultimo_msg = ultimo_msg_by_conv_id.get(int(conv.id))
        asignacion = conv.asignacion

        if contacto:
            etiquetas = [
                e.to_dict()
                for e in etiquetas_by_contacto_id.get(int(contacto.id), [])
            ]
        else:
            etiquetas = []

        items.append({
            'id': conv.id,
            'telefono': conv.telefono,
            'nombre': conv.nombre_contacto or (contacto.nombre if contacto else conv.telefono),
            'modo': conv.modo,
            'activa': conv.activa,
            'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
            'ultimo_mensaje': (ultimo_msg.contenido or '')[:100] if ultimo_msg else '',
            'ultimo_mensaje_direccion': ultimo_msg.direccion if ultimo_msg else None,
            'asesor': asignacion.asesor.nombre_completo if asignacion and asignacion.asesor else None,
            'etiquetas': etiquetas,
            'id_contacto': contacto.id if contacto else None,
        })

    return {
        'items': items,
        'total': total,
        'pagina': pagina,
        'por_pagina': por_pagina,
        'paginas': (total + por_pagina - 1) // por_pagina,
    }


@crm_bp.route('/', methods=['GET'])
@crm_bp.route('/bandeja', methods=['GET'])
@login_required
def bandeja():
    """Bandeja unificada de conversaciones activas."""
    bloqueo = _bloquear_si_no_es_jefe()
    if bloqueo is not None:
        return bloqueo
    etiquetas = CrmEtiqueta.query.filter_by(activa=True).order_by(CrmEtiqueta.nombre).all()
    initial_payload = _build_bandeja_payload()
    return render_template('crm/bandeja/index.html', etiquetas=etiquetas, initial_payload=initial_payload)


@crm_bp.route('/api/bandeja', methods=['GET'])
@login_required
def api_bandeja():
    """API: lista de conversaciones con filtros."""
    bloqueo = _bloquear_si_no_es_jefe()
    if bloqueo is not None:
        return bloqueo
    estado = request.args.get('estado', 'todas')  # todas, bot, asesor, derivacion
    id_etiqueta = request.args.get('etiqueta', type=int)
    id_asesor = request.args.get('asesor', type=int)
    busqueda = request.args.get('q', '').strip()
    solo_activas = request.args.get('activas', '1') == '1'
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = min(request.args.get('por_pagina', 30, type=int), 100)
    payload = _build_bandeja_payload(
        estado=estado,
        id_etiqueta=id_etiqueta,
        id_asesor=id_asesor,
        busqueda=busqueda,
        solo_activas=solo_activas,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return jsonify(payload)


@crm_bp.route('/bandeja/<int:id_conv>', methods=['GET'])
@login_required
def detalle_conversacion(id_conv):
    """Vista de detalle de una conversación específica."""
    bloqueo = _bloquear_si_no_es_jefe()
    if bloqueo is not None:
        return bloqueo
    from app.models.crm_contacto import CrmContacto as _Contacto
    conv = WhatsAppConversacion.query.get_or_404(id_conv)
    contacto = _Contacto.query.filter_by(telefono=conv.telefono).first()
    return render_template(
        'crm/bandeja/detalle.html',
        conv=conv,
        contacto=contacto,
        puede_operar_panel=False,
    )


@crm_bp.route('/api/buscar', methods=['GET'])
@login_required
def api_buscar():
    """Búsqueda global: teléfono, nombre, contenido de mensaje."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'resultados': []})

    like = f'%{q}%'
    resultados = []

    # Buscar en contactos
    contactos = CrmContacto.query.filter(
        or_(
            CrmContacto.telefono.like(like),
            CrmContacto.nombre.like(like),
        )
    ).limit(10).all()

    for c in contactos:
        resultados.append({
            'tipo': 'contacto',
            'id': c.id,
            'texto': f'{c.nombre or c.telefono} ({c.telefono})',
            'url': f'/crm/contactos/{c.id}',
        })

    # Buscar en mensajes
    mensajes = WhatsAppMensaje.query.filter(
        WhatsAppMensaje.contenido.like(like)
    ).order_by(desc(WhatsAppMensaje.created_at)).limit(10).all()

    vistos = set()
    for m in mensajes:
        conv = m.conversacion
        if conv and conv.id not in vistos:
            vistos.add(conv.id)
            resultados.append({
                'tipo': 'mensaje',
                'id': conv.id,
                'texto': f'{conv.nombre_contacto or conv.telefono}: {m.contenido[:60]}',
                'url': f'/crm/bandeja/{conv.id}',
            })

    return jsonify({'resultados': resultados[:15]})
