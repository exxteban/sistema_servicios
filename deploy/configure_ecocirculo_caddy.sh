#!/usr/bin/env bash
set -euo pipefail

domain="${DOMAIN:-ecocirculo.pysystems.online}"
expected_public_ip="${EXPECTED_PUBLIC_IP:-204.12.245.108}"
app_port="${APP_PORT:-3116}"
service_name="${SERVICE_NAME:-sistema-ecocirculo}"
caddyfile_path="${CADDYFILE_PATH:-/etc/caddy/Caddyfile}"
caddy_sites_dir="${CADDY_SITES_DIR:-/etc/caddy/sites.d}"
setup_caddy="${SETUP_CADDY:-1}"
check_dns="${CHECK_DNS:-1}"
setup_ufw="${SETUP_UFW:-1}"
enable_ufw="${ENABLE_UFW:-1}"
ssh_port="${SSH_PORT:-22}"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

install_caddy() {
  if [ "$setup_caddy" != "1" ] || have_cmd caddy; then
    return 0
  fi

  if have_cmd apt-get; then
    as_root apt-get update -y
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
}

install_ufw() {
  if [ "$setup_ufw" != "1" ] || have_cmd ufw; then
    return 0
  fi

  if have_cmd apt-get; then
    as_root apt-get update -y
    as_root apt-get install -y ufw
  elif have_cmd dnf; then
    as_root dnf install -y ufw
  elif have_cmd yum; then
    as_root yum install -y ufw
  else
    echo "Aviso: no se detectó gestor de paquetes compatible para instalar UFW."
  fi
}

configure_ufw() {
  if [ "$setup_ufw" != "1" ]; then
    return 0
  fi

  install_ufw

  if ! have_cmd ufw; then
    echo "Aviso: UFW no está instalado; se omite configuración de firewall."
    return 0
  fi

  as_root ufw allow "${ssh_port}/tcp"
  as_root ufw allow 80/tcp
  as_root ufw allow 443/tcp
  as_root ufw default deny incoming
  as_root ufw default allow outgoing

  if [ "$enable_ufw" = "1" ]; then
    as_root ufw --force enable
  else
    echo "UFW configurado pero no habilitado porque ENABLE_UFW=$enable_ufw."
  fi
}

validate_dns() {
  if [ "$check_dns" != "1" ]; then
    return 0
  fi

  if ! have_cmd getent; then
    echo "Aviso: no se pudo validar DNS porque no existe getent."
    return 0
  fi

  resolved_ips="$(getent ahostsv4 "$domain" | awk '{print $1}' | sort -u | tr '\n' ' ')"
  if [ -z "$resolved_ips" ]; then
    echo "Aviso: $domain todavía no resuelve por DNS."
    echo "Configura un registro A hacia $expected_public_ip antes de pedir SSL."
    return 0
  fi

  case " $resolved_ips " in
    *" $expected_public_ip "*) ;;
    *)
      echo "Aviso: $domain resuelve a: $resolved_ips"
      echo "El IP esperado es: $expected_public_ip"
      ;;
  esac
}

write_caddy_site() {
  as_root mkdir -p "$caddy_sites_dir"
  site_path="$caddy_sites_dir/${service_name}.caddy"

  as_root bash -lc "cat > '$site_path' <<EOF
$domain {
	reverse_proxy 127.0.0.1:$app_port
}
EOF"

  if [ ! -f "$caddyfile_path" ]; then
    as_root bash -lc "cat > '$caddyfile_path' <<EOF
{
	email admin@$domain
}

import $caddy_sites_dir/*.caddy
EOF"
  elif ! as_root grep -qF "import $caddy_sites_dir/*.caddy" "$caddyfile_path"; then
    backup_path="${caddyfile_path}.bak.$(date +%Y%m%d%H%M%S)"
    as_root cp "$caddyfile_path" "$backup_path"
    as_root bash -lc "printf '\nimport %s\n' '$caddy_sites_dir/*.caddy' >> '$caddyfile_path'"
  fi
}

reload_caddy() {
  if have_cmd caddy; then
    as_root caddy validate --config "$caddyfile_path"
  fi

  if have_cmd systemctl; then
    as_root systemctl enable --now caddy
    as_root systemctl reload caddy >/dev/null 2>&1 || as_root systemctl restart caddy
  fi
}

if [ -z "$domain" ]; then
  echo "DOMAIN no puede estar vacío."
  exit 1
fi

install_caddy

if ! have_cmd caddy; then
  echo "Caddy no está instalado. Ejecuta con SETUP_CADDY=1 o instálalo manualmente."
  exit 1
fi

validate_dns
configure_ufw
write_caddy_site
reload_caddy

echo "Caddy configurado para https://$domain -> 127.0.0.1:$app_port"
echo "Archivo del sitio: $caddy_sites_dir/${service_name}.caddy"
if [ "$setup_ufw" = "1" ]; then
  echo "Firewall UFW: abiertos ${ssh_port}/tcp, 80/tcp y 443/tcp. No se abre $app_port públicamente."
fi
