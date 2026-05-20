import argparse
import os
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


def _default_fdb_path() -> Path | None:
    base = Path(__file__).resolve().parent
    candidate_dir = base / "Base de datos"
    if not candidate_dir.exists():
        return None
    preferred = candidate_dir / "BASE.FDB"
    if preferred.exists():
        return preferred
    fdbs = sorted(candidate_dir.glob("*.FDB"), key=lambda p: p.stat().st_mtime, reverse=True)
    return fdbs[0] if fdbs else None


def _resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def export_csv(
    fdb_path: Path,
    out_path: Path,
    host: str,
    user: str,
    password: str,
    charset: str,
    dry_run: bool,
    limit: int | None,
) -> int:
    dsn = f"{host}:{str(fdb_path)}"
    conn = fdb.connect(
        dsn=dsn,
        user=user,
        password=password,
        charset=charset,
    )

    try:
        cur = conn.cursor()
        sql = SQL
        if limit is not None:
            sql = f"SELECT FIRST {int(limit)} * FROM ({SQL.rstrip().rstrip(';')})"
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=cols)
    if dry_run:
        print(f"Filas: {len(df)}")
        print("Columnas:", list(df.columns))
        print(df.head(10).to_string(index=False))
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"OK: {len(df)} filas -> {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("FB_HOST") or "localhost")
    parser.add_argument("--user", default=os.environ.get("FB_USER") or "SYSDBA")
    parser.add_argument("--password", default=os.environ.get("FB_PASSWORD") or "masterkey")
    parser.add_argument("--charset", default=os.environ.get("FB_CHARSET") or "WIN1252", choices=["WIN1252", "ISO8859_1"])
    parser.add_argument("--fdb-path", default=os.environ.get("FB_FDB_PATH") or None)
    parser.add_argument("--out", default="Base de datos/productos_migracion.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    fdb_path = _resolve_path(args.fdb_path) or _default_fdb_path()
    if not fdb_path:
        print("No se encontró ningún .FDB. Usá --fdb-path \"C:\\RUTA\\A\\BASE.FDB\"")
        return 2
    if not fdb_path.exists():
        print(f"No existe el archivo: {fdb_path}")
        return 2

    out_path = _resolve_path(args.out) or Path(args.out)

    return export_csv(
        fdb_path=fdb_path,
        out_path=out_path,
        host=str(args.host),
        user=str(args.user),
        password=str(args.password),
        charset=str(args.charset),
        dry_run=bool(args.dry_run),
        limit=args.limit,
    )


if __name__ == "__main__":
    raise SystemExit(main())

