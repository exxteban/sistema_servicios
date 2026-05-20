import argparse
import os
from pathlib import Path

from csv_bundle import unbundle_csv


def _resolve_path(value: str) -> Path:
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def _default_bundle() -> Path | None:
    base = Path(__file__).resolve().parent
    search_dir = base / "Base de datos"
    if not search_dir.exists():
        return None
    bundles = sorted(search_dir.glob("*.csv.bundle"), key=lambda p: p.stat().st_mtime, reverse=True)
    return bundles[0] if bundles else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", default=None)
    parser.add_argument("--out-csv", default="Base de datos/_productos_bundle_extraido.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--update-existing", action="store_true")
    args = parser.parse_args()

    bundle_path = _resolve_path(args.bundle) if args.bundle else (_default_bundle() or None)
    if not bundle_path:
        print("No se encontró ningún *.csv.bundle. Usá --bundle \"Base de datos/archivo.csv.bundle\"")
        return 2
    if not bundle_path.exists():
        print(f"No existe el bundle: {bundle_path}")
        return 2

    out_csv_path = _resolve_path(args.out_csv)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    unbundle_csv(bundle_path, out_csv_path)

    from deploy.import_legacy_products_csv import importar_productos

    config_name = (os.environ.get("APP_CONFIG") or "default").strip() or "default"
    os.environ["APP_CONFIG"] = config_name

    return importar_productos(
        out_csv_path,
        dry_run=bool(args.dry_run),
        limit=args.limit,
        only_missing=not bool(args.update_existing),
    )


if __name__ == "__main__":
    raise SystemExit(main())
