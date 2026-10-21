"""Diagnostico (solo lectura): por que el historial de ventas sale vacio.

Uso en el servidor, dentro del repo de la instancia:
    set -a; . /etc/sistema_breakingfat.env; set +a
    .venv/bin/python scripts/diagnostico_ventas.py 2026-10-01 2026-10-21
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app import create_app, db  # noqa: E402
from app.models import MovimientoCaja, Venta  # noqa: E402
from app.utils.helpers import utc_bounds_for_local_dates  # noqa: E402
from gastronomia.models import GastronomiaPedido, GastronomiaPedidoPago  # noqa: E402


def main():
    desde = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today().replace(day=1)
    hasta = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    inicio, fin = utc_bounds_for_local_dates(desde, hasta)

    print('Ventas totales en la base:', Venta.query.count())
    print('Ventas por estado:', db.session.query(Venta.estado, func.count()).group_by(Venta.estado).all())
    print('Ultima venta:', db.session.query(func.max(Venta.fecha_venta)).scalar())
    print('Pagos de pedidos gastronomia:', GastronomiaPedidoPago.query.count(),
          '| sin venta:', GastronomiaPedidoPago.query.filter(GastronomiaPedidoPago.id_venta.is_(None)).count())
    print('Pedidos por estado:', db.session.query(GastronomiaPedido.estado, func.count())
          .group_by(GastronomiaPedido.estado).all())

    print(f'\nIngresos de caja {desde} a {hasta} por referencia:')
    filas = (
        db.session.query(MovimientoCaja.referencia_tipo, func.count(), func.sum(MovimientoCaja.monto))
        .filter(MovimientoCaja.tipo == 'ingreso',
                MovimientoCaja.fecha_movimiento >= inicio, MovimientoCaja.fecha_movimiento < fin)
        .group_by(MovimientoCaja.referencia_tipo)
        .all()
    )
    for referencia, cantidad, total in filas:
        print(f'  {referencia or "(manual)"}: {cantidad} movimientos, total {float(total or 0):,.0f}')

    print('\nUltimos 15 ingresos del periodo:')
    for mov in (
        MovimientoCaja.query
        .filter(MovimientoCaja.tipo == 'ingreso',
                MovimientoCaja.fecha_movimiento >= inicio, MovimientoCaja.fecha_movimiento < fin)
        .order_by(MovimientoCaja.fecha_movimiento.desc()).limit(15)
    ):
        print(f'  #{mov.id_movimiento_caja} {mov.fecha_movimiento} {float(mov.monto):,.0f} '
              f'ref={mov.referencia_tipo}:{mov.referencia_id} usuario={mov.id_usuario} motivo={mov.motivo!r}')


if __name__ == '__main__':
    with create_app().app_context():
        main()
