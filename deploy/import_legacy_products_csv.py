import argparse
import csv
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.models.producto import Producto, Categoria
from app.models.proveedor import Proveedor
from app.models.usuario import Usuario


PROVEEDOR_DEFAULT = "Proveedor General"


def _app_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_csv_path(csv_path: str | None, csv_dir: str | None, auto: bool) -> Path | None:
    base = _app_dir()
    if csv_path:
        p = Path(csv_path)
        if not p.is_absolute():
            p = (base / p).resolve()
        return p

    search_dir = base / (csv_dir or "Base de datos")
    if not search_dir.exists() or not search_dir.is_dir():
        return None

    csvs = sorted(search_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        return None
    if auto:
        return csvs[0]
    return csvs[0]


def _clean_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    s = str(value).strip()
    if not s:
        return Decimal("0")
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _clean_int(value) -> int:
    d = _clean_decimal(value)
    try:
        return int(d.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        try:
            return int(d)
        except Exception:
            return 0


def _parse_csv_fields(line: str) -> list[str]:
    reader = csv.reader(StringIO(line), delimiter=",", quotechar='"', skipinitialspace=True)
    for row in reader:
        return [str(v).strip() for v in row]
    return []


def _maybe_unwrap_outer_quoted_line(line: str) -> str | None:
    s = (line or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"' and '""' in s:
        inner = s[1:-1].replace('""', '"')
        return inner
    return None


def _iter_rows(file_obj):
    start_pos = file_obj.tell()
    header_line = file_obj.readline()
    if not header_line:
        return

    unwrapped_header = _maybe_unwrap_outer_quoted_line(header_line)
    if unwrapped_header is not None:
        header_fields = _parse_csv_fields(unwrapped_header)
        if len(header_fields) > 1:
            for raw in file_obj:
                if not raw or not raw.strip():
                    continue
                unwrapped = _maybe_unwrap_outer_quoted_line(raw)
                fields = _parse_csv_fields(unwrapped if unwrapped is not None else raw)
                if not fields:
                    continue
                row = {header_fields[i]: (fields[i] if i < len(fields) else "") for i in range(len(header_fields))}
                yield row
            return

    file_obj.seek(start_pos)
    sample = file_obj.read(2048)
    file_obj.seek(start_pos)
    try:
        csv.Sniffer().sniff(sample)
    except Exception:
        pass
    reader = csv.DictReader(file_obj)
    for row in reader:
        yield row



def _get_or_create_proveedor() -> Proveedor:
    prov = Proveedor.query.filter_by(nombre=PROVEEDOR_DEFAULT).first()
    if not prov:
        prov = Proveedor(nombre=PROVEEDOR_DEFAULT, ruc="88888888-8", telefono="0900000000")
        db.session.add(prov)
        db.session.commit()
    return prov


def _get_admin_user_id() -> int | None:
    user = Usuario.query.filter_by(username="admin").first()
    return getattr(user, "id_usuario", None) if user else None


def _get_or_create_categoria(nombre_categoria: str | None, cache: dict[str, Categoria]) -> Categoria:
    nombre = (nombre_categoria or "").strip()
    if not nombre:
        nombre = "Sin Categoría"
    nombre = nombre.upper()

    cached = cache.get(nombre)
    if cached:
        return cached

    cat = Categoria.query.filter_by(nombre=nombre).first()
    if not cat:
        cat = Categoria(nombre=nombre, descripcion="Importada automáticamente", activo=True)
        db.session.add(cat)
        db.session.commit()
    cache[nombre] = cat
    return cat


def _row_value(row: dict, *keys: str) -> str:
    for k in keys:
        if k in row and row.get(k) is not None:
            return str(row.get(k)).strip()
    return ""


def importar_productos(csv_path: Path, dry_run: bool = False, limit: int | None = None, only_missing: bool = False) -> int:
    config_name = (os.environ.get("APP_CONFIG") or "default").strip() or "default"
    app = create_app(config_name)
    categorias_cache: dict[str, Categoria] = {}

    with app.app_context():
        if not csv_path.exists():
            print(f"No se encuentra el CSV: {csv_path}")
            return 2

        prov = _get_or_create_proveedor()
        user_id = _get_admin_user_id()

        count = 0
        errores = 0
        duplicados = 0
        actualizados = 0
        nuevos = 0
        omitidos = 0

        encodings = ["cp1252", "latin-1", "utf-8-sig", "utf-8"]
        file_obj = None
        for enc in encodings:
            try:
                file_obj = open(csv_path, mode="r", encoding=enc, newline="")
                file_obj.read(4096)
                file_obj.seek(0)
                break
            except Exception:
                try:
                    if file_obj:
                        file_obj.close()
                except Exception:
                    pass
                file_obj = None
        if not file_obj:
            print(f"No se pudo abrir el CSV: {csv_path}")
            return 2

        try:
            for row in _iter_rows(file_obj):
                if limit is not None and count >= limit:
                    break

                try:
                    nombre = _row_value(row, "PRODUCTO", "DESCRIPCION", "NOMBRE")
                    codigo_barras = _row_value(row, "BARRAS", "CODIGO_BARRAS", "CODIGO")
                    if codigo_barras in {"", '""', "0"}:
                        codigo_barras = ""

                    nombre_categoria = _row_value(row, "CATEGORIA", "CATEGORÍA", "RUBRO")
                    precio_publico = _clean_decimal(_row_value(row, "PRECIO_PUBLICO", "PRECIO", "PVP"))
                    precio_mayorista = _clean_decimal(_row_value(row, "PRECIO_MAYORISTA", "MAYORISTA"))
                    precio_compra = _clean_decimal(_row_value(row, "COSTO_PROMEDIO", "COSTO", "PRECIO_COMPRA"))
                    stock_actual = _clean_int(_row_value(row, "STOCK_ACTUAL", "STOCK", "EXISTENCIA"))

                    id_externo = _row_value(row, "ID_PRODUCTO", "ID", "CODIGO_INTERNO") or str(count + 1)
                    codigo_interno = f"IMP-{id_externo}"

                    if not nombre:
                        errores += 1
                        count += 1
                        continue

                    cat = _get_or_create_categoria(nombre_categoria, categorias_cache)

                    producto_existente = None
                    if codigo_barras and len(codigo_barras) > 2:
                        producto_existente = Producto.query.filter_by(codigo_barras=codigo_barras).first()
                    if not producto_existente:
                        producto_existente = Producto.query.filter_by(codigo=codigo_interno).first()

                    if producto_existente:
                        if only_missing:
                            omitidos += 1
                            count += 1
                            continue
                        if not dry_run:
                            producto_existente.nombre = nombre
                            producto_existente.id_categoria = cat.id_categoria
                            producto_existente.precio_venta = precio_publico
                            producto_existente.precio_mayorista = precio_mayorista
                            producto_existente.precio_compra = precio_compra
                            producto_existente.stock_actual = stock_actual
                            if codigo_barras and len(codigo_barras) > 2:
                                producto_existente.codigo_barras = codigo_barras
                            producto_existente.fecha_modificacion = datetime.utcnow()
                            db.session.commit()
                        actualizados += 1
                    else:
                        nuevo_producto = Producto(
                            codigo=codigo_interno,
                            codigo_barras=codigo_barras or None,
                            nombre=nombre,
                            descripcion=f"Importado de categoría: {nombre_categoria or 'General'}",
                            id_categoria=cat.id_categoria,
                            id_proveedor_principal=prov.id_proveedor,
                            precio_venta=precio_publico,
                            precio_mayorista=precio_mayorista,
                            precio_compra=precio_compra,
                            stock_actual=stock_actual,
                            stock_minimo=5,
                            porcentaje_iva=10,
                            activo=True,
                            id_usuario_modificacion=user_id,
                        )
                        if not dry_run:
                            db.session.add(nuevo_producto)
                            db.session.commit()
                        nuevos += 1

                    count += 1

                except IntegrityError:
                    db.session.rollback()
                    duplicados += 1
                    count += 1
                except Exception:
                    db.session.rollback()
                    errores += 1
                    count += 1

                if count % 200 == 0:
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

        finally:
            try:
                file_obj.close()
            except Exception:
                pass

        print(f"CSV: {csv_path}")
        print(f"Nuevos: {nuevos}")
        print(f"Actualizados: {actualizados}")
        print(f"Omitidos (only-missing): {omitidos}")
        print(f"Duplicados/Error: {duplicados + errores}")
        print(f"Total procesados: {count}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", dest="csv_path", default=None)
    parser.add_argument("--csv-dir", dest="csv_dir", default=None)
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    p = _resolve_csv_path(args.csv_path, args.csv_dir, args.auto)
    if not p:
        print("No se encontró ningún CSV para importar.")
        return 0

    return importar_productos(p, dry_run=args.dry_run, limit=args.limit, only_missing=args.only_missing)


if __name__ == "__main__":
    raise SystemExit(main())
