import argparse

from app import create_app
from cobranzas.services import backfill_cuentas_por_cobrar_ventas_credito


def parse_args():
    parser = argparse.ArgumentParser(description='Backfill idempotente de cuentas por cobrar para ventas credito.')
    parser.add_argument('--apply', action='store_true', help='Aplica cambios. Sin este flag corre en dry-run.')
    parser.add_argument('--limit', type=int, help='Limita la cantidad de ventas a revisar.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    app = create_app()
    with app.app_context():
        resultado = backfill_cuentas_por_cobrar_ventas_credito(
            dry_run=not args.apply,
            limit=args.limit,
        )
        print(f"dry_run={resultado['dry_run']}")
        print(f"detectadas={resultado['detectadas']}")
        print(f"creadas={resultado['creadas']}")
        if resultado['ventas']:
            print('ventas:')
            for venta in resultado['ventas']:
                print(
                    f"- venta={venta['id_venta']} cliente={venta['id_cliente']} saldo={venta['saldo_pendiente']}"
                )
        if resultado['omitidas']:
            print('omitidas:')
            for omitida in resultado['omitidas']:
                print(f"- venta={omitida['id_venta']} motivo={omitida['motivo']}")
