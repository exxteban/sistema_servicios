#!/usr/bin/env bash
#2954ea8b65cc320cd29a9b8e064720ec
set -euo pipefail

app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

env_file_path="${ENV_FILE_PATH:-/etc/sistema_ecocirculo.env}"

if [ -f "$env_file_path" ]; then
  set -a
  . "$env_file_path"
  set +a
fi

app_port="${APP_PORT:-3112}"
service_name="${SERVICE_NAME:-sistema-ecocirculo}"

domain="${DOMAIN:-}"
setup_caddy="${SETUP_CADDY:-1}"
caddyfile_path="${CADDYFILE_PATH:-/etc/caddy/Caddyfile}"
caddy_sites_dir="${CADDY_SITES_DIR:-/etc/caddy/sites.d}"

app_config="${APP_CONFIG:-production}"
app_server="${APP_SERVER:-waitress}"

bind_host="${HOST:-}"
if [ -z "$bind_host" ]; then
  if [ -n "$domain" ]; then
    bind_host="127.0.0.1"
  else
    bind_host="0.0.0.0"
  fi
fi

db_name="${DB_NAME:-bd_silvio}"
db_user="${DB_USER:-silvio_user}"
db_password="${DB_PASSWORD:-}"
db_host="${DB_HOST:-localhost}"
db_port="${DB_PORT:-3306}"
db_root_password="${DB_ROOT_PASSWORD:-}"
db_password_generated="0"

if [ -n "${DATABASE_URL:-}" ]; then
  db_name_env_set=0
  db_user_env_set=0
  db_password_env_set=0
  db_host_env_set=0
  db_port_env_set=0

  if [ "${DB_NAME+x}" = "x" ]; then db_name_env_set=1; fi
  if [ "${DB_USER+x}" = "x" ]; then db_user_env_set=1; fi
  if [ "${DB_PASSWORD+x}" = "x" ]; then db_password_env_set=1; fi
  if [ "${DB_HOST+x}" = "x" ]; then db_host_env_set=1; fi
  if [ "${DB_PORT+x}" = "x" ]; then db_port_env_set=1; fi

  parsed="$(
python3 - <<'PY'
import os
import urllib.parse
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "") or ""
try:
    p = urlparse(url)
except Exception:
    p = None

if not p:
    raise SystemExit(0)

user = urllib.parse.unquote(p.username or "")
password = urllib.parse.unquote(p.password or "")
host = p.hostname or ""
port = str(p.port or "")
db = (p.path or "").lstrip("/")

print(f"user={user}")
print(f"password={password}")
print(f"host={host}")
print(f"port={port}")
print(f"db={db}")
PY
)"

  parsed_user=""
  parsed_password=""
  parsed_host=""
  parsed_port=""
  parsed_db=""
  while IFS='=' read -r k v; do
    case "$k" in
      user) parsed_user="$v" ;;
      password) parsed_password="$v" ;;
      host) parsed_host="$v" ;;
      port) parsed_port="$v" ;;
      db) parsed_db="$v" ;;
    esac
  done <<< "$parsed"

  if [ "$db_user_env_set" = "0" ] && [ -n "$parsed_user" ]; then
    db_user="$parsed_user"
  fi
  if [ "$db_password_env_set" = "0" ] && [ -n "$parsed_password" ]; then
    db_password="$parsed_password"
  fi
  if [ "$db_host_env_set" = "0" ] && [ -n "$parsed_host" ]; then
    db_host="$parsed_host"
  fi
  if [ "$db_port_env_set" = "0" ] && [ -n "$parsed_port" ]; then
    db_port="$parsed_port"
  fi
  if [ "$db_name_env_set" = "0" ] && [ -n "$parsed_db" ]; then
    db_name="$parsed_db"
  fi
fi

secret_key="${SECRET_KEY:-}"

service_user="${SERVICE_USER:-${SUDO_USER:-$USER}}"
service_group="${SERVICE_GROUP:-$service_user}"

backup_dir="${BACKUP_DIR:-/home/administrador/backups}"
backup_on_calendar="${BACKUP_ON_CALENDAR:-*-*-* 03:15:00}"
retention_days="${RETENTION_DAYS:-14}"
compress="${COMPRESS:-1}"

import_legacy_csv="${IMPORT_LEGACY_CSV:-1}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

shell_quote() {
  python3 - "$1" <<'PY'
import shlex
import sys

print(shlex.quote(sys.argv[1]))
PY
}

append_env_line() {
  local file_path="$1"
  local key="$2"
  local value="${3-}"
  printf '%s=%s\n' "$key" "$(shell_quote "$value")" >> "$file_path"
}

if [ -z "$db_password" ]; then
  if have_cmd openssl; then
    db_password="$(openssl rand -hex 16)"
  else
    db_password="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)"
  fi
  db_password_generated="1"
fi

if [ -z "$secret_key" ]; then
  if have_cmd openssl; then
    secret_key="$(openssl rand -hex 32)"
  else
    secret_key="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  fi
fi

if [ -f /etc/os-release ]; then
  . /etc/os-release
  os_id="${ID:-}"
else
  os_id=""
fi

mysql_service=""
server_timezone="${SERVER_TIMEZONE:-America/Asuncion}"

if have_cmd apt-get; then
  as_root apt-get update -y
  as_root apt-get install -y python3 python3-venv python3-pip python3-dev build-essential pkg-config libcairo2 libcairo2-dev libffi-dev cmake meson ninja-build mariadb-server mariadb-client fail2ban curl ca-certificates gzip rclone
  mysql_service="mariadb"
elif have_cmd dnf; then
  as_root dnf install -y python3 python3-pip python3-devel gcc gcc-c++ pkgconf-pkg-config cairo cairo-devel libffi-devel cmake meson ninja-build mariadb-server curl ca-certificates gzip
  as_root dnf install -y fail2ban >/dev/null 2>&1 || true
  mysql_service="mariadb"
elif have_cmd yum; then
  as_root yum install -y python3 python3-pip python3-devel gcc gcc-c++ pkgconfig cairo cairo-devel libffi-devel cmake meson ninja-build mariadb-server curl ca-certificates gzip
  as_root yum install -y fail2ban >/dev/null 2>&1 || true
  mysql_service="mariadb"
else
  echo "No se detectó un gestor de paquetes compatible (apt/dnf/yum)."
  exit 1
fi

if ! have_cmd pkg-config || ! pkg-config --exists cairo; then
  echo "Dependencia faltante: cairo (pkg-config)."
  echo "Instala cairo dev y vuelve a ejecutar install.sh."
  exit 1
fi

if [ -f "/usr/share/zoneinfo/$server_timezone" ]; then
  if have_cmd timedatectl; then
    as_root timedatectl set-timezone "$server_timezone" >/dev/null 2>&1 || true
  fi
  as_root ln -snf "/usr/share/zoneinfo/$server_timezone" /etc/localtime 2>/dev/null || true
  as_root bash -lc "printf '%s\n' '$server_timezone' > /etc/timezone" 2>/dev/null || true
fi

venv_path="${VENV_PATH:-$app_dir/.venv}"
python_bin="$venv_path/bin/python"

if [ ! -d "$venv_path" ]; then
  python3 -m venv "$venv_path"
fi

"$python_bin" -m pip install --upgrade pip
"$venv_path/bin/pip" install -r "$app_dir/requirements.txt"

if [ -n "$mysql_service" ] && have_cmd systemctl; then
  as_root systemctl enable --now "$mysql_service"
fi

mysql_cmd=""
if have_cmd mysql; then
  mysql_cmd="mysql"
elif have_cmd mariadb; then
  mysql_cmd="mariadb"
else
  echo "No se encontró el cliente mysql/mariadb."
  exit 1
fi

mysql_root_auth=""

mysql_root_with_password() {
  as_root env MYSQL_PWD="$db_root_password" "$mysql_cmd" --user=root "$@"
}

mysql_root_with_socket() {
  as_root "$mysql_cmd" --user=root "$@"
}

if [ -n "$db_root_password" ] && mysql_root_with_password -e "SELECT 1" >/dev/null 2>&1; then
  mysql_root_auth="password"
elif mysql_root_with_socket -e "SELECT 1" >/dev/null 2>&1; then
  mysql_root_auth="socket"
else
  echo "No se pudo conectar a MariaDB/MySQL como root."
  echo "Define DB_ROOT_PASSWORD si root ya tiene clave, o ejecuta como root/sudo para usar auth_socket."
  exit 1
fi

mysql_root() {
  if [ "$mysql_root_auth" = "socket" ]; then
    mysql_root_with_socket "$@"
  else
    mysql_root_with_password "$@"
  fi
}

if [[ ! "$db_name" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "DB_NAME inválido: $db_name"
  exit 1
fi
if [[ ! "$db_user" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "DB_USER inválido: $db_user"
  exit 1
fi
if [[ "$db_password" == *"'"* ]] || [[ "$db_host" == *"'"* ]]; then
  echo "DB_PASSWORD/DB_HOST no puede contener comillas simples."
  exit 1
fi

mysql_root -e "CREATE DATABASE IF NOT EXISTS \`$db_name\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

user_hosts=("localhost")
if [ "$db_host" = "127.0.0.1" ]; then
  user_hosts+=("127.0.0.1")
elif [ "$db_host" = "::1" ]; then
  user_hosts+=("::1")
elif [ "$db_host" != "localhost" ]; then
  user_hosts+=("$db_host")
fi

for h in "${user_hosts[@]}"; do
  mysql_root -e "CREATE USER IF NOT EXISTS '$db_user'@'$h' IDENTIFIED BY '$db_password';"
  mysql_root -e "ALTER USER '$db_user'@'$h' IDENTIFIED BY '$db_password';"
  mysql_root -e "GRANT ALL PRIVILEGES ON \`$db_name\`.* TO '$db_user'@'$h';"
done
mysql_root -e "FLUSH PRIVILEGES;"

export DB_USER="$db_user"
export DB_PASSWORD="$db_password"
export DB_HOST="$db_host"
export DB_PORT="$db_port"
export DB_NAME="$db_name"

database_url="$(
python3 - <<PY
import os
import urllib.parse

user = os.environ.get("DB_USER") or ""
password = os.environ.get("DB_PASSWORD") or ""
host = os.environ.get("DB_HOST") or "127.0.0.1"
port = os.environ.get("DB_PORT") or "3306"
db = os.environ.get("DB_NAME") or ""

user_q = urllib.parse.quote(user, safe="")
pass_q = urllib.parse.quote(password, safe="")
db_q = urllib.parse.quote(db, safe="")

print(f"mysql+pymysql://{user_q}:{pass_q}@{host}:{port}/{db_q}?charset=utf8mb4")
PY
)"

cookie_secure="${COOKIE_SECURE:-}"
if [ -z "$cookie_secure" ]; then
  if [ -n "$domain" ] || [ "$setup_caddy" = "1" ]; then
    cookie_secure="1"
  else
    cookie_secure="0"
  fi
fi
cookie_samesite="${COOKIE_SAMESITE:-Lax}"
use_proxy_fix="${USE_PROXY_FIX:-}"
if [ -z "$use_proxy_fix" ]; then
  if [ -n "$domain" ] || [ "$setup_caddy" = "1" ]; then
    use_proxy_fix="1"
  else
    use_proxy_fix="0"
  fi
fi
force_production_config="${FORCE_PRODUCTION_CONFIG:-}"
if [ -z "$force_production_config" ]; then
  if [ "$app_config" = "production" ]; then
    force_production_config="1"
  else
    force_production_config="0"
  fi
fi

bootstrap_admin_password="${APP_BOOTSTRAP_ADMIN_PASSWORD:-}"
bootstrap_root_username="${APP_BOOTSTRAP_ROOT_USERNAME:-root}"
bootstrap_root_password="${APP_BOOTSTRAP_ROOT_PASSWORD:-}"
bootstrap_admin_password_generated="0"
bootstrap_root_password_generated="0"

if [ "$app_config" = "production" ]; then
  if [ -z "$bootstrap_admin_password" ]; then
    if have_cmd openssl; then
      bootstrap_admin_password="$(openssl rand -hex 16)"
    else
      bootstrap_admin_password="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)"
    fi
    bootstrap_admin_password_generated="1"
  fi
  if [ "$bootstrap_admin_password" = "admin123" ] || [ "${#bootstrap_admin_password}" -lt 10 ]; then
    echo "APP_BOOTSTRAP_ADMIN_PASSWORD inválido (>=10 y distinto de admin123)."
    exit 1
  fi

  bootstrap_root_username="$(echo -n "$bootstrap_root_username" | xargs || true)"
  if [ -n "$bootstrap_root_username" ]; then
    if [ -z "$bootstrap_root_password" ]; then
      if have_cmd openssl; then
        bootstrap_root_password="$(openssl rand -hex 16)"
      else
        bootstrap_root_password="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)"
      fi
      bootstrap_root_password_generated="1"
    fi
    if [ "$bootstrap_root_password" = "root1409" ] || [ "${#bootstrap_root_password}" -lt 10 ]; then
      echo "APP_BOOTSTRAP_ROOT_PASSWORD inválido (>=10 y distinto de root1409)."
      exit 1
    fi
  else
    bootstrap_root_password=""
  fi
fi

extra_env_tmp="$(mktemp)"
env_tmp="$(mktemp)"
cleanup_tmp() { rm -f "$extra_env_tmp" "$env_tmp"; }
trap cleanup_tmp EXIT

if [ -f "$env_file_path" ]; then
  as_root cat "$env_file_path" | grep -vE '^(APP_CONFIG|FORCE_PRODUCTION_CONFIG|SERVER|HOST|PORT|SECRET_KEY|DATABASE_URL|USE_PROXY_FIX|APP_BOOTSTRAP_ADMIN_PASSWORD|APP_BOOTSTRAP_ROOT_USERNAME|APP_BOOTSTRAP_ROOT_PASSWORD|SESSION_COOKIE_SECURE|REMEMBER_COOKIE_SECURE|SESSION_COOKIE_SAMESITE|REMEMBER_COOKIE_SAMESITE|RCLONE_DEST_DIR|RCLONE_OP|RCLONE_FAIL_OPEN|WHATSAPP_ENABLED|WHATSAPP_PHONE_NUMBER_ID|WHATSAPP_PHONE_ID|WHATSAPP_ACCESS_TOKEN|WHATSAPP_TOKEN|WHATSAPP_WEBHOOK_VERIFY_TOKEN|WHATSAPP_VERIFY_TOKEN|WHATSAPP_DRY_RUN|WHATSAPP_RATE_LIMIT_PER_PHONE|WHATSAPP_RATE_LIMIT_GLOBAL|WHATSAPP_SESION_HORAS|WHATSAPP_CODIGO_EXPIRACION_DIAS|WHATSAPP_MAX_INTENTOS_CODIGO|WHATSAPP_ASESOR_TIMEOUT_SEGUNDOS|WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS|WHATSAPP_ASESOR_MAX_CONVERSACIONES|WHATSAPP_TIMEOUT_SCHEDULER|WHATSAPP_TIMEOUT_INTERVAL_SECONDS|WHATSAPP_NOTIFICAR_LISTO|WHATSAPP_NOTIFICAR_ESPERA_CLIENTE|WHATSAPP_NOTIFICAR_NO_SE_PUDO|CRM_ENABLED|CRM_BANDEJA_JEFE_MIN_NIVEL|AI_ENABLED|AI_PROVIDER|AI_MODEL|AI_REASONING_EFFORT|AI_MAX_TOKENS|AI_TEMPERATURE|AI_API_KEY|AI_BASE_URL|DEEPSEEK_API_KEY|DEEPSEEK_BASE_URL|LOG_LEVEL|LOG_REQUEST_ACCESS|LOG_REQUEST_VERBOSE|LOG_REQUEST_BODY|LOG_WHATSAPP_WEBHOOK|LOG_DB_COMMITS)=' > "$extra_env_tmp" || true
fi

append_env_line "$env_tmp" "APP_CONFIG" "$app_config"
append_env_line "$env_tmp" "FORCE_PRODUCTION_CONFIG" "$force_production_config"
append_env_line "$env_tmp" "SERVER" "$app_server"
append_env_line "$env_tmp" "HOST" "$bind_host"
append_env_line "$env_tmp" "PORT" "$app_port"
append_env_line "$env_tmp" "SECRET_KEY" "$secret_key"
append_env_line "$env_tmp" "DATABASE_URL" "$database_url"
append_env_line "$env_tmp" "USE_PROXY_FIX" "$use_proxy_fix"
append_env_line "$env_tmp" "APP_BOOTSTRAP_ADMIN_PASSWORD" "$bootstrap_admin_password"
append_env_line "$env_tmp" "APP_BOOTSTRAP_ROOT_USERNAME" "$bootstrap_root_username"
append_env_line "$env_tmp" "APP_BOOTSTRAP_ROOT_PASSWORD" "$bootstrap_root_password"
append_env_line "$env_tmp" "SESSION_COOKIE_SECURE" "$cookie_secure"
append_env_line "$env_tmp" "REMEMBER_COOKIE_SECURE" "$cookie_secure"
append_env_line "$env_tmp" "SESSION_COOKIE_SAMESITE" "$cookie_samesite"
append_env_line "$env_tmp" "REMEMBER_COOKIE_SAMESITE" "$cookie_samesite"
append_env_line "$env_tmp" "WHATSAPP_ENABLED" "${WHATSAPP_ENABLED:-0}"
append_env_line "$env_tmp" "WHATSAPP_PHONE_NUMBER_ID" "${WHATSAPP_PHONE_NUMBER_ID:-${WHATSAPP_PHONE_ID:-}}"
append_env_line "$env_tmp" "WHATSAPP_ACCESS_TOKEN" "${WHATSAPP_ACCESS_TOKEN:-${WHATSAPP_TOKEN:-}}"
append_env_line "$env_tmp" "WHATSAPP_WEBHOOK_VERIFY_TOKEN" "${WHATSAPP_WEBHOOK_VERIFY_TOKEN:-${WHATSAPP_VERIFY_TOKEN:-}}"
append_env_line "$env_tmp" "WHATSAPP_DRY_RUN" "${WHATSAPP_DRY_RUN:-0}"
append_env_line "$env_tmp" "WHATSAPP_RATE_LIMIT_PER_PHONE" "${WHATSAPP_RATE_LIMIT_PER_PHONE:-20}"
append_env_line "$env_tmp" "WHATSAPP_RATE_LIMIT_GLOBAL" "${WHATSAPP_RATE_LIMIT_GLOBAL:-500}"
append_env_line "$env_tmp" "WHATSAPP_SESION_HORAS" "${WHATSAPP_SESION_HORAS:-24}"
append_env_line "$env_tmp" "WHATSAPP_CODIGO_EXPIRACION_DIAS" "${WHATSAPP_CODIGO_EXPIRACION_DIAS:-30}"
append_env_line "$env_tmp" "WHATSAPP_MAX_INTENTOS_CODIGO" "${WHATSAPP_MAX_INTENTOS_CODIGO:-3}"
append_env_line "$env_tmp" "WHATSAPP_ASESOR_TIMEOUT_SEGUNDOS" "${WHATSAPP_ASESOR_TIMEOUT_SEGUNDOS:-180}"
append_env_line "$env_tmp" "WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS" "${WHATSAPP_ASESOR_HEARTBEAT_SEGUNDOS:-30}"
append_env_line "$env_tmp" "WHATSAPP_ASESOR_MAX_CONVERSACIONES" "${WHATSAPP_ASESOR_MAX_CONVERSACIONES:-5}"
append_env_line "$env_tmp" "WHATSAPP_TIMEOUT_SCHEDULER" "${WHATSAPP_TIMEOUT_SCHEDULER:-1}"
append_env_line "$env_tmp" "WHATSAPP_TIMEOUT_INTERVAL_SECONDS" "${WHATSAPP_TIMEOUT_INTERVAL_SECONDS:-30}"
append_env_line "$env_tmp" "WHATSAPP_NOTIFICAR_LISTO" "${WHATSAPP_NOTIFICAR_LISTO:-1}"
append_env_line "$env_tmp" "WHATSAPP_NOTIFICAR_ESPERA_CLIENTE" "${WHATSAPP_NOTIFICAR_ESPERA_CLIENTE:-1}"
append_env_line "$env_tmp" "WHATSAPP_NOTIFICAR_NO_SE_PUDO" "${WHATSAPP_NOTIFICAR_NO_SE_PUDO:-0}"
append_env_line "$env_tmp" "CRM_ENABLED" "${CRM_ENABLED:-1}"
append_env_line "$env_tmp" "CRM_BANDEJA_JEFE_MIN_NIVEL" "${CRM_BANDEJA_JEFE_MIN_NIVEL:-100}"
append_env_line "$env_tmp" "AI_ENABLED" "${AI_ENABLED:-0}"
append_env_line "$env_tmp" "AI_PROVIDER" "${AI_PROVIDER:-openai}"
append_env_line "$env_tmp" "AI_MODEL" "${AI_MODEL:-gpt-4o-mini}"
append_env_line "$env_tmp" "AI_REASONING_EFFORT" "${AI_REASONING_EFFORT:-low}"
append_env_line "$env_tmp" "AI_MAX_TOKENS" "${AI_MAX_TOKENS:-500}"
append_env_line "$env_tmp" "AI_TEMPERATURE" "${AI_TEMPERATURE:-0.7}"
append_env_line "$env_tmp" "AI_API_KEY" "${AI_API_KEY:-}"
append_env_line "$env_tmp" "AI_BASE_URL" "${AI_BASE_URL:-}"
append_env_line "$env_tmp" "DEEPSEEK_API_KEY" "${DEEPSEEK_API_KEY:-}"
append_env_line "$env_tmp" "DEEPSEEK_BASE_URL" "${DEEPSEEK_BASE_URL:-}"
append_env_line "$env_tmp" "LOG_LEVEL" "${LOG_LEVEL:-}"
append_env_line "$env_tmp" "LOG_REQUEST_ACCESS" "${LOG_REQUEST_ACCESS:-0}"
append_env_line "$env_tmp" "LOG_REQUEST_VERBOSE" "${LOG_REQUEST_VERBOSE:-0}"
append_env_line "$env_tmp" "LOG_REQUEST_BODY" "${LOG_REQUEST_BODY:-0}"
append_env_line "$env_tmp" "LOG_WHATSAPP_WEBHOOK" "${LOG_WHATSAPP_WEBHOOK:-0}"
append_env_line "$env_tmp" "LOG_DB_COMMITS" "${LOG_DB_COMMITS:-0}"
append_env_line "$env_tmp" "RCLONE_DEST_DIR" ""
append_env_line "$env_tmp" "RCLONE_OP" "copy"
append_env_line "$env_tmp" "RCLONE_FAIL_OPEN" "0"
as_root cp "$env_tmp" "$env_file_path"

if [ -s "$extra_env_tmp" ]; then
  as_root bash -lc "printf '\n' >> '$env_file_path'"
  as_root bash -lc "cat '$extra_env_tmp' >> '$env_file_path'"
fi

as_root chgrp "$service_group" "$env_file_path" 2>/dev/null || true
as_root chmod 640 "$env_file_path" 2>/dev/null || true

mkdir -p "$app_dir/logs"
as_root chown -R "$service_user:$service_group" "$app_dir/logs" 2>/dev/null || true
as_root chmod 775 "$app_dir/logs" 2>/dev/null || true

uploads_dir="$app_dir/app/static/uploads"
tienda_uploads_dir="$app_dir/app/static/tienda_uploads"
tienda_upload_web_user="${TIENDA_UPLOAD_WEB_USER:-www-data}"

mkdir -p "$uploads_dir" "$tienda_uploads_dir/portadas" "$tienda_uploads_dir/compras/facturas"
as_root chown -R "$service_user:$service_group" "$uploads_dir" "$tienda_uploads_dir" 2>/dev/null || true
as_root find "$uploads_dir" "$tienda_uploads_dir" -type d -exec chmod 755 {} \; 2>/dev/null || true
as_root find "$uploads_dir" "$tienda_uploads_dir" -type f -exec chmod 644 {} \; 2>/dev/null || true
if have_cmd setfacl && id "$tienda_upload_web_user" >/dev/null 2>&1; then
  as_root setfacl -R -m "u:$tienda_upload_web_user:rx" "$uploads_dir" "$tienda_uploads_dir" >/dev/null 2>&1 || true
  as_root setfacl -R -d -m "u:$tienda_upload_web_user:rx" "$uploads_dir" "$tienda_uploads_dir" >/dev/null 2>&1 || true
fi

unit_path="/etc/systemd/system/${service_name}.service"

as_root bash -lc "cat > '$unit_path' <<EOF
[Unit]
Description=Sistema Cliente 2
After=network.target mysql.service mariadb.service

[Service]
Type=simple
User=$service_user
Group=$service_group
WorkingDirectory=$app_dir
EnvironmentFile=$env_file_path
ExecStart=$python_bin $app_dir/run.py
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF"

backup_unit_path="/etc/systemd/system/${service_name}-backup.service"
backup_timer_path="/etc/systemd/system/${service_name}-backup.timer"

as_root mkdir -p "$backup_dir"
as_root chown "$service_user:$service_group" "$backup_dir" 2>/dev/null || true
as_root chmod 750 "$backup_dir" 2>/dev/null || true

as_root bash -lc "cat > '$backup_unit_path' <<EOF
[Unit]
Description=Backup BD - Sistema Cliente 2
After=network.target mysql.service mariadb.service

[Service]
Type=oneshot
User=$service_user
Group=$service_group
WorkingDirectory=$app_dir
EnvironmentFile=$env_file_path
Environment=ENV_FILE_PATH=$env_file_path
Environment=BACKUP_DIR=$backup_dir
Environment=RETENTION_DAYS=$retention_days
Environment=COMPRESS=$compress
ExecStart=/usr/bin/env bash $app_dir/backup_db.sh
NoNewPrivileges=true
PrivateTmp=true
EOF"

as_root bash -lc "cat > '$backup_timer_path' <<EOF
[Unit]
Description=Backup diario BD - Sistema Cliente 2

[Timer]
OnCalendar=$backup_on_calendar
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF"

if have_cmd systemctl; then
  as_root systemctl daemon-reload
  as_root systemctl enable --now "$service_name"
  as_root systemctl enable --now "${service_name}-backup.timer"
fi

if [ "$import_legacy_csv" = "1" ]; then
  if ls "$app_dir/deploy/"*.csv* >/dev/null 2>&1 || ls "$app_dir/Base de datos/"*.csv >/dev/null 2>&1; then
    export ENV_FILE_PATH="$env_file_path"
    export VENV_PATH="$venv_path"
    /usr/bin/env bash "$app_dir/deploy/import_legacy_data.sh" || true
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
  filter_src="$app_dir/deploy/fail2ban/filter.d/sistema-cliente2-auth.conf"
  jail_tpl="$app_dir/deploy/fail2ban/jail.d/sistema-cliente2.conf.template"
  as_root install -D -m 0644 "$filter_src" "/etc/fail2ban/filter.d/sistema-cliente2-auth.conf"
  as_root env \
    JAIL_TEMPLATE="$jail_tpl" \
    APP_LOG_PATH="$app_dir/logs/sistema.log" \
    APP_PORT="$app_port" \
    python3 - <<'PY'
from pathlib import Path
import os

tpl = Path(os.environ["JAIL_TEMPLATE"]).read_text(encoding="utf-8")
out = tpl.replace("__APP_LOG_PATH__", os.environ["APP_LOG_PATH"]).replace("__APP_PORT__", os.environ["APP_PORT"])
Path("/etc/fail2ban/jail.d/sistema-cliente2.conf").write_text(out, encoding="utf-8")
PY
  as_root systemctl enable --now fail2ban >/dev/null 2>&1 || true
  as_root systemctl restart fail2ban >/dev/null 2>&1 || true
fi

if [ -n "$domain" ]; then
  export DOMAIN="$domain"
  export APP_PORT="$app_port"
  export SERVICE_NAME="$service_name"
  export CADDYFILE_PATH="$caddyfile_path"
  export CADDY_SITES_DIR="$caddy_sites_dir"
  export SETUP_CADDY="$setup_caddy"
  /usr/bin/env bash "$app_dir/deploy/setup_caddy.sh"
fi

echo "Listo."
echo "Servicio: $service_name"
echo "Puerto: $app_port"
echo "ENV_FILE: $env_file_path"
echo "DB_NAME: $db_name"
echo "DB_USER: $db_user"
if [ "$db_password_generated" = "1" ]; then
  echo "DB_PASSWORD: generado (ver ENV_FILE)"
fi
if [ "$app_config" = "production" ]; then
  echo "Usuario admin: admin"
  if [ "$bootstrap_admin_password_generated" = "1" ]; then
    echo "Password admin: $bootstrap_admin_password"
  else
    echo "Password admin: (ver ENV_FILE)"
  fi
  if [ -n "$bootstrap_root_username" ]; then
    echo "Usuario root: $bootstrap_root_username"
    if [ "$bootstrap_root_password_generated" = "1" ]; then
      echo "Password root: $bootstrap_root_password"
    else
      echo "Password root: (ver ENV_FILE)"
    fi
  fi
fi
if [ -n "$domain" ]; then
  echo "Dominio: $domain"
  echo "Caddy site: $caddy_sites_dir/${service_name}.caddy"
fi
