#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir="$(cd "$script_dir/.." && pwd)"
local_env="$script_dir/demoservicios.env"

if [ -f "$local_env" ]; then
  set -a
  . "$local_env"
  set +a
fi

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

detect_service_user() {
  if [ -n "${SERVICE_USER:-}" ]; then
    printf '%s\n' "$SERVICE_USER"
    return
  fi
  if id administrator >/dev/null 2>&1; then
    printf '%s\n' "administrator"
    return
  fi
  if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    printf '%s\n' "$SUDO_USER"
    return
  fi
  printf '%s\n' "$(id -un)"
}

export DOMAIN="${DOMAIN:-demoservicios.pysystems.online}"
export EXPECTED_PUBLIC_IP="${EXPECTED_PUBLIC_IP:-38.247.128.125}"
export SERVICE_NAME="${SERVICE_NAME:-sistema-demoservicios}"
export APP_PORT="${APP_PORT:-3117}"
export ENV_FILE_PATH="${ENV_FILE_PATH:-/etc/sistema_demoservicios.env}"
export DB_NAME="${DB_NAME:-demoservicios}"
export DB_USER="${DB_USER:-demoservicios_user}"
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-3306}"
export APP_CONFIG="${APP_CONFIG:-production}"
export APP_SERVER="${APP_SERVER:-waitress}"
export HOST="${HOST:-127.0.0.1}"
export SETUP_CADDY="${SETUP_CADDY:-1}"
export CADDYFILE_PATH="${CADDYFILE_PATH:-/etc/caddy/Caddyfile}"
export CADDY_SITES_DIR="${CADDY_SITES_DIR:-/etc/caddy/sites.d}"
export SERVER_TIMEZONE="${SERVER_TIMEZONE:-America/Asuncion}"
export SERVICE_USER="$(detect_service_user)"
export SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
export BACKUP_DIR="${BACKUP_DIR:-/home/$SERVICE_USER/backups/demoservicios}"
export IMPORT_LEGACY_CSV="${IMPORT_LEGACY_CSV:-0}"
export RUN_TIENDA_BUILD="${RUN_TIENDA_BUILD:-1}"
export RUN_TIENDA_MIGRATIONS="${RUN_TIENDA_MIGRATIONS:-1}"
export RUN_APP_BOOTSTRAP_MIGRATIONS="${RUN_APP_BOOTSTRAP_MIGRATIONS:-1}"
export RUN_TIENDA_UPLOAD_PERMISSIONS="${RUN_TIENDA_UPLOAD_PERMISSIONS:-1}"

if [ -z "${DB_ROOT_PASSWORD:-}" ]; then
  cat >&2 <<'MSG'
Falta DB_ROOT_PASSWORD.

Ejemplo:
  DB_ROOT_PASSWORD='clave-root-mariadb' bash deploy/install_demoservicios.sh

Tambien puedes crear deploy/demoservicios.env desde deploy/demoservicios.env.example.
MSG
  exit 1
fi

if [ "${CHECK_DNS:-1}" = "1" ] && have_cmd getent; then
  resolved_ips="$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')"
  if [ -z "$resolved_ips" ]; then
    echo "Aviso: $DOMAIN todavia no resuelve por DNS."
    echo "En Namecheap configura A demoservicios -> $EXPECTED_PUBLIC_IP."
  elif ! printf ' %s ' "$resolved_ips" | grep -q " $EXPECTED_PUBLIC_IP "; then
    echo "Aviso: $DOMAIN resuelve a: $resolved_ips"
    echo "IP esperada: $EXPECTED_PUBLIC_IP"
  fi
fi

if have_cmd ufw; then
  ssh_port="${SSH_PORT:-22}"
  as_root ufw allow "${ssh_port}/tcp" >/dev/null 2>&1 || true
  as_root ufw allow 80/tcp >/dev/null 2>&1 || true
  as_root ufw allow 443/tcp >/dev/null 2>&1 || true
fi

echo "Instalando $SERVICE_NAME para https://$DOMAIN -> 127.0.0.1:$APP_PORT"
echo "Usuario systemd: $SERVICE_USER"
echo "ENV: $ENV_FILE_PATH"

"$script_dir/install.sh"

ENV_FILE_PATH="$ENV_FILE_PATH" \
SERVICE_NAME="$SERVICE_NAME" \
VENV_PATH="${VENV_PATH:-$app_dir/.venv}" \
SKIP_GIT="${SKIP_GIT:-1}" \
RUN_TIENDA_BUILD="$RUN_TIENDA_BUILD" \
RUN_TIENDA_MIGRATIONS="$RUN_TIENDA_MIGRATIONS" \
RUN_APP_BOOTSTRAP_MIGRATIONS="$RUN_APP_BOOTSTRAP_MIGRATIONS" \
RUN_TIENDA_UPLOAD_PERMISSIONS="$RUN_TIENDA_UPLOAD_PERMISSIONS" \
"$script_dir/update_min.sh"

if have_cmd systemctl; then
  as_root systemctl status "$SERVICE_NAME" --no-pager || true
  as_root systemctl status caddy --no-pager || true
fi

echo "Deploy demo listo: https://$DOMAIN"
echo "Revisar logs app: journalctl -u $SERVICE_NAME -f"
echo "Revisar Caddy: journalctl -u caddy -f"
