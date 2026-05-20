from datetime import date

from sqlalchemy import func

from app import db
from app.models import Cliente, CrmPlantilla, Venta
from app.services.ia_backoffice.periods import normalizar_top_n, resolver_rango
from app.services.inteligencia.clientes import obtener_inteligencia_clientes
from app.utils.helpers import utc_bounds_for_local_dates


def _money(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _fecha_corte(args: dict | None) -> date:
    return resolver_rango(args)['hasta']


def clientes_resumen_inteligencia(args: dict | None = None, usuario=None) -> dict:
    fecha_corte = _fecha_corte(args)
    data = obtener_inteligencia_clientes(fecha_corte)
    return {
        'fecha_corte': fecha_corte.isoformat(),
        'total_para_activar': int(data.get('total_para_activar') or 0),
        'segmentos': data.get('segmentos') or {},
        'valiosos_dormidos': int(data.get('valiosos_dormidos') or 0),
        'frecuentes_en_pausa': int(data.get('frecuentes_en_pausa') or 0),
        'clientes_destacados': (data.get('clientes_para_activar') or [])[:5],
    }


def clientes_para_contactar(args: dict | None = None, usuario=None) -> dict:
    top_n = normalizar_top_n((args or {}).get('top_n'))
    fecha_corte = _fecha_corte(args)
    data = obtener_inteligencia_clientes(fecha_corte)
    candidatos = (data.get('para_activar_detalle') or [])[:top_n]
    return {
        'fecha_corte': fecha_corte.isoformat(),
        'top_n': top_n,
        'clientes': [_contacto_payload(cliente) for cliente in candidatos],
        'criterio': 'Clientes dormidos priorizados por valor, frecuencia y dias sin compra.',
    }


def _contacto_payload(cliente: dict) -> dict:
    tiene_whatsapp = bool(cliente.get('whatsapp_url'))
    return {
        'id_cliente': cliente.get('id_cliente'),
        'nombre': cliente.get('nombre') or '',
        'prioridad': cliente.get('prioridad') or 'baja',
        'motivo': cliente.get('motivo') or '',
        'accion': cliente.get('accion') or 'Revisar cliente',
        'dias_inactivo': int(cliente.get('dias_inactivo') or 0),
        'cantidad_compras': int(cliente.get('cantidad_compras') or 0),
        'ultima_compra_label': cliente.get('ultima_compra_label') or '',
        'total_gastado_label': cliente.get('total_gastado_label') or '',
        'ticket_promedio_label': cliente.get('ticket_promedio_label') or '',
        'telefono_label': cliente.get('telefono_label') or '',
        'canal_sugerido': 'whatsapp' if tiene_whatsapp else 'llamada/manual',
        'tiene_whatsapp': tiene_whatsapp,
    }


def clientes_top_valor(args: dict | None = None, usuario=None) -> dict:
    rango = resolver_rango(args)
    top_n = normalizar_top_n((args or {}).get('top_n'))
    inicio_utc, fin_utc = utc_bounds_for_local_dates(rango['desde'], rango['hasta'])
    filas = (
        db.session.query(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.telefono,
            Cliente.tipo,
            Cliente.nivel_estrellas,
            Cliente.saldo_pendiente,
            func.count(Venta.id_venta).label('cantidad_compras'),
            func.coalesce(func.sum(Venta.total), 0).label('total_gastado'),
            func.max(Venta.fecha_venta).label('ultima_compra'),
        )
        .join(Venta, Venta.id_cliente == Cliente.id_cliente)
        .filter(
            Cliente.activo.is_(True),
            Cliente.id_cliente != 1,
            Venta.estado == 'completada',
            Venta.fecha_venta >= inicio_utc,
            Venta.fecha_venta < fin_utc,
        )
        .group_by(
            Cliente.id_cliente,
            Cliente.nombre,
            Cliente.telefono,
            Cliente.tipo,
            Cliente.nivel_estrellas,
            Cliente.saldo_pendiente,
        )
        .order_by(func.sum(Venta.total).desc(), func.count(Venta.id_venta).desc(), Cliente.nombre.asc())
        .limit(top_n)
        .all()
    )
    return {
        'periodo_label': rango['periodo_label'],
        'top_n': top_n,
        'clientes': [_top_valor_payload(row) for row in filas],
    }


def _top_valor_payload(row) -> dict:
    compras = int(row.cantidad_compras or 0)
    total = _money(row.total_gastado)
    return {
        'id_cliente': int(row.id_cliente),
        'nombre': row.nombre or '',
        'telefono': row.telefono or '',
        'tipo': row.tipo or '',
        'nivel_estrellas': int(row.nivel_estrellas or 0),
        'cantidad_compras': compras,
        'total_gastado': total,
        'ticket_promedio': round(total / compras, 2) if compras else 0,
        'saldo_pendiente': _money(row.saldo_pendiente),
        'ultima_compra': row.ultima_compra.isoformat() if row.ultima_compra else None,
    }


def crm_sugerir_mensaje(args: dict | None = None, usuario=None) -> dict:
    data = args or {}
    cliente_info = _resolver_cliente_para_mensaje(data)
    if not cliente_info:
        return {'encontrado': False, 'envio_automatico': False}
    plantilla = _seleccionar_plantilla(data.get('objetivo'))
    borrador = _armar_borrador(cliente_info, plantilla)
    return {
        'encontrado': True,
        'envio_automatico': False,
        'requiere_confirmacion_envio': True,
        'cliente': _contacto_payload(cliente_info),
        'plantilla_usada': plantilla.titulo if plantilla else None,
        'borrador': borrador,
        'nota': 'Borrador generado para revision humana; esta tool no envia mensajes.',
    }


def _resolver_cliente_para_mensaje(args: dict) -> dict | None:
    id_cliente = args.get('id_cliente')
    candidatos = obtener_inteligencia_clientes(_fecha_corte(args)).get('para_activar_detalle') or []
    if id_cliente:
        try:
            id_cliente = int(id_cliente)
        except Exception:
            id_cliente = None
        for candidato in candidatos:
            if int(candidato.get('id_cliente') or 0) == id_cliente:
                return candidato
        cliente = db.session.get(Cliente, id_cliente) if id_cliente else None
        if cliente:
            return _cliente_basico(cliente)
    return candidatos[0] if candidatos else None


def _cliente_basico(cliente: Cliente) -> dict:
    return {
        'id_cliente': cliente.id_cliente,
        'nombre': cliente.nombre or '',
        'prioridad': 'media',
        'motivo': 'Cliente seleccionado manualmente para contacto comercial.',
        'accion': 'Enviar mensaje personalizado',
        'dias_inactivo': 0,
        'cantidad_compras': 0,
        'telefono_label': cliente.telefono or 'Sin telefono cargado',
        'whatsapp_url': None,
    }


def _seleccionar_plantilla(objetivo: str | None):
    categoria = (objetivo or 'reactivacion').strip().lower()
    return (
        CrmPlantilla.query.filter(CrmPlantilla.activa.is_(True))
        .filter(CrmPlantilla.categoria.in_([categoria, 'reactivacion', 'general']))
        .order_by((CrmPlantilla.categoria == categoria).desc(), CrmPlantilla.orden.asc(), CrmPlantilla.titulo.asc())
        .first()
    )


def _armar_borrador(cliente: dict, plantilla) -> str:
    nombre = (cliente.get('nombre') or 'cliente').strip()
    motivo = (cliente.get('motivo') or 'queriamos acercarte una propuesta').strip()
    accion = (cliente.get('accion') or 'Responder cuando puedas').strip()
    if plantilla and plantilla.contenido:
        texto = plantilla.contenido
        for clave, valor in {'{nombre}': nombre, '{cliente}': nombre, '{motivo}': motivo, '{accion}': accion}.items():
            texto = texto.replace(clave, valor)
        return texto.strip()
    return (
        f'Hola {nombre}, como estas? Te escribimos porque {motivo.lower()} '
        f'Si te sirve, podemos ayudarte hoy. {accion}.'
    )
