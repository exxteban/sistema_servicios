import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app
from sqlalchemy import func

from app import db
from app.models import Configuracion, PresupuestoEmpresarial

PRESUPUESTO_CONDICIONES_DEFAULT = (
    "Precios expresados en guaraníes e incluyen únicamente los conceptos detallados. "
    "La validez del presente presupuesto está sujeta al plazo indicado. "
    "Cualquier cambio de alcance o agregado se cotiza por separado."
)


def parse_decimal(value) -> Decimal:
    raw = str(value or '').strip()
    if not raw:
        return Decimal('0')
    raw = raw.replace('₲', '').replace('Gs.', '').replace('Gs', '').replace(' ', '')
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    elif ',' in raw:
        raw = raw.replace(',', '.')
    elif raw.count('.') > 1:
        raw = raw.replace('.', '')
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def parse_int(value, default=0) -> int:
    try:
        return int(str(value or '').strip())
    except (TypeError, ValueError):
        return int(default)


def parse_date(value: str | None) -> date | None:
    raw = (value or '').strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def normalize_text(value: str | None) -> str:
    return ' '.join((value or '').strip().split())


def next_budget_number() -> int:
    ultimo = db.session.query(func.max(PresupuestoEmpresarial.numero_presupuesto)).scalar() or 0
    return int(ultimo) + 1


def company_payload() -> dict:
    nombre = (
        Configuracion.obtener('nombre_empresa_ui', '')
        or Configuracion.obtener('nombre_empresa', 'RYJCELL')
        or 'RYJCELL'
    )
    logo_rel = (Configuracion.obtener('logo_empresa_ui_path', '') or '').strip()
    logo_pdf_src = ''
    if logo_rel:
        try:
            logo_pdf_src = str((Path(current_app.static_folder) / logo_rel).resolve())
        except Exception:
            logo_pdf_src = ''
    return {
        'nombre': nombre.strip() or 'RYJCELL',
        'direccion': Configuracion.obtener('direccion_empresa', '') or '',
        'telefono': Configuracion.obtener('telefono_empresa', '') or '',
        'ruc': Configuracion.obtener('ruc_empresa', '') or '',
        'logo_rel': logo_rel,
        'logo_pdf_src': logo_pdf_src,
        'logo_file_uri': logo_pdf_src,
    }


def build_items_from_form(form) -> tuple[list[dict], Decimal]:
    descriptions = form.getlist('item_descripcion[]')
    quantities = form.getlist('item_cantidad[]')
    prices = form.getlist('item_precio_unitario[]')
    items: list[dict] = []
    subtotal = Decimal('0')

    max_len = max(len(descriptions), len(quantities), len(prices), 1)
    for idx in range(max_len):
        descripcion = (descriptions[idx] if idx < len(descriptions) else '').strip()
        cantidad = parse_decimal(quantities[idx] if idx < len(quantities) else '')
        precio_unitario = parse_decimal(prices[idx] if idx < len(prices) else '')
        if not descripcion and cantidad == 0 and precio_unitario == 0:
            continue
        total_linea = cantidad * precio_unitario
        subtotal += total_linea
        items.append({
            'descripcion': descripcion,
            'cantidad': float(cantidad),
            'precio_unitario': float(precio_unitario),
            'total': float(total_linea),
        })

    return items, subtotal


def build_form_seed(form=None) -> dict:
    form = form or {}
    descriptions = form.getlist('item_descripcion[]') if hasattr(form, 'getlist') else []
    quantities = form.getlist('item_cantidad[]') if hasattr(form, 'getlist') else []
    prices = form.getlist('item_precio_unitario[]') if hasattr(form, 'getlist') else []

    items = []
    max_len = max(len(descriptions), len(quantities), len(prices), 2)
    for idx in range(max_len):
        items.append({
            'descripcion': descriptions[idx] if idx < len(descriptions) else '',
            'cantidad': quantities[idx] if idx < len(quantities) else ('1' if idx == 0 else ''),
            'precio_unitario': prices[idx] if idx < len(prices) else '',
        })

    return {
        'fecha_emision': form.get('fecha_emision', date.today().strftime('%Y-%m-%d')),
        'validez_dias': form.get('validez_dias', '7'),
        'cliente_busqueda': form.get('cliente_busqueda', ''),
        'id_cliente': form.get('id_cliente', ''),
        'destinatario_nombre': form.get('destinatario_nombre', ''),
        'destinatario_contacto': form.get('destinatario_contacto', ''),
        'destinatario_ruc': form.get('destinatario_ruc', ''),
        'destinatario_telefono': form.get('destinatario_telefono', ''),
        'destinatario_email': form.get('destinatario_email', ''),
        'destinatario_direccion': form.get('destinatario_direccion', ''),
        'asunto': form.get('asunto', 'Presupuesto empresarial'),
        'descuento': form.get('descuento', ''),
        'observaciones': form.get('observaciones', ''),
        'condiciones': form.get('condiciones', PRESUPUESTO_CONDICIONES_DEFAULT),
        'item_rows': items,
    }


def payload_from_request(form) -> tuple[dict, list[str]]:
    items, subtotal = build_items_from_form(form)
    descuento = parse_decimal(form.get('descuento'))
    total = subtotal - descuento
    if total < 0:
        total = Decimal('0')

    payload = {
        'fecha_emision': parse_date(form.get('fecha_emision')) or date.today(),
        'validez_dias': max(parse_int(form.get('validez_dias'), 7), 0),
        'id_cliente': form.get('id_cliente', type=int),
        'destinatario_nombre': normalize_text(form.get('destinatario_nombre')),
        'destinatario_contacto': normalize_text(form.get('destinatario_contacto')),
        'destinatario_ruc': (form.get('destinatario_ruc') or '').strip(),
        'destinatario_telefono': (form.get('destinatario_telefono') or '').strip(),
        'destinatario_email': (form.get('destinatario_email') or '').strip(),
        'destinatario_direccion': (form.get('destinatario_direccion') or '').strip(),
        'asunto': normalize_text(form.get('asunto')) or 'Presupuesto empresarial',
        'observaciones': (form.get('observaciones') or '').strip(),
        'condiciones': (form.get('condiciones') or '').strip() or PRESUPUESTO_CONDICIONES_DEFAULT,
        'items': items,
        'subtotal': subtotal,
        'descuento': descuento,
        'total': total,
    }

    errores = []
    if not payload['destinatario_nombre']:
        errores.append('Debe indicar el nombre o razón social de la empresa.')
    if not payload['asunto']:
        errores.append('Debe indicar el asunto del presupuesto.')
    if not items:
        errores.append('Debe agregar al menos un ítem al presupuesto.')
    else:
        invalid_items = [item for item in items if not item['descripcion'] or item['cantidad'] <= 0]
        if invalid_items:
            errores.append('Cada ítem debe tener descripción y cantidad mayor a cero.')
    if payload['descuento'] < 0:
        errores.append('El descuento no puede ser negativo.')

    return payload, errores


def serialize_items_for_template(items) -> str:
    return json.dumps(items or [], ensure_ascii=False)
