import argparse
from pathlib import Path

from csv_bundle import bundle_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser()
    if not csv_path.is_absolute():
        csv_path = (Path.cwd() / csv_path).resolve()
    if not csv_path.exists():
        print(f"No existe el archivo: {csv_path}")
        return 2

    if args.out:
        out_path = Path(args.out)
    else:
        if csv_path.name.lower().endswith(".csv"):
            out_path = csv_path.with_suffix(csv_path.suffix + ".bundle")
        else:
            out_path = Path(str(csv_path) + ".csv.bundle")
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()

    bundle_csv(csv_path, out_path)
    print(f"OK: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
