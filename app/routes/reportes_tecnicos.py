from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, case
from sqlalchemy.orm import joinedload

from app import db
from app.models import DetalleReparacion, Reparacion, Usuario, Venta
from app.routes.reportes import _normalizar_fechas_reparaciones_invalidas
from app.services.reparaciones_tecnicos import usuarios_tecnicos_activos
from app.utils.helpers import parse_iso_date, today_local, utc_bounds_for_local_dates


reportes_tecnicos_bp = Blueprint('reportes_tecnicos', __name__)
ESTADOS_CERRADOS = {'listo', 'no_se_pudo', 'entregado', 'cancelado', 'antiguos'}
ESTADOS_TECNICOS_FINALIZADOS = {'listo', 'no_se_pudo', 'entregado'}
PER_PAGE = 20


def _parsear_filtros():
    raw_desde = request.args.get('desde')
    raw_hasta = request.args.get('hasta')
    raw_tecnico = request.args.get('id_tecnico', 0)
    estado = (request.args.get('estado') or 'todas').strip().lower()
    page = request.args.get('page', 1, type=int)

    desde = parse_iso_date(raw_desde) or (today_local() - timedelta(days=30))
    hasta = parse_iso_date(raw_hasta) or today_local()
    if desde > hasta:
        desde, hasta = hasta, desde

    try:
        tecnico_id = int(raw_tecnico or 0)
    except Exception:
        tecnico_id = 0

    if estado not in {'todas', 'abiertas', 'cerradas'}:
        estado = 'todas'
    if not page or page < 1:
        page = 1

    return desde, hasta, tecnico_id, estado, page


def _horas_delta(desde, hasta):
    if not desde or not hasta:
        return None
    delta = (hasta - desde).total_seconds() / 3600
    return round(delta, 2) if delta >= 0 else None


def _construir_contexto(desde, hasta, tecnico_id, estado, page):
    _normalizar_fechas_reparaciones_invalidas()
    start_utc, end_utc = utc_bounds_for_local_dates(desde, hasta)
    fecha_ref_expr = db.func.coalesce(Reparacion.fecha_toma_tecnico, Reparacion.fecha_ingreso)

    tecnicos = usuarios_tecnicos_activos()
    tecnicos_por_id = {int(u.id_usuario): u for u in tecnicos}
    filtro_tecnico_invalido = False
    if tecnico_id and tecnico_id not in tecnicos_por_id:
        tecnico_extra = db.session.get(Usuario, tecnico_id)
        if tecnico_extra:
            tecnicos.append(tecnico_extra)
            tecnicos_por_id[int(tecnico_extra.id_usuario)] = tecnico_extra
        else:
            filtro_tecnico_invalido = True
            tecnico_id = 0

    query = (
        Reparacion.query.options(
            joinedload(Reparacion.cliente),
            joinedload(Reparacion.tecnico),
        )
        .filter(
            Reparacion.id_usuario_tecnico.isnot(None),
            fecha_ref_expr >= start_utc,
            fecha_ref_expr < end_utc,
        )
    )
    if tecnico_id:
        query = query.filter(Reparacion.id_usuario_tecnico == tecnico_id)
    if estado == 'abiertas':
        query = query.filter(~Reparacion.estado.in_(ESTADOS_CERRADOS))
    elif estado == 'cerradas':
        query = query.filter(Reparacion.estado.in_(ESTADOS_CERRADOS))

    reparaciones = query.order_by(fecha_ref_expr.desc(), Reparacion.id_reparacion.desc()).all()
    reparacion_ids = [int(rep.id_reparacion) for rep in reparaciones]
    total = len(reparaciones)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    if page > pages:
        page = pages
    offset = (page - 1) * PER_PAGE
    historial_rows = reparaciones[offset:offset + PER_PAGE]

    ventas_map = {}
    detalles_map = {}
    if reparacion_ids:
        for row in (
            db.session.query(
                Venta.id_reparacion,
                db.func.max(Venta.total).label('total_venta'),
            )
            .filter(
                Venta.id_reparacion.in_(reparacion_ids),
                Venta.estado != 'anulada',
            )
            .group_by(Venta.id_reparacion)
            .all()
        ):
            ventas_map[int(row.id_reparacion)] = float(row.total_venta or 0)

        for row in (
            db.session.query(
                DetalleReparacion.id_reparacion,
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (DetalleReparacion.incluye_costo_final.is_(True), DetalleReparacion.subtotal),
                            else_=0,
                        )
                    ),
                    0,
                ).label('extras'),
                db.func.coalesce(
                    db.func.sum(
                        case(
                            (
                                and_(
                                    DetalleReparacion.incluye_costo_final.is_(True),
                                    DetalleReparacion.es_servicio.is_(True),
                                ),
                                DetalleReparacion.subtotal,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label('mano_obra_items'),
            )
            .filter(DetalleReparacion.id_reparacion.in_(reparacion_ids))
            .group_by(DetalleReparacion.id_reparacion)
            .all()
        ):
            detalles_map[int(row.id_reparacion)] = {
                'extras': float(row.extras or 0),
                'mano_obra_items': float(row.mano_obra_items or 0),
            }

    def _valor_generado(reparacion):
        rep_id = int(reparacion.id_reparacion)
        total_venta = float(ventas_map.get(rep_id) or 0)
        if total_venta > 0:
            return total_venta
        extras = float((detalles_map.get(rep_id) or {}).get('extras') or 0)
        return float(reparacion.costo_final or 0) + extras

    def _mano_obra_generada(reparacion):
        rep_id = int(reparacion.id_reparacion)
        mano_obra_items = float((detalles_map.get(rep_id) or {}).get('mano_obra_items') or 0)
        return float(reparacion.costo_final or 0) + mano_obra_items

    ranking_map = {}
    tiempos_toma = []
    tiempos_resolucion = []
    total_generado = 0.0
    finalizadas = 0
    entregas_cliente = 0
    en_curso = 0

    for rep in reparaciones:
        tid = int(rep.id_usuario_tecnico or 0)
        tecnico = rep.tecnico or tecnicos_por_id.get(tid)
        generado = _valor_generado(rep)
        mano_obra = _mano_obra_generada(rep)
        demora_toma = _horas_delta(rep.fecha_ingreso, rep.fecha_toma_tecnico)
        demora_resolucion = _horas_delta(rep.fecha_toma_tecnico, rep.fecha_listo_tecnico or rep.fecha_entrega)

        row = ranking_map.setdefault(tid, {
            'id_usuario': tid,
            'nombre': tecnico.nombre_completo if tecnico else 'Desconocido',
            'rol': ((tecnico.rol.nombre if tecnico and tecnico.rol else '') or '').strip(),
            'tomadas': 0,
            'finalizadas': 0,
            'entregas_cliente': 0,
            'en_curso': 0,
            'total_generado': 0.0,
            'mano_obra': 0.0,
            'sum_toma': 0.0,
            'count_toma': 0,
            'sum_resolucion': 0.0,
            'count_resolucion': 0,
        })

        row['tomadas'] += 1
        row['total_generado'] += generado
        row['mano_obra'] += mano_obra

        if (rep.estado or '').strip().lower() in ESTADOS_TECNICOS_FINALIZADOS or rep.fecha_listo_tecnico:
            row['finalizadas'] += 1
            finalizadas += 1
        if rep.fecha_entrega:
            row['entregas_cliente'] += 1
            entregas_cliente += 1
        if (rep.estado or '').strip().lower() not in ESTADOS_CERRADOS:
            row['en_curso'] += 1
            en_curso += 1
        if demora_toma is not None:
            row['sum_toma'] += demora_toma
            row['count_toma'] += 1
            tiempos_toma.append(demora_toma)
        if demora_resolucion is not None:
            row['sum_resolucion'] += demora_resolucion
            row['count_resolucion'] += 1
            tiempos_resolucion.append(demora_resolucion)

        total_generado += generado

    ranking = []
    for row in ranking_map.values():
        row['ticket_promedio'] = round(row['total_generado'] / max(row['tomadas'], 1), 2)
        row['promedio_toma_horas'] = round(row['sum_toma'] / row['count_toma'], 2) if row['count_toma'] else None
        row['promedio_resolucion_horas'] = (
            round(row['sum_resolucion'] / row['count_resolucion'], 2)
            if row['count_resolucion'] else None
        )
        ranking.append(row)

    ranking.sort(
        key=lambda item: (
            float(item['total_generado'] or 0),
            int(item['finalizadas'] or 0),
            int(item['tomadas'] or 0),
        ),
        reverse=True,
    )

    historial = []
    for rep in historial_rows:
        historial.append({
            'id_reparacion': int(rep.id_reparacion),
            'cliente': rep.cliente.nombre if rep.cliente else '—',
            'tecnico': rep.tecnico.nombre_completo if rep.tecnico else 'Sin asignar',
            'equipo': ' - '.join([x for x in [rep.tipo_equipo, rep.marca_modelo] if x]) or 'Sin equipo',
            'estado': rep.estado_display,
            'fecha_ingreso': rep.fecha_ingreso,
            'fecha_toma': rep.fecha_toma_tecnico,
            'fecha_listo': rep.fecha_listo_tecnico,
            'fecha_entrega': rep.fecha_entrega,
            'generado': _valor_generado(rep),
            'mano_obra': _mano_obra_generada(rep),
            'demora_toma_horas': _horas_delta(rep.fecha_ingreso, rep.fecha_toma_tecnico),
            'demora_resolucion_horas': _horas_delta(rep.fecha_toma_tecnico, rep.fecha_listo_tecnico or rep.fecha_entrega),
            'url': url_for('reparaciones.detalle', id=rep.id_reparacion),
        })

    resumen = {
        'tomadas': total,
        'finalizadas': finalizadas,
        'entregas_cliente': entregas_cliente,
        'en_curso': en_curso,
        'total_generado': round(total_generado, 2),
        'promedio_toma_horas': round(sum(tiempos_toma) / len(tiempos_toma), 2) if tiempos_toma else None,
        'promedio_resolucion_horas': (
            round(sum(tiempos_resolucion) / len(tiempos_resolucion), 2)
            if tiempos_resolucion else None
        ),
    }

    return {
        'desde': desde,
        'hasta': hasta,
        'tecnicos': tecnicos,
        'id_tecnico': tecnico_id,
        'estado': estado,
        'ranking': ranking,
        'historial': historial,
        'resumen': resumen,
        'paginacion': {
            'page': page,
            'pages': pages,
            'total': total,
            'has_prev': page > 1,
            'has_next': page < pages,
            'prev_num': page - 1 if page > 1 else 1,
            'next_num': page + 1 if page < pages else pages,
        },
        'filtro_tecnico_invalido': filtro_tecnico_invalido,
    }


@reportes_tecnicos_bp.route('/historial-tecnicos')
@login_required
def historial_tecnicos():
    if not current_user.tiene_permiso('ver_reporte_ventas'):
        if getattr(current_user, 'modo_demo', False):
            flash('Modo demo: esta acción está deshabilitada.', 'warning')
        else:
            flash('No tienes permisos para ver reportes técnicos.', 'danger')
        return redirect(url_for('reportes.index'))

    desde, hasta, tecnico_id, estado, page = _parsear_filtros()
    ctx = _construir_contexto(desde, hasta, tecnico_id, estado, page)
    if ctx.get('filtro_tecnico_invalido'):
        flash('Técnico inválido para el filtro.', 'warning')
    return render_template('reportes/historial_tecnicos.html', **ctx)
