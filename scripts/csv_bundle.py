import base64
import gzip
from pathlib import Path


MAGIC = "CSV_BUNDLE_V1"


def bundle_csv(csv_path: Path, bundle_path: Path) -> None:
    raw = Path(csv_path).read_bytes()
    compressed = gzip.compress(raw)
    encoded = base64.b64encode(compressed).decode("ascii")
    payload = f"{MAGIC}\n{encoded}\n"
    Path(bundle_path).write_text(payload, encoding="utf-8", newline="\n")


def unbundle_csv(bundle_path: Path, out_csv_path: Path) -> None:
    text = Path(bundle_path).read_text(encoding="utf-8")
    parts = text.splitlines()
    if not parts or parts[0].strip() != MAGIC:
        raise ValueError(f"Bundle inválido: falta encabezado {MAGIC}")
    encoded = "".join(p.strip() for p in parts[1:] if p.strip())
    compressed = base64.b64decode(encoded.encode("ascii"))
    raw = gzip.decompress(compressed)
    Path(out_csv_path).write_bytes(raw)

