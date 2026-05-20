"""
CRM - Contactos: lista, perfil, historial, notas, etiquetas
"""
import logging
from datetime import datetime

from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import desc

from app import db
from app.models.whatsapp import WhatsAppConversacion, WhatsAppMensaje
from app.models.crm_contacto import CrmContacto
from app.models.crm_etiqueta import CrmEtiqueta
from app.models.crm_nota_interna import CrmNotaInterna
from app.routes.crm import crm_bp

logger = logging.getLogger(__name__)


def _get_or_404(model, pk):
    obj = db.session.get(model, pk)
    if obj is None:
        abort(404)
    return obj


@crm_bp.route('/contactos', methods=['GET'])
@login_required
def lista_contactos():
    """Lista de contactos CRM."""
    etiquetas = CrmEtiqueta.query.filter_by(activa=True).order_by(CrmEtiqueta.nombre).all()
    return render_template('crm/contactos/lista.html', etiquetas=etiquetas)


@crm_bp.route('/api/contactos', methods=['GET'])
@login_required
def api_contactos():
    """API: lista paginada de contactos."""
    q = request.args.get('q', '').strip()
    id_etiqueta = request.args.get('etiqueta', type=int)
    pagina = request.args.get('pagina', 1, type=int)
    por_pagina = min(request.args.get('por_pagina', 30, type=int), 100)

    query = CrmContacto.query

    if q:
        like = f'%{q}%'
        from sqlalchemy import or_
        query = query.filter(
            or_(CrmContacto.telefono.like(like), CrmContacto.nombre.like(like))
        )

    if id_etiqueta:
        query = query.filter(CrmContacto.etiquetas.any(CrmEtiqueta.id == id_etiqueta))

    query = query.order_by(desc(CrmContacto.ultimo_contacto))
    total = query.count()
    contactos = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

    return jsonify({
        'items': [c.to_dict() for c in contactos],
        'total': total,
        'pagina': pagina,
        'paginas': (total + por_pagina - 1) // por_pagina,
    })


@crm_bp.route('/contactos/<int:id_contacto>', methods=['GET'])
@login_required
def perfil_contacto(id_contacto):
    """Perfil completo del contacto con historial."""
    contacto = _get_or_404(CrmContacto, id_contacto)
    etiquetas_disponibles = CrmEtiqueta.query.filter_by(activa=True).order_by(CrmEtiqueta.nombre).all()
    return render_template(
        'crm/contactos/perfil.html',
        contacto=contacto,
        etiquetas_disponibles=etiquetas_disponibles,
    )


@crm_bp.route('/api/contactos/<int:id_contacto>', methods=['GET'])
@login_required
def api_perfil_contacto(id_contacto):
    """API: datos completos del contacto."""
    contacto = _get_or_404(CrmContacto, id_contacto)

    conversaciones = WhatsAppConversacion.query.filter_by(
        telefono=contacto.telefono
    ).order_by(desc(WhatsAppConversacion.inicio_sesion)).all()

    conv_data = []
    for conv in conversaciones:
        ultimo = conv.mensajes.order_by(desc(WhatsAppMensaje.created_at)).first()
        conv_data.append({
            'id': conv.id,
            'modo': conv.modo,
            'activa': conv.activa,
            'inicio': conv.inicio_sesion.isoformat() if conv.inicio_sesion else None,
            'fin': conv.fin_sesion.isoformat() if conv.fin_sesion else None,
            'ultima_actividad': conv.ultima_actividad.isoformat() if conv.ultima_actividad else None,
            'ultimo_mensaje': ultimo.contenido[:80] if ultimo else '',
            'total_mensajes': conv.mensajes.count(),
        })

    notas = CrmNotaInterna.query.filter_by(id_contacto=id_contacto).order_by(
        desc(CrmNotaInterna.created_at)
    ).all()

    return jsonify({
        'contacto': contacto.to_dict(),
        'conversaciones': conv_data,
        'notas': [n.to_dict() for n in notas],
    })


@crm_bp.route('/api/contactos/<int:id_contacto>/etiquetas', methods=['POST'])
@login_required
def api_agregar_etiqueta(id_contacto):
    """Agregar etiqueta a un contacto."""
    contacto = _get_or_404(CrmContacto, id_contacto)
    data = request.get_json(silent=True) or {}
    id_etiqueta = data.get('id_etiqueta')
    if not id_etiqueta:
        return jsonify({'error': 'id_etiqueta requerido'}), 400

    etiqueta = _get_or_404(CrmEtiqueta, id_etiqueta)
    if etiqueta not in contacto.etiquetas:
        contacto.etiquetas.append(etiqueta)
        db.session.commit()

    return jsonify({'ok': True, 'etiquetas': [e.to_dict() for e in contacto.etiquetas]})


@crm_bp.route('/api/contactos/<int:id_contacto>/etiquetas/<int:id_etiqueta>', methods=['DELETE'])
@login_required
def api_quitar_etiqueta(id_contacto, id_etiqueta):
    """Quitar etiqueta de un contacto."""
    contacto = _get_or_404(CrmContacto, id_contacto)
    etiqueta = _get_or_404(CrmEtiqueta, id_etiqueta)
    if etiqueta in contacto.etiquetas:
        contacto.etiquetas.remove(etiqueta)
        db.session.commit()
    return jsonify({'ok': True, 'etiquetas': [e.to_dict() for e in contacto.etiquetas]})


@crm_bp.route('/api/contactos/<int:id_contacto>/notas', methods=['POST'])
@login_required
def api_agregar_nota(id_contacto):
    """Agregar nota interna a un contacto."""
    contacto = _get_or_404(CrmContacto, id_contacto)
    data = request.get_json(silent=True) or {}
    contenido = (data.get('contenido') or '').strip()
    if not contenido:
        return jsonify({'error': 'contenido requerido'}), 400

    id_conversacion = data.get('id_conversacion')
    if id_conversacion is not None:
        conv = _get_or_404(WhatsAppConversacion, id_conversacion)
        if conv.telefono != contacto.telefono:
            return jsonify({'error': 'La conversación no pertenece a este contacto'}), 400

    nota = CrmNotaInterna(
        id_contacto=id_contacto,
        id_conversacion=id_conversacion,
        id_usuario=current_user.id_usuario,
        contenido=contenido,
    )
    db.session.add(nota)
    db.session.commit()
    return jsonify({'ok': True, 'nota': nota.to_dict()}), 201


@crm_bp.route('/api/contactos/<int:id_contacto>/notas/<int:id_nota>', methods=['DELETE'])
@login_required
def api_eliminar_nota(id_contacto, id_nota):
    """Eliminar nota interna."""
    nota = CrmNotaInterna.query.filter_by(id=id_nota, id_contacto=id_contacto).first_or_404()
    if nota.id_usuario != current_user.id_usuario and not current_user.es_admin():
        abort(403)
    db.session.delete(nota)
    db.session.commit()
    return jsonify({'ok': True})


@crm_bp.route('/api/contactos/<int:id_contacto>', methods=['PATCH'])
@login_required
def api_editar_contacto(id_contacto):
    """Editar nombre/notas generales de un contacto."""
    contacto = _get_or_404(CrmContacto, id_contacto)
    data = request.get_json(silent=True) or {}
    if 'nombre' in data:
        contacto.nombre = (data['nombre'] or '').strip() or None
    if 'notas_generales' in data:
        contacto.notas_generales = (data['notas_generales'] or '').strip() or None
    if 'bloqueado' in data:
        contacto.bloqueado = bool(data['bloqueado'])
    db.session.commit()
    return jsonify({'ok': True, 'contacto': contacto.to_dict()})
