import argparse
from pathlib import Path

import fdb
import pandas as pd

SQL = """
SELECT
    P.ID_PRODUCTO,
    P.BARRAS,
    P.DESCRIPCION as PRODUCTO,
    COALESCE(C.DESCRIPTION, 'SIN CATEGORIA') as CATEGORIA,
    COALESCE(PRECIO_PUB.PRECIO, 0) as PRECIO_PUBLICO,
    COALESCE(PRECIO_MAY.PRECIO, 0) as PRECIO_MAYORISTA,
    (COALESCE(COMPRAS.TOTAL, 0) - COALESCE(VENTAS.TOTAL, 0)) as STOCK_ACTUAL
FROM PRODUCTO P
LEFT JOIN CLA_PRO C ON P.ID_CLA_PRO = C.ID_CLA_PRO
LEFT JOIN PRECIO_PRO PRECIO_PUB
    ON P.ID_PRODUCTO = PRECIO_PUB.ID_PRODUCTO
    AND PRECIO_PUB.ID_PRECIO = 1
LEFT JOIN PRECIO_PRO PRECIO_MAY
    ON P.ID_PRODUCTO = PRECIO_MAY.ID_PRODUCTO
    AND PRECIO_MAY.ID_PRECIO = 3
LEFT JOIN (
    SELECT ID_PRODUCTO, SUM(CANTIDAD) as TOTAL
    FROM COMPRA_D GROUP BY ID_PRODUCTO
) COMPRAS ON P.ID_PRODUCTO = COMPRAS.ID_PRODUCTO
LEFT JOIN (
    SELECT ID_PRODUCTO, SUM(CANTIDAD) as TOTAL
    FROM VENTA_DETALLE GROUP BY ID_PRODUCTO
) VENTAS ON P.ID_PRODUCTO = VENTAS.ID_PRODUCTO
"""

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--user", default="SYSDBA")
    parser.add_argument("--password", default="masterkey")
    parser.add_argument("--charset", default="WIN1252", choices=["WIN1252", "ISO8859_1"])
    parser.add_argument("--fdb-path", required=True)
    parser.add_argument("--out", default="productos_migracion.csv")
    args = parser.parse_args()

    fdb_path = Path(args.fdb_path).expanduser().resolve()
    if not fdb_path.exists():
        raise SystemExit(f"No existe el archivo: {fdb_path}")

    dsn = f"{args.host}:{str(fdb_path)}"

    conn = fdb.connect(
        dsn=dsn,
        user=args.user,
        password=args.password,
        charset=args.charset,
    )

    try:
        cur = conn.cursor()
        cur.execute(SQL)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(args.out, index=False, encoding="utf-8")

    print(f"OK: {len(df)} filas -> {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())