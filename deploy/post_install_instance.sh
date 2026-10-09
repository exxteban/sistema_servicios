#!/usr/bin/env bash
set -euo pipefail

app_dir="${APP_DIR:?}"
import_legacy_csv="${IMPORT_LEGACY_CSV:-1}"
env_file_path="${ENV_FILE_PATH:?}"
venv_path="${VENV_PATH:?}"
bind_host="${BIND_HOST:-127.0.0.1}"
app_port="${APP_PORT:?}"
domain="${DOMAIN:-}"
service_name="${SERVICE_NAME:?}"
caddyfile_path="${CADDYFILE_PATH:-/etc/caddy/Caddyfile}"
caddy_sites_dir="${CADDY_SITES_DIR:-/etc/caddy/sites.d}"
setup_caddy="${SETUP_CADDY:-1}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if [ "$import_legacy_csv" = "1" ]; then
  if ls "$app_dir/deploy/"*.csv* >/dev/null 2>&1 || ls "$app_dir/Base de datos/"*.csv >/dev/null 2>&1; then
    ENV_FILE_PATH="$env_file_path" VENV_PATH="$venv_path" /usr/bin/env bash "$app_dir/deploy/import_legacy_data.sh" || true
  fi
fi

if have_cmd ufw; then
  if [ "$bind_host" = "0.0.0.0" ] || [ "$bind_host" = "::" ]; then
    as_root ufw allow "${app_port}/tcp" >/dev/null 2>&1 || true
  fi
  if [ -n "$domain" ]; then
    as_root ufw allow "80/tcp" >/dev/null 2>&1 || true
    as_root ufw allow "443/tcp" >/dev/null 2>&1 || true
  fi
  as_root ufw reload >/dev/null 2>&1 || true
fi

if have_cmd fail2ban-client; then
  filter_name="${service_name}-auth"
  jail_name="$service_name"
  filter_src="$app_dir/deploy/fail2ban/filter.d/sistema-cliente2-auth.conf"
  jail_tpl="$app_dir/deploy/fail2ban/jail.d/sistema-cliente2.conf.template"
  as_root install -D -m 0644 "$filter_src" "/etc/fail2ban/filter.d/${filter_name}.conf"
  as_root env \
    JAIL_TEMPLATE="$jail_tpl" \
    JAIL_NAME="$jail_name" \
    FILTER_NAME="$filter_name" \
    APP_LOG_PATH="$app_dir/logs/sistema.log" \
    APP_PORT="$app_port" \
    python3 - <<'PY'
from pathlib import Path
import os

tpl = Path(os.environ["JAIL_TEMPLATE"]).read_text(encoding="utf-8")
out = (
    tpl.replace("__JAIL_NAME__", os.environ["JAIL_NAME"])
    .replace("__FILTER_NAME__", os.environ["FILTER_NAME"])
    .replace("__APP_LOG_PATH__", os.environ["APP_LOG_PATH"])
    .replace("__APP_PORT__", os.environ["APP_PORT"])
)
Path(f"/etc/fail2ban/jail.d/{os.environ['JAIL_NAME']}.conf").write_text(out, encoding="utf-8")
PY
  as_root systemctl enable --now fail2ban >/dev/null 2>&1 || true
  as_root systemctl restart fail2ban >/dev/null 2>&1 || true
fi

if [ -n "$domain" ]; then
  DOMAIN="$domain" \
  APP_PORT="$app_port" \
  SERVICE_NAME="$service_name" \
  CADDYFILE_PATH="$caddyfile_path" \
  CADDY_SITES_DIR="$caddy_sites_dir" \
  SETUP_CADDY="$setup_caddy" \
  /usr/bin/env bash "$app_dir/deploy/setup_caddy.sh"
fi
