#!/bin/bash
# ==============================================================================
# Script de configuración de carpetas y permisos para la Tienda Online
# Ejecutar este script en el servidor de producción (Linux/Ubuntu)
# 
# Uso: 
#   sudo ./setup_permisos_tienda.sh [usuario_servidor]
# 
# Ejemplo: 
#   sudo ./setup_permisos_tienda.sh www-data
# ==============================================================================

# Si no se pasa un usuario como parámetro, usa "www-data" por defecto (estándar en Nginx/Ubuntu)
WEB_USER=${1:-www-data}

echo "================================================================="
echo "⚙️ Configurando directorios de la Tienda Online"
echo "👤 Usuario del servidor web: $WEB_USER"
echo "================================================================="

# Variables de ruta (asumiendo que el script se ejecuta dentro de sistema_silvio_cel)
UPLOADS_DIR="app/static/uploads"
TIENDA_UPLOADS_DIR="app/static/tienda_uploads"

echo "📂 1. Verificando y creando directorios principales..."
mkdir -p "$UPLOADS_DIR"
mkdir -p "$TIENDA_UPLOADS_DIR/portadas"
mkdir -p "$TIENDA_UPLOADS_DIR/compras/facturas"
echo "   ✅ Directorios creados exitosamente."

echo "🔑 2. Asignando propiedad al usuario '$WEB_USER'..."
# Solo intentamos hacer chown si el usuario existe en el sistema
if id "$WEB_USER" &>/dev/null; then
    chown -R "$WEB_USER":"$WEB_USER" "$UPLOADS_DIR"
    chown -R "$WEB_USER":"$WEB_USER" "$TIENDA_UPLOADS_DIR"
    echo "   ✅ Propiedad asignada correctamente."
else
    echo "   ⚠️ ADVERTENCIA: El usuario '$WEB_USER' no existe en este sistema."
    echo "   Por favor, verifica qué usuario ejecuta tu servidor web (ej. nginx, apache, root) y pásalo como parámetro:"
    echo "   Ejemplo: sudo ./setup_permisos_tienda.sh tu_usuario"
    exit 1
fi

echo "🛡️ 3. Estableciendo permisos seguros (755)..."
# 755 = El dueño puede leer, escribir y ejecutar. Los demás solo pueden leer y ejecutar.
chmod -R 755 "$UPLOADS_DIR"
chmod -R 755 "$TIENDA_UPLOADS_DIR"
echo "   ✅ Permisos establecidos correctamente."

echo "================================================================="
echo "🚀 ¡Todo listo! Las carpetas están preparadas para recibir imágenes."
echo "================================================================="
