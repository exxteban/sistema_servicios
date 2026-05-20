from sqlalchemy import func

from app import db
from app.models import PresupuestoEmpresarial
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.utils.helpers import today_local


def _base_presupuestos(desde, hasta):
    return PresupuestoEmpresarial.query.filter(
        PresupuestoEmpresarial.fecha_emision >= desde,
        PresupuestoEmpresarial.fecha_emision <= hasta,
    )


def _serializar_presupuesto(p: PresupuestoEmpresarial) -> dict:
    return {
        'id_presupuesto_empresarial': p.id_presupuesto_empresarial,
        'numero_presupuesto': p.numero_presupuesto_display,
        'fecha_emision': p.fecha_emision.isoformat() if p.fecha_emision else None,
        'valido_hasta': p.valido_hasta.isoformat() if p.valido_hasta else None,
        'destinatario_nombre': p.destinatario_nombre,
        'destinatario_ruc': p.destinatario_ruc,
        'asunto': p.asunto,
        'total': float(p.total or 0),
        'cantidad_items': len(p.items),
        'cantidad_impresiones': int(p.cantidad_impresiones or 0),
    }


def presupuestos_resumen(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_presupuestos(rango['desde'], rango['hasta'])
    fila = base.with_entities(
        func.count(PresupuestoEmpresarial.id_presupuesto_empresarial).label('cantidad'),
        func.coalesce(func.sum(PresupuestoEmpresarial.total), 0).label('total'),
        func.coalesce(func.sum(PresupuestoEmpresarial.descuento), 0).label('descuento'),
    ).first()
    hoy = today_local()
    return {
        **rango,
        'cantidad_presupuestos': int(getattr(fila, 'cantidad', 0) or 0),
        'total_presupuestado': float(getattr(fila, 'total', 0) or 0),
        'descuento_total': float(getattr(fila, 'descuento', 0) or 0),
        'vigentes': int(base.filter(PresupuestoEmpresarial.fecha_emision >= hoy).count()),
        'vencidos_estimados': int(base.filter(PresupuestoEmpresarial.fecha_emision < hoy).count()),
    }


def presupuestos_pendientes(args: dict, usuario=None) -> dict:
    top_n = normalizar_top_n(args.get('top_n'), default=10)
    hoy = today_local()
    filas = (
        PresupuestoEmpresarial.query
        .filter(PresupuestoEmpresarial.fecha_emision <= hoy)
        .order_by(PresupuestoEmpresarial.fecha_emision.desc(), PresupuestoEmpresarial.id_presupuesto_empresarial.desc())
        .limit(top_n)
        .all()
    )
    return {'presupuestos': [_serializar_presupuesto(p) for p in filas]}


def presupuestos_conversion(args: dict, usuario=None) -> dict:
    rango = resolver_rango(args)
    base = _base_presupuestos(rango['desde'], rango['hasta'])
    total = int(base.count())
    impresos = int(base.filter(PresupuestoEmpresarial.cantidad_impresiones > 0).count())
    return {
        **rango,
        'cantidad_presupuestos': total,
        'presupuestos_impresos': impresos,
        'ratio_impresion_pct': round((impresos / total) * 100, 2) if total else 0,
        'nota': 'Conversion aproximada: el modulo no guarda estado aprobado/rechazado; se usa impresion como senal de avance.',
    }


def presupuesto_detalle(args: dict, usuario=None) -> dict:
    presupuesto = None
    if args.get('id_presupuesto_empresarial'):
        presupuesto = db.session.get(PresupuestoEmpresarial, int(args.get('id_presupuesto_empresarial') or 0))
    if presupuesto is None and args.get('id_venta'):
        presupuesto = db.session.get(PresupuestoEmpresarial, int(args.get('id_venta') or 0))
    referencia = (args.get('referencia') or args.get('busqueda') or '').strip()
    if presupuesto is None and referencia:
        patron = f'%{referencia}%'
        candidatos = PresupuestoEmpresarial.query.filter(
            db.or_(
                PresupuestoEmpresarial.destinatario_nombre.ilike(patron),
                PresupuestoEmpresarial.destinatario_ruc.ilike(patron),
                PresupuestoEmpresarial.asunto.ilike(patron),
            )
        ).limit(6).all()
        if len(candidatos) != 1:
            return {
                'encontrado': False,
                'requiere_seleccion': bool(candidatos),
                'candidatos': [_serializar_presupuesto(p) for p in candidatos],
                'error': 'presupuesto_no_encontrado' if not candidatos else 'presupuesto_ambiguo',
            }
        presupuesto = candidatos[0]
    if presupuesto is None:
        return {'encontrado': False, 'error': 'presupuesto_no_encontrado'}
    data = _serializar_presupuesto(presupuesto)
    data.update({
        'items': presupuesto.items[:30],
        'observaciones': presupuesto.observaciones,
        'condiciones': presupuesto.condiciones,
    })
    return {'encontrado': True, 'presupuesto': data}
