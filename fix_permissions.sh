#!/bin/bash
# Script para arreglar permisos en el servidor
# Ejecutar como: sudo bash fix_permissions.sh

echo "=== Arreglando permisos del sistema de inventario ==="

# Directorio base de la aplicación
APP_DIR="/home/administrator/sistema_inventario/stockinventariojavier"

# Usuario que corre el servicio (ajustar si es diferente)
APP_USER="administrator"

echo "Directorio de aplicación: $APP_DIR"
echo "Usuario de la aplicación: $APP_USER"

# Crear directorio de logs si no existe
if [ ! -d "$APP_DIR/logs" ]; then
    echo "Creando directorio logs..."
    mkdir -p "$APP_DIR/logs"
fi

# Dar permisos al directorio logs
echo "Configurando permisos de logs..."
chown -R $APP_USER:$APP_USER "$APP_DIR/logs"
chmod -R 755 "$APP_DIR/logs"

# Dar permisos al directorio instance (base de datos)
if [ -d "$APP_DIR/instance" ]; then
    echo "Configurando permisos de instance..."
    chown -R $APP_USER:$APP_USER "$APP_DIR/instance"
    chmod -R 755 "$APP_DIR/instance"
fi

# Dar permisos a archivos de base de datos
if [ -f "$APP_DIR/instance/inventario.db" ]; then
    echo "Configurando permisos de base de datos..."
    chown $APP_USER:$APP_USER "$APP_DIR/instance/inventario.db"
    chmod 664 "$APP_DIR/instance/inventario.db"
fi

# Dar permisos al directorio completo (recursivo)
echo "Configurando permisos del directorio completo..."
chown -R $APP_USER:$APP_USER "$APP_DIR"

# Asegurar que los directorios sean ejecutables
find "$APP_DIR" -type d -exec chmod 755 {} \;

# Asegurar que los archivos Python sean legibles
find "$APP_DIR" -name "*.py" -exec chmod 644 {} \;

echo ""
echo "=== Permisos configurados ==="
echo ""
echo "Verificando permisos:"
ls -la "$APP_DIR/logs" 2>/dev/null || echo "  logs: no existe"
ls -la "$APP_DIR/instance" 2>/dev/null || echo "  instance: no existe"

echo ""
echo "Ahora reinicia el servicio:"
echo "  sudo systemctl restart inventario-ventas"
echo ""
echo "Para ver el estado:"
echo "  sudo systemctl status inventario-ventas"
echo ""
echo "Para ver los logs:"
echo "  sudo journalctl -u inventario-ventas -f"
