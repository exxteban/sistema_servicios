import argparse
import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _sign_payload(payload: dict, secret: str) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return _b64url(signature)


def _build_payload(args: argparse.Namespace) -> dict:
    now = datetime.now(timezone.utc)
    expires = datetime.strptime(args.expira, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return {
        "cliente_id": args.cliente_id,
        "cliente_nombre": args.cliente_nombre,
        "plan": args.plan,
        "machine_fingerprint": args.machine_fingerprint,
        "features": [feature.strip() for feature in args.features.split(",") if feature.strip()],
        "iat": now.isoformat(),
        "exp": expires.isoformat(),
    }


def _encode_license(payload: dict, signature: str) -> str:
    envelope = {
        "payload": payload,
        "signature": signature,
    }
    raw = json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _b64url(raw)


def _resolve_secret(secret_value: str) -> str:
    if secret_value:
        return secret_value
    env_secret = os.environ.get("LICENSE_SIGNING_SECRET", "").strip()
    if env_secret:
        return env_secret
    raise RuntimeError("Debes proveer --secret o variable de entorno LICENSE_SIGNING_SECRET.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente-id", required=True)
    parser.add_argument("--cliente-nombre", required=True)
    parser.add_argument("--plan", default="local-premium")
    parser.add_argument("--machine-fingerprint", required=True)
    parser.add_argument("--expira", required=True)
    parser.add_argument("--features", default="core")
    parser.add_argument("--secret", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    secret = _resolve_secret(args.secret)
    payload = _build_payload(args)
    signature = _sign_payload(payload, secret)
    license_data = _encode_license(payload, signature)

    output_path = Path(args.output) if args.output else Path.cwd() / "license.dat"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(license_data, encoding="utf-8")
    print(str(output_path.resolve()))


if __name__ == "__main__":
    main()
