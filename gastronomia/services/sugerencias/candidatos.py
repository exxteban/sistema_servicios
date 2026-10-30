"""Vista previa explicable; consume asociaciones ya calculadas, nunca calcula tickets."""
from time import monotonic

from gastronomia.channel_models import GastronomiaProductoPrecioCanal
from gastronomia.services.channel_price_service import normalizar_canal_precio
from gastronomia.models import GastronomiaProducto, GastronomiaCategoria
from gastronomia.sugerencias_models import (
    GastronomiaSugerenciaRegla as Regla, GastronomiaSugerenciaExcluido as Excluido,
    GastronomiaSugerenciaPar as Par, GastronomiaSugerenciaOrigen as Origen,
)
from gastronomia.services.sugerencias.afinidad import Catalogo
from gastronomia.services.sugerencias import constantes as C
from gastronomia.services.sugerencias.aprendizaje import factores
from gastronomia.services.sugerencias.complementos import Complementos


def _coincide(tipo, numero, producto):
    return (tipo == 'cualquiera' or (tipo == 'producto' and numero == producto.id_producto)
            or (tipo == 'categoria' and numero == producto.categoria_id))


def previsualizar(cliente_id, productos_carrito, *, canal_precio=None, plazo=None):
    def comprobar_plazo():
        if plazo is not None and monotonic() >= plazo:
            raise TimeoutError('Presupuesto de consulta de sugerencias agotado')
    comprobar_plazo()
    canal = normalizar_canal_precio(canal_precio)
    productos = {p.id_producto: p for p in GastronomiaProducto.query.filter_by(cliente_id=cliente_id)}
    comprobar_plazo()
    precios = {p.producto_id: float(p.precio) for p in GastronomiaProductoPrecioCanal.query.filter_by(
        cliente_id=cliente_id, canal=canal,
    )} if canal else {}
    def precio(producto):
        return precios.get(producto.id_producto, float(producto.precio or 0))
    carrito = list(reversed(dict.fromkeys(reversed(productos_carrito))))
    origenes = [productos[p] for p in carrito if p in productos and productos[p].activo][-C.MAX_ORIGENES_CARRITO:]
    reglas = Regla.query.filter_by(cliente_id=cliente_id, activa=True).all()
    exclusiones = {(e.tipo, e.id_ref) for e in Excluido.query.filter_by(cliente_id=cliente_id)}
    comprobar_plazo()
    def excluido(p):
        return ('producto', p.id_producto) in exclusiones or ('categoria', p.categoria_id) in exclusiones
    origenes = [p for p in origenes if not excluido(p)]
    if not origenes:
        return {'sugerencias': [], 'descartados': []}
    catalogo = Catalogo((p.id_producto, p.nombre, p.categoria_id) for p in productos.values() if p.activo)
    conteos = {o.id_origen: o.pedidos for o in Origen.query.filter_by(cliente_id=cliente_id, nivel='producto')}
    pares = Par.query.filter_by(cliente_id=cliente_id).filter(
        ((Par.nivel == 'producto') & Par.id_origen.in_([p.id_producto for p in origenes]))
        | ((Par.nivel == 'categoria') & Par.id_origen.in_([p.categoria_id for p in origenes])),
    ).all()
    comprobar_plazo()
    candidatos = []
    aprendizaje = factores(cliente_id)
    categorias = {c.id_categoria: c.nombre for c in GastronomiaCategoria.query.filter_by(cliente_id=cliente_id)} if C.COMPLEMENTOS_ACTIVOS else {}
    complementos = Complementos(productos, categorias, carrito) if C.COMPLEMENTOS_ACTIVOS else None
    for origen in origenes:
        comprobar_plazo()
        def sumar(destino, fuente, puntaje, *, regla=None, par=None, motivo=None):
            afinidad, _ = catalogo.afinidad(origen.id_producto, destino.id_producto)
            peso = 1 if origen == origenes[-1] else .5
            candidatos.append(dict(
                id_producto=destino.id_producto, nombre=destino.nombre, id_origen=origen.id_producto,
                fuente=fuente, forzada=regla is not None, prioridad=regla.prioridad if regla else 0,
                puntaje=puntaje * (1 + afinidad / (1 + afinidad)) * peso
                * aprendizaje.get((origen.id_producto, destino.id_producto), {}).get('factor', 1),
                soporte=par.soporte if par else None, confianza=par.confianza if par else None,
                lift=par.lift if par else None,
                motivo=motivo or ('Regla del negocio' if regla else (
                    'Se suelen pedir juntos' if fuente == 'producto' else 'Asociación entre categorías')),
            ))
        for regla in reglas:
            if regla.tipo != 'forzar' or not _coincide(regla.origen_tipo, regla.origen_id, origen):
                continue
            destinos = [p for p in productos.values() if _coincide(regla.destino_tipo, regla.destino_id, p)]
            for destino in destinos:
                sumar(destino, 'regla', 1, regla=regla)
        nivel = 'producto' if conteos.get(origen.id_producto, 0) >= C.TICKETS_MINIMOS_PRODUCTO else 'categoria'
        for par in pares:
            if par.nivel != nivel or par.id_origen != (origen.id_producto if nivel == 'producto' else origen.categoria_id):
                continue
            destinos = [p for p in productos.values() if (
                p.id_producto == par.id_destino if nivel == 'producto' else p.categoria_id == par.id_destino)]
            destinos.sort(key=lambda p: (-catalogo.afinidad(origen.id_producto, p.id_producto)[0],
                                         -conteos.get(p.id_producto, 0), p.id_producto))
            for destino in destinos[:C.CANDIDATOS_POR_CATEGORIA]:
                sumar(destino, nivel, par.puntaje, par=par)
        if complementos:
            existentes = {c['id_producto'] for c in candidatos if c['id_origen'] == origen.id_producto}
            for destino, prioridad, motivo in complementos.para(origen):
                comprobar_plazo()
                if destino.id_producto not in existentes:
                    sumar(destino, 'complemento', C.PUNTAJE_COMPLEMENTO / (1 + prioridad), motivo=motivo)
    aceptados, descartados = {}, []
    principal = max(precio(productos[p]) for p in carrito if p in productos)
    for fila in candidatos:
        comprobar_plazo()
        p = productos[fila['id_producto']]
        origen = productos[fila['id_origen']]
        razon = None
        if not p.activo:
            razon = 'Producto inactivo'
        elif not p.disponible:
            razon = 'No disponible'
        elif p.control_stock_venta and (p.stock_disponible or 0) <= 0:
            razon = 'Sin stock'
        elif not p.visible:
            razon = 'No visible en el POS'
        elif p.id_producto in carrito:
            razon = 'Ya está en el pedido'
        elif excluido(p):
            razon = 'Excluido por el negocio'
        elif any(r.tipo == 'prohibir' and _coincide(r.origen_tipo, r.origen_id, origen)
                 and _coincide(r.destino_tipo, r.destino_id, p) for r in reglas):
            razon = 'Combinación prohibida'
        elif C.CONFLICTO_NOMBRES_ACTIVO and fila['fuente'] == 'categoria' and catalogo.conflicto(origen.id_producto, p.id_producto):
            razon = 'Conflicto de nombres'
        elif not fila['forzada'] and precio(p) > principal and (fila['lift'] or 0) < C.LIFT_PRECIO_ALTO:
            razon = 'Precio mayor que el plato principal'
        elif fila['fuente'] == 'complemento' and precio(p) > precio(origen):
            razon = 'Complemento más caro que el plato que lo pide'
        elif aprendizaje.get((origen.id_producto, p.id_producto), {}).get('oculto'):
            razon = 'Oculta por baja aceptación durante 30 días'
        if razon:
            descartados.append(dict(fila, descarte=razon))
            continue
        anterior = aceptados.get(p.id_producto)
        if anterior:
            total = anterior['puntaje'] + fila['puntaje']
            if (fila['forzada'], fila['prioridad'], fila['fuente'] != 'complemento', fila['puntaje']) > (
                anterior['forzada'], anterior['prioridad'], anterior['fuente'] != 'complemento', anterior['puntaje'],
            ):
                aceptados[p.id_producto] = fila
            aceptados[p.id_producto]['puntaje'] = total
        else:
            aceptados[p.id_producto] = fila
    salida = sorted(aceptados.values(), key=lambda f: (
        -f['forzada'], -f['prioridad'], f['fuente'] == 'complemento', -f['puntaje'],
        precio(productos[f['id_producto']]) if f['fuente'] == 'complemento' else 0, f['id_producto']))
    diversos, tipos_presentes = [], set()
    for fila in salida:
        tipo = complementos.tipos.get(fila['id_producto']) if complementos else None
        if fila['fuente'] == 'complemento' and tipo in tipos_presentes:
            continue
        diversos.append(fila)
        if tipo:
            tipos_presentes.add(tipo)
    return {'sugerencias': diversos[:C.MAX_EN_LISTA], 'descartados': descartados[:30]}
