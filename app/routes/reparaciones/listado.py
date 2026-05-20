from math import ceil
from types import SimpleNamespace

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.models import Cliente, Reparacion

from .base import reparaciones_bp


@reparaciones_bp.route('/')
@login_required
def listar():
    if not current_user.tiene_permiso('ver_reparaciones'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reparaciones.', 'danger')
        return redirect(url_for('main.dashboard'))
    q_raw = (request.args.get('q') or '').strip()
    q_tokens = [t for t in q_raw.split() if len(t.strip()) >= 2][:4]
    q = ' '.join(q_tokens)
    stopwords = {'en', 'de', 'del', 'la', 'el', 'los', 'las', 'y', 'o', 'a', 'al', 'un', 'una', 'unos', 'unas'}
    q_tokens_filtrados = [t for t in q_tokens if t.lower() not in stopwords]
    tokens_busqueda = q_tokens_filtrados or q_tokens
    filtro_db = None
    if tokens_busqueda:
        condiciones = []
        for t in tokens_busqueda:
            like = f'%{t}%'
            or_terms = [
                Cliente.nombre.ilike(like),
                Reparacion.tipo_equipo.ilike(like),
                Reparacion.marca_modelo.ilike(like),
                Reparacion.imei_serie.ilike(like),
                Reparacion.falla_reportada.ilike(like),
                Reparacion.diagnostico_tecnico.ilike(like),
                Reparacion.solucion.ilike(like),
                Reparacion.estado.ilike(like),
                func.replace(Reparacion.estado, '_', ' ').ilike(like),
            ]
            if t.isdigit():
                try:
                    or_terms.append(Reparacion.id_reparacion == int(t))
                except Exception:
                    pass
            condiciones.append(db.or_(*or_terms))
        filtro_db = db.and_(*condiciones)

    def _clamp_per_page(value, default=12):
        try:
            value = int(value)
        except Exception:
            value = default
        return max(5, min(value, 50))

    def _build_pag(items, page, per_page, total):
        total = int(total or 0)
        page = int(page or 1)
        per_page = int(per_page or 12)
        pages = int(ceil(total / per_page)) if total > 0 else 0
        has_prev = page > 1
        has_next = pages > 0 and page < pages
        prev_num = page - 1 if has_prev else 1
        next_num = page + 1 if has_next else pages if pages > 0 else 1
        return SimpleNamespace(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            pages=pages,
            has_prev=has_prev,
            has_next=has_next,
            prev_num=prev_num,
            next_num=next_num,
        )

    def _page_query(query, page, per_page):
        offset = max(0, (int(page or 1) - 1) * int(per_page or 12))
        return query.offset(offset).limit(per_page).all()

    def _normalize_page(page, per_page, total):
        total = int(total or 0)
        per_page = int(per_page or 12)
        page = int(page or 1)
        pages = int(ceil(total / per_page)) if total > 0 else 0
        if pages <= 0:
            return 1, pages
        if page < 1:
            page = 1
        if page > pages:
            page = pages
        return page, pages

    pendientes_page = request.args.get('pendientes_page', 1, type=int)
    diagnostico_page = request.args.get('diagnostico_page', 1, type=int)
    espera_presupuesto_page = request.args.get('espera_presupuesto_page', 1, type=int)
    espera_page = request.args.get('espera_page', 1, type=int)
    en_proceso_page = request.args.get('en_proceso_page', 1, type=int)
    listos_page = request.args.get('listos_page', 1, type=int)
    no_se_pudo_page = request.args.get('no_se_pudo_page', 1, type=int)
    entregados_page = request.args.get('entregados_page', 1, type=int)
    cancelados_page = request.args.get('cancelados_page', 1, type=int)
    antiguos_page = request.args.get('antiguos_page', 1, type=int)

    pendientes_per_page = _clamp_per_page(request.args.get('pendientes_per_page', 12))
    diagnostico_per_page = _clamp_per_page(request.args.get('diagnostico_per_page', 12))
    espera_presupuesto_per_page = _clamp_per_page(request.args.get('espera_presupuesto_per_page', 12))
    espera_per_page = _clamp_per_page(request.args.get('espera_per_page', 12))
    en_proceso_per_page = _clamp_per_page(request.args.get('en_proceso_per_page', 12))
    listos_per_page = _clamp_per_page(request.args.get('listos_per_page', 12))
    no_se_pudo_per_page = _clamp_per_page(request.args.get('no_se_pudo_per_page', 12))
    entregados_per_page = _clamp_per_page(request.args.get('entregados_per_page', 12))
    cancelados_per_page = _clamp_per_page(request.args.get('cancelados_per_page', 12))
    antiguos_per_page = _clamp_per_page(request.args.get('antiguos_per_page', 12))

    conteos_query = db.session.query(Reparacion.estado, func.count(Reparacion.id_reparacion))
    if filtro_db is not None:
        conteos_query = conteos_query.join(Reparacion.cliente).filter(filtro_db)
    conteos_rows = conteos_query.group_by(Reparacion.estado).all()
    conteos = {str(estado): int(total or 0) for estado, total in (conteos_rows or [])}

    def _count_estado(*estados):
        objetivos = {str(e or '').strip().lower() for e in estados if str(e or '').strip()}
        total = 0
        for estado, cantidad in conteos.items():
            clave = str(estado or '').strip().lower()
            if clave in objetivos:
                total += int(cantidad or 0)
        return total

    pendientes_total = _count_estado('pendiente')
    diagnostico_total = _count_estado('diagnostico')
    espera_presupuesto_total = _count_estado('espera_presupuesto')
    espera_total = _count_estado('espera_repuesto', 'espera_cliente')
    en_proceso_total = _count_estado('en_proceso')
    listos_total = _count_estado('listo')
    no_se_pudo_total = _count_estado('no_se_pudo')
    entregados_total = _count_estado('entregado')
    cancelados_total = _count_estado('cancelado')
    antiguos_total = _count_estado('antiguos')

    base = Reparacion.query.options(
        joinedload(Reparacion.cliente),
        joinedload(Reparacion.tecnico),
    )
    if filtro_db is not None:
        base = base.join(Reparacion.cliente).filter(filtro_db)

    pendientes_page, _ = _normalize_page(pendientes_page, pendientes_per_page, pendientes_total)
    diagnostico_page, _ = _normalize_page(diagnostico_page, diagnostico_per_page, diagnostico_total)
    espera_presupuesto_page, _ = _normalize_page(espera_presupuesto_page, espera_presupuesto_per_page, espera_presupuesto_total)
    espera_page, _ = _normalize_page(espera_page, espera_per_page, espera_total)
    en_proceso_page, _ = _normalize_page(en_proceso_page, en_proceso_per_page, en_proceso_total)
    listos_page, _ = _normalize_page(listos_page, listos_per_page, listos_total)
    no_se_pudo_page, _ = _normalize_page(no_se_pudo_page, no_se_pudo_per_page, no_se_pudo_total)
    entregados_page, _ = _normalize_page(entregados_page, entregados_per_page, entregados_total)
    cancelados_page, _ = _normalize_page(cancelados_page, cancelados_per_page, cancelados_total)
    antiguos_page, _ = _normalize_page(antiguos_page, antiguos_per_page, antiguos_total)

    pendientes_items = _page_query(
        base.filter(Reparacion.estado == 'pendiente').order_by(Reparacion.fecha_ingreso.desc()),
        pendientes_page,
        pendientes_per_page,
    )
    diagnostico_items = _page_query(
        base.filter(Reparacion.estado == 'diagnostico').order_by(Reparacion.fecha_ingreso.desc()),
        diagnostico_page,
        diagnostico_per_page,
    )
    espera_presupuesto_items = _page_query(
        base.filter(Reparacion.estado == 'espera_presupuesto').order_by(Reparacion.fecha_ingreso.desc()),
        espera_presupuesto_page,
        espera_presupuesto_per_page,
    )
    espera_items = _page_query(
        base.filter(Reparacion.estado.in_(['espera_repuesto', 'espera_cliente'])).order_by(Reparacion.fecha_ingreso.desc()),
        espera_page,
        espera_per_page,
    )
    en_proceso_items = _page_query(
        base.filter(Reparacion.estado == 'en_proceso').order_by(Reparacion.fecha_ingreso.desc()),
        en_proceso_page,
        en_proceso_per_page,
    )
    listos_items = _page_query(
        base.filter(Reparacion.estado == 'listo').order_by(Reparacion.fecha_ingreso.desc()),
        listos_page,
        listos_per_page,
    )
    no_se_pudo_items = _page_query(
        base.filter(Reparacion.estado == 'no_se_pudo').order_by(Reparacion.fecha_ingreso.desc()),
        no_se_pudo_page,
        no_se_pudo_per_page,
    )
    entregados_items = _page_query(
        base.filter(Reparacion.estado == 'entregado').order_by(Reparacion.fecha_ingreso.desc()),
        entregados_page,
        entregados_per_page,
    )
    estado_normalizado = func.lower(func.trim(Reparacion.estado))
    cancelados_items = _page_query(
        base.filter(estado_normalizado == 'cancelado').order_by(Reparacion.fecha_ingreso.desc()),
        cancelados_page,
        cancelados_per_page,
    )
    antiguos_items = _page_query(
        base.filter(estado_normalizado == 'antiguos').order_by(Reparacion.fecha_ingreso.desc()),
        antiguos_page,
        antiguos_per_page,
    )

    pendientes_pag = _build_pag(pendientes_items, pendientes_page, pendientes_per_page, pendientes_total)
    diagnostico_pag = _build_pag(diagnostico_items, diagnostico_page, diagnostico_per_page, diagnostico_total)
    espera_presupuesto_pag = _build_pag(espera_presupuesto_items, espera_presupuesto_page, espera_presupuesto_per_page, espera_presupuesto_total)
    espera_pag = _build_pag(espera_items, espera_page, espera_per_page, espera_total)
    en_proceso_pag = _build_pag(en_proceso_items, en_proceso_page, en_proceso_per_page, en_proceso_total)
    listos_pag = _build_pag(listos_items, listos_page, listos_per_page, listos_total)
    no_se_pudo_pag = _build_pag(no_se_pudo_items, no_se_pudo_page, no_se_pudo_per_page, no_se_pudo_total)
    entregados_pag = _build_pag(entregados_items, entregados_page, entregados_per_page, entregados_total)
    cancelados_pag = _build_pag(cancelados_items, cancelados_page, cancelados_per_page, cancelados_total)
    antiguos_pag = _build_pag(antiguos_items, antiguos_page, antiguos_per_page, antiguos_total)

    estado_inicial = (request.args.get('estado') or 'pendiente').strip().lower()
    if estado_inicial not in {'pendiente', 'diagnostico', 'espera_presupuesto', 'espera', 'en_proceso', 'listo', 'no_se_pudo', 'entregado', 'cancelado', 'antiguos'}:
        estado_inicial = 'pendiente'

    return render_template(
        'reparaciones/listar.html',
        pendientes=pendientes_pag.items,
        diagnostico=diagnostico_pag.items,
        espera_presupuesto=espera_presupuesto_pag.items,
        espera=espera_pag.items,
        en_proceso=en_proceso_pag.items,
        listos=listos_pag.items,
        no_se_pudo=no_se_pudo_pag.items,
        entregados=entregados_pag.items,
        cancelados=cancelados_pag.items,
        antiguos=antiguos_pag.items,
        pendientes_pag=pendientes_pag,
        diagnostico_pag=diagnostico_pag,
        espera_presupuesto_pag=espera_presupuesto_pag,
        espera_pag=espera_pag,
        en_proceso_pag=en_proceso_pag,
        listos_pag=listos_pag,
        no_se_pudo_pag=no_se_pudo_pag,
        entregados_pag=entregados_pag,
        cancelados_pag=cancelados_pag,
        antiguos_pag=antiguos_pag,
        pendientes_total=pendientes_total,
        diagnostico_total=diagnostico_total,
        espera_presupuesto_total=espera_presupuesto_total,
        espera_total=espera_total,
        en_proceso_total=en_proceso_total,
        listos_total=listos_total,
        no_se_pudo_total=no_se_pudo_total,
        entregados_total=entregados_total,
        cancelados_total=cancelados_total,
        antiguos_total=antiguos_total,
        q=q,
        estado_inicial=estado_inicial
    )
