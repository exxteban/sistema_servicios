from sqlalchemy.orm import joinedload

from app.models import ClienteServicio


def build_pos_data_from_cliente_servicio(asignacion: ClienteServicio):
    data = build_pos_data_from_cliente_servicios([asignacion] if asignacion else [])
    if not data:
        return None
    data['id'] = int(asignacion.id_cliente_servicio)
    return data


def parse_cliente_servicio_ids(raw_values):
    if raw_values in (None, '', [], ()):
        return []

    if not isinstance(raw_values, (list, tuple, set)):
        raw_values = [raw_values]

    ids = []
    seen = set()
    for raw_value in raw_values:
        if raw_value in (None, ''):
            continue
        partes = raw_value if isinstance(raw_value, (list, tuple, set)) else str(raw_value).split(',')
        for parte in partes:
            texto = str(parte or '').strip()
            if not texto:
                continue
            try:
                numero = int(texto)
            except Exception:
                continue
            if numero <= 0 or numero in seen:
                continue
            seen.add(numero)
            ids.append(numero)
    return ids


def get_cliente_servicios_cobrables(cliente_servicio_ids, id_cliente=None):
    ids = parse_cliente_servicio_ids(cliente_servicio_ids)
    if not ids:
        return []

    asignaciones = (
        ClienteServicio.query.options(
            joinedload(ClienteServicio.servicio),
            joinedload(ClienteServicio.venta),
        )
        .filter(ClienteServicio.id_cliente_servicio.in_(ids))
        .all()
    )
    asignaciones_por_id = {
        int(asignacion.id_cliente_servicio): asignacion
        for asignacion in asignaciones
    }

    resultado = []
    cliente_resuelto = None if id_cliente in (None, '') else int(id_cliente)
    for asignacion_id in ids:
        asignacion = asignaciones_por_id.get(int(asignacion_id))
        if not asignacion:
            raise ValueError('Servicio del cliente no encontrado')
        if cliente_resuelto is None:
            cliente_resuelto = int(asignacion.id_cliente)
        if int(asignacion.id_cliente) != int(cliente_resuelto):
            raise ValueError('Las asignaciones seleccionadas deben pertenecer al mismo cliente')
        if asignacion.id_venta:
            raise ValueError(f'El servicio del cliente #{asignacion.id_cliente_servicio} ya fue cobrado en la venta #{asignacion.id_venta}')
        if (asignacion.estado or '').strip().lower() == 'cancelado':
            raise ValueError(f'El servicio del cliente #{asignacion.id_cliente_servicio} está cancelado')
        if getattr(asignacion, 'servicio', None) is None:
            raise ValueError(f'El servicio asociado a la asignación #{asignacion.id_cliente_servicio} ya no existe')
        resultado.append(asignacion)

    return resultado


def build_pos_data_from_cliente_servicios(asignaciones):
    asignaciones = [asignacion for asignacion in (asignaciones or []) if asignacion]
    if not asignaciones:
        return None

    items = []
    observaciones = []
    ids = []
    cliente_id = None

    for asignacion in asignaciones:
        servicio = getattr(asignacion, 'servicio', None)
        if servicio is None:
            continue
        precio_pactado = float(asignacion.precio_pactado or servicio.precio or 0)
        precio_base = float(servicio.precio or 0)
        costo_pactado = float(asignacion.costo_pactado or servicio.costo or 0)
        cantidad = max(int(asignacion.cantidad or 1), 1)
        cliente_id = int(asignacion.id_cliente)
        ids.append(int(asignacion.id_cliente_servicio))
        if (asignacion.observaciones or '').strip():
            observaciones.append(f'#{asignacion.id_cliente_servicio}: {(asignacion.observaciones or "").strip()}')

        items.append({
            'tipo': 'servicio',
            'id': int(servicio.id_servicio),
            'id_servicio': int(servicio.id_servicio),
            'cliente_servicio_id': int(asignacion.id_cliente_servicio),
            'codigo': (servicio.codigo or '').strip(),
            'nombre': (servicio.nombre or '').strip(),
            'precio': precio_pactado,
            'precio_base': precio_base,
            'cantidad': cantidad,
            'es_servicio': True,
            'stock': 0,
            'stock_minimo': 0,
            'iva': int(servicio.porcentaje_iva or 0),
            'precio_manual': abs(precio_pactado - precio_base) > 0.0001,
            'costo_pactado': costo_pactado,
        })

    if not items:
        return None

    return {
        'id': ids[0],
        'ids': ids,
        'cliente_id': cliente_id,
        'observaciones': ' | '.join(observaciones),
        'items': items,
    }
