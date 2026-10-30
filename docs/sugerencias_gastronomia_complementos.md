# Complementos iniciales de gastronomía

Implementados el 30/10/2026 para que un menú pequeño pueda sugerir desde el
primer pedido, sin historial ni reglas cargadas. Complementan el cálculo
estadístico existente; no cambian sus umbrales ni inventan ventas.

## Comportamiento

| Producto del pedido | Complementos del menú |
| --- | --- |
| Hamburguesa, sándwich, lomito, pancho o milanesa | Papas, gaseosa, agua, jugo |
| Pizza o empanada | Gaseosa, agua, jugo |
| Café o infusión | Medialuna, chipa, tostado, torta y similares |
| Panificado o torta | Café o infusión |

Reconoce nombres explícitos normalizados y categorías. Por ejemplo, «Gus
Doble» dentro de «Hamburguesas» recibe complementos aunque su nombre comercial
no diga hamburguesa. Un producto desconocido no genera relaciones por intuición.
Los alias y relaciones se mantienen en `complementos_datos.py`, separados del
clasificador `complementos.py`.

Las reglas del dueño y las asociaciones calculadas preceden a estos
complementos. Se conserva como máximo un complemento por tipo para evitar que
tres variantes de Coca ocupen la franja. A igualdad de puntaje se favorece el
precio menor. Con el menú de QA, «Gus Doble» ofrece «Papas fritas», «Coca
Personal» y «Agua mineral», aunque no haya ventas ni reglas.

## Filtros y límites

- Usa únicamente productos de la instalación y del mismo `cliente_id`.
- Respeta disponibilidad, stock controlado, visibilidad, exclusiones,
  prohibiciones y fatiga. Usa el precio del canal actual y evita un complemento
  más caro que el producto que lo origina.
- Si ya hay bebida en el carrito, deja de ofrecer bebidas iniciales. Lo mismo
  ocurre con guarniciones y panificados. También reconoce inclusiones explícitas
  en el nombre («con papas», «+ bebida») o en descripciones con «incluye».
- Los combos y promociones no generan complementos de fábrica, y un combo
  presente en el carrito suspende esta fuente porque sus componentes pueden
  estar implícitos. Las reglas y asociaciones siguen funcionando.
- No ofrece alcohol ni otra hamburguesa como complemento de una hamburguesa.
  No deduce restricciones dietarias ni interpreta texto libre con IA.
- El motivo visible es «Complemento habitual para hamburguesas», por ejemplo;
  no atribuye soporte, confianza o lift a relaciones sin ventas.

No crea reglas, ventas ni tablas nuevas. Funciona al actualizar el código con el
sugeridor ya habilitado. Si la configuración del módulo está apagada, continúa
sin mostrar sugerencias. La constante `COMPLEMENTOS_ACTIVOS` permite desactivar
esta fuente a nivel de instalación.

## Validación

`test_gastronomia_sugerencias_complementos.py` cubre 16 casos: arranque sin
historial, diversidad, filtros, carrito, inclusiones, reglas, asociaciones,
canales, aislamiento, familias gastronómicas, combos y módulo apagado.
Nueve escenarios reutilizables también pasaron en MariaDB 10.4.32 mediante el
runner temporal `scripts/probar_sugerencias_mysql.py`.
La regresión del módulo completo pasó con 77 pruebas de backend y 10 de JavaScript.

QA de navegador sobre SQLite en memoria, con cinco productos y sin ventas ni
reglas: cargar «Gus Doble» muestra papas, Coca Personal y agua, con motivos
explícitos y el configurador habitual del POS. La demo remota requiere actualizar
el código y reiniciar el servicio para incorporar esta fuente. Al agregar la
Coca, la franja conserva solo las papas; a 390 px no hay desbordamiento horizontal.
