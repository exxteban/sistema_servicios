#!/usr/bin/env bash
set -euo pipefail

domain="${DOMAIN:-}"
app_port="${APP_PORT:-3112}"
service_name="${SERVICE_NAME:-sistema-telefonica}"
caddyfile_path="${CADDYFILE_PATH:-/etc/caddy/Caddyfile}"
caddy_sites_dir="${CADDY_SITES_DIR:-/etc/caddy/sites.d}"
setup_caddy="${SETUP_CADDY:-1}"
stop_nginx="${STOP_NGINX:-0}"
disable_nginx="${DISABLE_NGINX:-0}"
caddy_append_import="${CADDY_APPEND_IMPORT:-0}"
caddy_rewrite_default="${CADDY_REWRITE_DEFAULT:-0}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

stop_conflicting_nginx() {
  if [ "$stop_nginx" != "1" ]; then
    return 0
  fi

  if ! have_cmd systemctl; then
    return 0
  fi

  if ! systemctl list-unit-files nginx.service >/dev/null 2>&1; then
    return 0
  fi

  if systemctl is-active --quiet nginx; then
    as_root systemctl stop nginx
  fi

  if [ "$disable_nginx" = "1" ]; then
    as_root systemctl disable nginx >/dev/null 2>&1 || true
  fi
}

write_base_caddyfile() {
  as_root bash -lc "cat > '$caddyfile_path' <<EOF
{
	email admin@$domain
}

import $caddy_sites_dir/*.caddy
EOF"
}

ensure_caddyfile() {
  if [ ! -f "$caddyfile_path" ]; then
    write_base_caddyfile
    return 0
  fi

  if as_root grep -qF "import $caddy_sites_dir/*.caddy" "$caddyfile_path"; then
    return 0
  fi

  if [ "$caddy_rewrite_default" = "1" ] && as_root grep -qF "root * /usr/share/caddy" "$caddyfile_path" && as_root grep -qF "file_server" "$caddyfile_path"; then
    backup_path="${caddyfile_path}.bak.$(date +%Y%m%d%H%M%S)"
    as_root cp "$caddyfile_path" "$backup_path"
    write_base_caddyfile
    return 0
  fi

  if [ "$caddy_append_import" = "1" ]; then
    backup_path="${caddyfile_path}.bak.$(date +%Y%m%d%H%M%S)"
    as_root cp "$caddyfile_path" "$backup_path"
    as_root bash -lc "printf '\nimport %s\n' '$caddy_sites_dir/*.caddy' >> '$caddyfile_path'"
    return 0
  fi

  echo "Caddyfile existente sin import de $caddy_sites_dir/*.caddy."
  echo "Se creo el sitio $caddy_sites_dir/${service_name}.caddy, pero no se modifica el Caddyfile base automaticamente."
  echo "En host compartido integra el sitio manualmente o ejecuta con CADDY_APPEND_IMPORT=1."
  exit 1
}

if [ -z "$domain" ]; then
  echo "DOMAIN vacío, se omite configuración de Caddy."
  exit 0
fi

if [ "$setup_caddy" = "1" ] && ! have_cmd caddy; then
  if have_cmd apt-get; then
    as_root apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
    as_root mkdir -p /etc/apt/keyrings
    as_root bash -lc "curl -fsSL 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor > /etc/apt/keyrings/caddy-stable-archive-keyring.gpg"
    as_root chmod 0644 /etc/apt/keyrings/caddy-stable-archive-keyring.gpg
    as_root bash -lc "cat > /etc/apt/sources.list.d/caddy-stable.list <<EOF
deb [signed-by=/etc/apt/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main
deb-src [signed-by=/etc/apt/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main
EOF"
    as_root apt-get update -y
    as_root apt-get install -y caddy
  elif have_cmd dnf; then
    as_root dnf install -y 'dnf-command(copr)' >/dev/null 2>&1 || true
    as_root dnf copr enable -y @caddy/caddy >/dev/null 2>&1 || true
    as_root dnf install -y caddy
  elif have_cmd yum; then
    as_root yum install -y yum-plugin-copr >/dev/null 2>&1 || true
    as_root yum copr enable -y @caddy/caddy >/dev/null 2>&1 || true
    as_root yum install -y caddy
  else
    echo "No se detectó gestor de paquetes compatible para instalar Caddy."
    exit 1
  fi
fi

if ! have_cmd caddy; then
  echo "Caddy no está instalado. Define SETUP_CADDY=1 para instalarlo automáticamente."
  exit 1
fi

as_root mkdir -p "$caddy_sites_dir"
site_path="$caddy_sites_dir/${service_name}.caddy"
as_root bash -lc "cat > '$site_path' <<EOF
$domain {
	reverse_proxy 127.0.0.1:$app_port
}
EOF"

ensure_caddyfile
stop_conflicting_nginx

if have_cmd caddy; then
  as_root caddy validate --config "$caddyfile_path"
fi

if have_cmd systemctl; then
  as_root systemctl enable caddy >/dev/null 2>&1 || true
  as_root systemctl restart caddy
  if ! systemctl is-active --quiet caddy; then
    as_root systemctl status caddy --no-pager || true
    echo "Caddy no quedo activo. Revisa conflictos de puertos y la configuracion en /etc/caddy/Caddyfile."
    exit 1
  fi
fi

echo "Caddy configurado para $domain en $site_path"
