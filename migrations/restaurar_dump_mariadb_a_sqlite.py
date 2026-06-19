import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable


def _sqlite_url_from_path(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _iter_insert_statements(dump_path: Path) -> Iterable[tuple[str, str]]:
    insert_re = re.compile(r"^\s*INSERT\s+INTO\s+`?([A-Za-z0-9_]+)`?\s+", re.IGNORECASE)

    current_table: str | None = None
    buffer: list[str] = []

    with dump_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if current_table is None:
                m = insert_re.match(line)
                if not m:
                    continue
                current_table = m.group(1)
                buffer = [line]
                if line.rstrip().endswith(";"):
                    stmt = "".join(buffer)
                    yield current_table, stmt
                    current_table = None
                    buffer = []
                continue

            buffer.append(line)
            if line.rstrip().endswith(";"):
                stmt = "".join(buffer)
                yield current_table, stmt
                current_table = None
                buffer = []


def _backup_file(path: Path) -> Path:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.stem}_backup_{now}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        choices=("restore", "list-users", "reset-password"),
        default="restore",
    )
    parser.add_argument(
        "--dump",
        default=str(Path(__file__).resolve().parent / "bd_silvio_2026-02-17_03-17-15.sql"),
    )
    parser.add_argument(
        "--sqlite",
        default=str(Path(__file__).resolve().parent / "inventario.db"),
    )
    parser.add_argument("--username", default="")
    parser.add_argument("--new-password", default="admin123")
    parser.add_argument("--no-backup", action="store_true", default=False)
    parser.add_argument("--commit-every", type=int, default=200)
    args = parser.parse_args()

    dump_path = Path(args.dump)
    sqlite_path = Path(args.sqlite)

    if not dump_path.exists():
        if args.action == "restore":
            raise SystemExit(f"No existe el dump: {dump_path}")

    if sqlite_path.exists() and not args.no_backup:
        backup_path = _backup_file(sqlite_path)
        print(f"Backup SQLite: {backup_path}")

    os.environ["DATABASE_URL"] = _sqlite_url_from_path(sqlite_path)

    from app import create_app, db
    import app.models  # noqa: F401

    app = create_app("development")

    with app.app_context():
        if args.action == "list-users":
            from app.models.usuario import Usuario

            usuarios = (
                Usuario.query.order_by(Usuario.id_usuario.asc()).all()
            )
            print(f"SQLite: {sqlite_path}")
            print(f"Total usuarios: {len(usuarios)}")
            for u in usuarios:
                rol = getattr(getattr(u, "rol", None), "nombre", None)
                print(f"- id={u.id_usuario} username={u.username} rol={rol} activo={bool(u.activo)}")
            return 0

        if args.action == "reset-password":
            username = (args.username or "").strip()
            if not username:
                raise SystemExit("Falta --username")
            new_password = args.new_password or ""
            if len(new_password) < 4:
                raise SystemExit("--new-password debe tener al menos 4 caracteres")

            from app.models.usuario import Usuario

            usuario = Usuario.query.filter_by(username=username).first()
            if not usuario:
                raise SystemExit(f"No existe el usuario: {username}")

            usuario.set_password(new_password)
            db.session.commit()
            print(f"Contraseña actualizada para: {username}")
            print(f"Login: {username} / {new_password}")
            return 0

        if args.action != "restore":
            raise SystemExit(f"Acción inválida: {args.action}")

        raw = db.engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute("PRAGMA foreign_keys=OFF")

            existing_tables = {
                row[0]
                for row in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }

            for table in reversed(db.metadata.sorted_tables):
                if table.name in existing_tables:
                    cur.execute(f"DELETE FROM {table.name}")
            raw.commit()

            inserted_tables: dict[str, int] = {}
            skipped_tables: set[str] = set()
            executed = 0

            for table_name, stmt in _iter_insert_statements(dump_path):
                if table_name not in existing_tables:
                    skipped_tables.add(table_name)
                    continue
                stmt_sqlite = stmt.replace("\\'", "''")
                try:
                    cur.execute(stmt_sqlite)
                except Exception:
                    try:
                        cur.executescript(stmt_sqlite)
                    except Exception as e:
                        raise RuntimeError(f"Fallo insert en tabla {table_name}") from e

                inserted_tables[table_name] = inserted_tables.get(table_name, 0) + 1
                executed += 1
                if args.commit_every > 0 and executed % args.commit_every == 0:
                    raw.commit()

            raw.commit()
            cur.execute("PRAGMA foreign_keys=ON")

            def _count(name: str) -> int | None:
                if name not in existing_tables:
                    return None
                return int(cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])

            resumen = {
                "usuarios": _count("usuarios"),
                "productos": _count("productos"),
                "ventas": _count("ventas"),
                "reparaciones": _count("reparaciones"),
            }

            print("✓ Restauración terminada")
            print(f"SQLite: {sqlite_path}")
            print(f"Statements INSERT ejecutados: {executed}")
            print("Conteos:")
            for k, v in resumen.items():
                if v is not None:
                    print(f"  - {k}: {v}")

            if skipped_tables:
                skipped = ", ".join(sorted(skipped_tables))
                print(f"Tablas omitidas (no existen en SQLite actual): {skipped}")
        finally:
            raw.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
