"""Guia de "donde esta cada cosa" con caminos y enlaces reales del sistema.

Los enlaces salen de url_for (nunca los inventa el modelo) y se filtran por permisos.
"""
from __future__ import annotations

from flask import url_for

from gastronomia.services.asistente import resolver
from gastronomia.services.permisos import (
    PERMISO_CAJA,
    PERMISO_COCINA,
    PERMISO_DELIVERY,
    PERMISO_MENU,
    PERMISO_POS,
    PERMISO_SALON,
    tiene_permiso_gastronomia,
)

DASH = 'Dashboard de Gastronomia (pestana "Dashboard", arriba a la izquierda)'
CARGA = f'{DASH} > bajando, seccion "Carga y configuracion"'


def _menu(main='menu', entry=None, lista=None) -> str:
    params = {'gastro_main_tab': main}
    if entry:
        params['gastro_entry_tab'] = entry
    if lista:
        params['gastro_menu_tab'] = lista
    return url_for('gastronomia.menu_config', **params)


def _temas() -> dict:
    return {
        'empezar': {
            'permiso': PERMISO_MENU,
            'pasos': [
                ('1. Categorias del menu (Hamburguesas, Bebidas...)', f'{CARGA} > "Cargar menu" > pestana "Menu" > boton "Categoria"', _menu('menu', 'categoria')),
                ('2. Platos con precio', f'{CARGA} > "Cargar menu" > "Producto y extras"', _menu('menu', 'producto')),
                ('3. Insumos y recetas (para stock y costos)', f'{CARGA} > "Cargar menu" > pestana "Stock y recetas"', _menu('stock')),
                ('4. Mesas del salon', f'{CARGA} > "Configurar salon"', 'salon'),
                ('5. Abrir caja y vender', f'{DASH} > "Operacion en vivo" > "Caja" y luego "POS Touch" (tecla F2)', 'caja'),
            ],
            'consejo': 'Si no queres cargar a mano, en "Cargar menu" esta "Empezar con plantilla", o pedimelo a mi y lo cargo yo.',
        },
        'categorias': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu" > boton "Categoria"',
            'url': _menu('menu', 'categoria'), 'titulo': 'Cargar categorias',
        },
        'platos': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu" > boton "Producto y extras"',
            'url': _menu('menu', 'producto'), 'titulo': 'Cargar un plato',
            'consejo': 'Para ver o editar lo ya cargado: pestana "Menu cargado" > "Productos".',
        },
        'menu_cargado': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu cargado" > "Productos"',
            'url': _menu('menu-cargado', lista='productos'), 'titulo': 'Ver menu cargado',
        },
        'plantilla': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu" > "Empezar con plantilla"',
            'url': _menu('menu', 'plantilla'), 'titulo': 'Empezar con plantilla',
        },
        'extras': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > "Producto y extras" > elegir el plato > campos "Adicionales" e "Ingredientes removibles"',
            'url': _menu('menu', 'producto'), 'titulo': 'Extras del plato',
        },
        'recetas': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Stock y recetas" > "Recetas por plato"',
            'url': _menu('stock'), 'titulo': 'Recetas e insumos',
            'consejo': 'Ahi mismo estan "Precios de ingredientes" (para calcular costo y ganancia) e "Insumos del inventario central".',
        },
        'insumos': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Stock y recetas" > "Insumos del inventario central" (precios en "Precios de ingredientes")',
            'url': _menu('stock'), 'titulo': 'Insumos',
        },
        'precios_canales': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu cargado" > "PedidosYa" o "Monchis"',
            'url': _menu('menu-cargado', lista='pedidosya'), 'titulo': 'Precios por canal',
        },
        'promociones': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu cargado" > "Promociones"',
            'url': _menu('menu-cargado', lista='promociones'), 'titulo': 'Promociones',
        },
        'pantalla_tv': {
            'permiso': PERMISO_MENU,
            'camino': f'{CARGA} > "Cargar menu" > pestana "Menu cargado" > "Pantalla TV"',
            'url': _menu('menu-cargado', lista='tv'), 'titulo': 'Pantalla TV',
        },
        'mesas': {
            'permiso': PERMISO_SALON,
            'camino': f'{CARGA} > "Configurar salon"',
            'url': 'salon', 'titulo': 'Configurar salon',
            'consejo': 'Para ver ocupacion en vivo: Dashboard > "Operacion en vivo" > "Salon" (F8).',
        },
        'vender': {
            'permiso': PERMISO_POS,
            'camino': f'{DASH} > "Operacion en vivo" > "POS Touch" (tecla F2)',
            'url': url_for('gastronomia.pos'), 'titulo': 'POS Touch',
            'consejo': 'Antes conviene tener la caja abierta.',
        },
        'caja': {
            'permiso': PERMISO_CAJA,
            'camino': f'{DASH} > "Operacion en vivo" > "Caja"',
            'url': 'caja', 'titulo': 'Caja',
        },
        'cocina': {
            'permiso': PERMISO_COCINA,
            'camino': f'{DASH} > "Operacion en vivo" > "Cocina" (tecla F9)',
            'url': url_for('gastronomia.cocina'), 'titulo': 'Cocina',
        },
        'delivery': {
            'permiso': PERMISO_DELIVERY,
            'camino': f'{DASH} > "Operacion en vivo" > "Delivery"',
            'url': url_for('gastronomia.delivery'), 'titulo': 'Delivery',
        },
    }


def _url(valor: str) -> str:
    especiales = {'salon': 'gastronomia.salon_config', 'caja': 'gastronomia.caja'}
    return url_for(especiales[valor]) if valor in especiales else valor


def temas_disponibles() -> list[str]:
    return list(_temas().keys())


def donde_esta(cliente_id: int, args: dict) -> dict:
    tema = str(args.get('tema') or 'empezar').strip().lower()
    temas = _temas()
    if tema not in temas:
        return {'error': f'Tema desconocido. Usa uno de: {", ".join(temas)}'}
    info = temas[tema]
    if not tiene_permiso_gastronomia(info['permiso']):
        return {'tema': tema, 'sin_permiso': True, 'mensaje': 'Este usuario no tiene permiso para esa pantalla; que lo pida al administrador.'}
    if tema == 'empezar':
        return {
            'tema': tema,
            'pasos': [{'paso': p, 'camino': c, 'enlace': _url(u)} for p, c, u in info['pasos']],
            'consejo': info['consejo'],
        }
    salida = {'tema': tema, 'camino': info['camino'], 'enlace': _url(info['url']), 'titulo_enlace': info['titulo']}
    if info.get('consejo'):
        salida['consejo'] = info['consejo']
    if tema in {'platos', 'extras', 'recetas'} and args.get('plato'):
        plato = resolver.plato(cliente_id, args['plato'])
        if plato:
            salida['plato'] = plato.nombre
            salida['como_abrir_plato'] = (
                f'Para editar "{plato.nombre}": pestana "Menu cargado" > "Productos" > boton editar en esa fila'
                if tema != 'recetas' else f'En "Recetas por plato" elegi "{plato.nombre}" en la lista de platos'
            )
            if tema != 'recetas':
                salida['enlace_lista'] = _menu('menu-cargado', lista='productos')
    return salida
