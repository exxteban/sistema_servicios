#!/usr/bin/env bash
set -euo pipefail
app_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git_ref="${GIT_REF:-}"
venv_path="${VENV_PATH:-$app_dir/.venv}"
service_name="${SERVICE_NAME:-sistema-ecocirculo}"
env_file_path="${ENV_FILE_PATH:-}"
use_system_python="${USE_SYSTEM_PYTHON:-0}"
skip_git="${SKIP_GIT:-1}"
run_tienda_migrations="${RUN_TIENDA_MIGRATIONS:-1}"
run_tienda_build="${RUN_TIENDA_BUILD:-1}"
run_app_bootstrap_migrations="${RUN_APP_BOOTSTRAP_MIGRATIONS:-1}"
run_tienda_upload_permissions="${RUN_TIENDA_UPLOAD_PERMISSIONS:-1}"
auto_install_node="${AUTO_INSTALL_NODE:-1}"
npm_ipv4_fallback="${NPM_IPV4_FALLBACK:-1}"
tienda_upload_web_user="${TIENDA_UPLOAD_WEB_USER:-www-data}"
tienda_dir="$app_dir/tienda_online"

have_cmd() { command -v "$1" >/dev/null 2>&1; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

run_npm_step() {
  local label="$1"
  shift
  if (cd "$tienda_dir" && "$@"); then
    return 0
  fi
  if [ "$npm_ipv4_fallback" != "1" ]; then
    return 1
  fi
  echo "Falló $label. Reintentando con preferencia IPv4..."
  if (cd "$tienda_dir" && NODE_OPTIONS="--dns-result-order=ipv4first ${NODE_OPTIONS:-}" "$@"); then
    return 0
  fi
  return 1
}

load_env_file() {
  if [ -f "$env_file_path" ]; then
    set -a
    . "$env_file_path"
    set +a
  fi
}

resolve_env_file_path() {
  if [ -n "$env_file_path" ]; then
    return
  fi

  if [ -n "$service_name" ] && command -v systemctl >/dev/null 2>&1; then
    unit_env_file="$(systemctl show "$service_name" --property=EnvironmentFiles --value 2>/dev/null | head -n1 | sed 's/^-//' | awk '{print $1}')"
    if [ -n "$unit_env_file" ] && [ -f "$unit_env_file" ]; then
      env_file_path="$unit_env_file"
      return
    fi
  fi

  if [ -f /etc/sistema_ecocirculo.env ]; then
    env_file_path="/etc/sistema_ecocirculo.env"
  else
    env_file_path="/etc/sistema_cliente2.env"
  fi
}

fix_upload_permissions() {
  uploads_dir="$app_dir/app/static/uploads"
  tienda_uploads_dir="$app_dir/app/static/tienda_uploads"
  app_owner="${SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
  app_group="${SERVICE_GROUP:-$app_owner}"
  web_user="$tienda_upload_web_user"

  mkdir -p "$uploads_dir" "$tienda_uploads_dir/portadas" "$tienda_uploads_dir/compras/facturas"
  as_root chown -R "$app_owner:$app_group" "$uploads_dir" "$tienda_uploads_dir"
  as_root find "$uploads_dir" "$tienda_uploads_dir" -type d -exec chmod 755 {} \;
  as_root find "$uploads_dir" "$tienda_uploads_dir" -type f -exec chmod 644 {} \;

  if command -v setfacl >/dev/null 2>&1 && id "$web_user" >/dev/null 2>&1; then
    as_root setfacl -R -m "u:$web_user:rx" "$uploads_dir" "$tienda_uploads_dir" || true
    as_root setfacl -R -d -m "u:$web_user:rx" "$uploads_dir" "$tienda_uploads_dir" || true
  fi
}

resolve_env_file_path
load_env_file
cd "$app_dir"
if [ "$skip_git" != "1" ]; then
  if [ -d .git ]; then
    git fetch --all --tags
    if [ -n "$git_ref" ]; then
      git checkout -f "$git_ref"
    else
      git pull --ff-only || true
    fi
  fi
fi
if [ "$use_system_python" = "1" ]; then
  python_bin="python3"
  pip_bin="python3 -m pip"
else
  if [ ! -d "$venv_path" ]; then
    python3 -m venv "$venv_path"
  fi
  python_bin="$venv_path/bin/python"
  pip_bin="$venv_path/bin/pip"
fi
"$python_bin" -m pip install --upgrade pip || true
if [ "${MIN_ONLY_XHTML2PDF:-1}" = "1" ]; then
  if ! "$python_bin" -m pip install "xhtml2pdf==0.2.17"; then
    if ! "$python_bin" -m pip install --user "xhtml2pdf==0.2.17"; then
      mkdir -p "$app_dir/libs"
      # Instalar xhtml2pdf sin dependencias (para evitar svglib/rlpycairo/pycairo)
      "$python_bin" -m pip install --no-cache-dir --no-deps --target "$app_dir/libs" "xhtml2pdf==0.2.17"
      # Instalar dependencias mínimas necesarias en libs
      "$python_bin" -m pip install --no-cache-dir --target "$app_dir/libs" "reportlab" "html5lib" "cssselect" "Pillow" "pypdf" "PyPDF2" "asn1crypto" "arabic-reshaper" "python-bidi"
      # Stub opcional para firmas si pyhanko no está disponible
      mkdir -p "$app_dir/libs/xhtml2pdf/builders"
      cat > "$app_dir/libs/xhtml2pdf/builders/signs.py" <<'PY'
try:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter  # type: ignore
    from pyhanko.sign import signers  # type: ignore
    from pyhanko_certvalidator import ValidationContext  # type: ignore
except Exception:
    IncrementalPdfFileWriter = None
    signers = None
    ValidationContext = None

class PDFSignature:
    def __init__(self, *args, **kwargs):
        self.enabled = all([IncrementalPdfFileWriter, signers, ValidationContext])

    def sign_pdf(self, pdf_bytes: bytes) -> bytes:
        # Sin dependencias de firma disponibles, retornar el PDF tal como está
        return pdf_bytes
PY
    fi
  fi
  req_tmp="$(mktemp)"
  grep -Ev '^[[:space:]]*($|#|xhtml2pdf==)' "$app_dir/requirements.txt" > "$req_tmp"
  if ! "$python_bin" -m pip install -r "$req_tmp"; then
    mkdir -p "$app_dir/libs"
    "$python_bin" -m pip install --no-cache-dir --target "$app_dir/libs" -r "$req_tmp"
  fi
  rm -f "$req_tmp"
else
  if ! "$python_bin" -m pip install -r "$app_dir/requirements.txt"; then
    mkdir -p "$app_dir/libs"
    "$python_bin" -m pip install --no-cache-dir --target "$app_dir/libs" -r "$app_dir/requirements.txt"
  fi
fi
if [ "$run_tienda_build" = "1" ]; then
  if [ ! -d "$tienda_dir" ]; then
    echo "No existe el directorio tienda_online: $tienda_dir"
    exit 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    if [ "$auto_install_node" = "1" ]; then
      if have_cmd apt-get; then
        as_root apt-get update -y
        as_root apt-get install -y nodejs npm
      elif have_cmd dnf; then
        as_root dnf install -y nodejs npm
      elif have_cmd yum; then
        as_root yum install -y nodejs npm
      fi
    fi
    if ! command -v npm >/dev/null 2>&1; then
      echo "No se encontró npm. Instala Node.js/npm o ejecuta con RUN_TIENDA_BUILD=0."
      exit 1
    fi
  fi
  if [ -f "$tienda_dir/package-lock.json" ]; then
    run_npm_step "npm ci" npm ci --no-audit --no-fund || run_npm_step "npm install" npm install --no-audit --no-fund
  elif [ -f "$tienda_dir/package.json" ]; then
    run_npm_step "npm install" npm install --no-audit --no-fund
  else
    echo "No se encontró package.json en $tienda_dir"
    exit 1
  fi
  run_npm_step "npm run build" npm run build
fi
if [ "$run_tienda_migrations" = "1" ]; then
  tienda_migrations=(
    "$app_dir/migrations/tienda_fase1.py"
    "$app_dir/migrations/tienda_fase2.py"
    "$app_dir/migrations/tienda_destacados_ofertas.py"
    "$app_dir/migrations/tienda_precio_anterior.py"
    "$app_dir/migrations/tienda_config_update.py"
    "$app_dir/migrations/tienda_config_imagen_portada.py"
    "$app_dir/migrations/tienda_config_contacto_expandido.py"
    "$app_dir/migrations/compras_hora_factura.py"
    "$app_dir/migrations/caja_reclasificar_vueltos.py"
  )
  for migration in "${tienda_migrations[@]}"; do
    if [ -f "$migration" ]; then
      "$python_bin" "$migration"
    fi
  done
fi
if [ "$run_tienda_upload_permissions" = "1" ]; then
  fix_upload_permissions
fi
if [ "$run_app_bootstrap_migrations" = "1" ]; then
  "$python_bin" -c "import os; from app import create_app; create_app(os.environ.get('APP_CONFIG') or 'default'); print('bootstrap_migrations_ok')"
fi
if [ -n "$service_name" ] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl restart "$service_name" 2>/dev/null || true
fi
echo "OK"
