import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text


def _default_sqlite_url() -> str:
    base_dir = Path(__file__).resolve().parent
    db_path = base_dir / "inventario.db"
    return f"sqlite:///{db_path.as_posix()}"


def _iter_batches(result, batch_size: int):
    batch = []
    for row in result.mappings():
        batch.append(dict(row))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.environ.get("SQLITE_URL") or _default_sqlite_url())
    parser.add_argument("--target", default=os.environ.get("DATABASE_URL") or "")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--clear-target", action="store_true", default=True)
    parser.add_argument("--no-clear-target", action="store_true", default=False)
    args = parser.parse_args()

    clear_target = args.clear_target and not args.no_clear_target

    if not args.target:
        raise SystemExit("Falta --target o DATABASE_URL")

    source_engine = create_engine(args.source, future=True)
    target_engine = create_engine(args.target, future=True, pool_pre_ping=True)

    from app import db
    import app.models

    db.metadata.create_all(target_engine)

    source_table_names = set(inspect(source_engine).get_table_names())
    target_table_names = set(inspect(target_engine).get_table_names())

    tables = [
        t
        for t in db.metadata.sorted_tables
        if t.name in source_table_names and t.name in target_table_names
    ]

    if not tables:
        raise SystemExit("No se encontraron tablas en común para migrar")

    dialect = target_engine.dialect.name

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        trans = target_conn.begin()
        try:
            if dialect in {"mysql", "mariadb"}:
                target_conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))

            if clear_target:
                for table in reversed(tables):
                    target_conn.execute(table.delete())

            for table in tables:
                result = source_conn.execute(table.select())
                inserted = 0
                for batch in _iter_batches(result, args.batch_size):
                    target_conn.execute(table.insert(), batch)
                    inserted += len(batch)
                print(f"{table.name}: {inserted} filas copiadas")

            if dialect in {"mysql", "mariadb"}:
                target_conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

            trans.commit()
        except Exception:
            trans.rollback()
            raise

    mismatches = []
    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in tables:
            src_count = source_conn.execute(select_count(table)).scalar_one()
            dst_count = target_conn.execute(select_count(table)).scalar_one()
            if src_count != dst_count:
                mismatches.append((table.name, src_count, dst_count))

    if mismatches:
        for name, src, dst in mismatches:
            print(f"✗ {name}: source={src} target={dst}")
        return 2

    print("✓ Migración completada y verificada por conteo de filas")
    return 0


def select_count(table):
    return select(func.count()).select_from(table)


if __name__ == "__main__":
    raise SystemExit(main())
