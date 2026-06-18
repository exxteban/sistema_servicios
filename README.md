# Sistema de Gestión Comercial + Gastronomía

Sistema integral de inventario, ventas (POS), caja, cobranzas, CRM por WhatsApp,
reportes/BI y un **módulo de Gastronomía** (POS touch, cocina/KDS, salón, delivery con
GPS, menú TV, reportes) con **tienda online** integrada para pedidos web.

Cada instalación es una **instancia independiente** (su propia base de datos y procesos),
no es un SaaS multi-tenant compartido.

---

## Stack

- **Backend:** Python 3.13 · Flask 3 · SQLAlchemy 2 · Flask-Login
- **Base de datos:** SQLite (desarrollo) o MySQL/MariaDB vía PyMySQL (producción)
- **Servidor WSGI:** Waitress (producción)
- **Tienda online:** React 18 + Vite 5 + TailwindCSS 3 + React Router 6 (carpeta `tienda_online/`)
- **PDFs:** xhtml2pdf · **QR:** segno · **Excel:** openpyxl
- **WhatsApp Cloud API + IA (OpenAI/DeepSeek)** opcionales

---

## Requisitos

- Python 3.13+
- Node.js 20+ (solo si se compila la tienda online)
- MySQL/MariaDB (producción) — opcional, SQLite para desarrollo

## Instalación (desarrollo)

```powershell
# 1) Entorno virtual y dependencias
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt   # solo para tests

# 2) (Opcional) compilar la tienda online
cd tienda_online
npm install
npm run build      # genera tienda_online/dist que sirve el backend
cd ..

# 3) Configurar entorno
copy .env.example .env        # ajustar DATABASE_URL, SECRET_KEY, etc.

# 4) Arrancar
python run.py                 # http://127.0.0.1:5003
```

### Variables de entorno principales (`.env`)

| Variable | Default | Descripción |
|---|---|---|
| `DATABASE_URL` | `sqlite:///inventario.db` | URI de la base de datos |
| `SECRET_KEY` | — | **Obligatorio cambiar en producción** |
| `APP_CONFIG` | `default` | `development` · `production` · `testing` |
| `APP_TIMEZONE` | `America/Asuncion` | Zona horaria |
| `HOST` / `PORT` | `127.0.0.1` / `5003` | Bind del servidor |
| `SERVER` | `waitress` (prod) | `waitress` o `flask` |
| `WHATSAPP_ENABLED` | `false` | Activar WhatsApp Cloud API |
| `AI_ENABLED` | `false` | Activar asistente IA |

> Ver `config.py` para el detalle completo y `deploy/*.env.example` para ejemplos de cliente.

## Instalación (producción por cliente)

Cada cliente se despliega como instancia aislada. Hay instaladores de referencia en `deploy/`:

```bash
# Ejemplo (servidor Linux)
sudo bash deploy/install_lionsburguer.sh        # referencias Lionsburguer
sudo bash deploy/install_demoservicios.sh       # referencias Demo Servicios
```

Incluyen configuración de Caddy/Nginx, fail2ban y servicio systemd. Un mismo servidor
puede alojar hasta 3 instancias, cada una con su propio `.env`, base de datos y proceso.

---

## Estructura del proyecto

```
sistema_servicios/
├── app/                       # Backoffice principal (Flask)
│   ├── models.py              # Modelos compartidos (Venta, SesionCaja, Usuario, ...)
│   ├── utils/permisos.py      # Sistema de permisos/autorizaciones
│   └── ...
├── gastronomia/               # Módulo Gastronomía (aislado)
│   ├── routes/                # Blueprints de páginas y API
│   ├── services/              # Lógica de negocio (pedidos, cocina, stock, reportes)
│   ├── templates/gastronomia/ # Jinja2
│   ├── static/js/             # POS, cocina, salón, delivery, menú TV
│   └── models.py              # GastronomiaPedido, GastronomiaClienteConfig, ...
├── tienda_online/             # Frontend React (catálogo web para clientes finales)
├── deploy/                    # Instaladores y config por cliente
├── scripts/                   # Setup de tests, migraciones de runtime
├── tests/                     # Tests organizados (preferido para tests nuevos)
├── migrations/                # Migraciones de esquema
├── run.py                     # Punto de entrada
├── config.py                  # Configuración por entorno
└── requirements.txt
```

> **Regla del proyecto:** ver `AGENTS.md`. El código de `tienda_online/` NO debe invadir el
> backoffice; solo consume la API REST `/api/tienda/...`. Ningún archivo debe superar las
> **600 líneas** (dividir en componentes/hooks/services/utils).

---

## Módulo Gastronomía

### Activación

Se activa por cliente mediante `GastronomiaClienteConfig.gastronomia_activo = True`
(una fila por `id_cliente`). Mientras esté activa, el menú y los permisos de gastronomía
quedan disponibles en el backoffice.

### Roles y permisos

Los permisos (asignables desde **Usuarios → Permisos**) son:

| Permiso | Acceso |
|---|---|
| `gastronomia_acceso` | Entrada general al módulo |
| `gastronomia_menu` | Administrar menú, productos y modificadores |
| `gastronomia_pos` | POS touch (carga de pedidos) |
| `gastronomia_cocina` | KDS de cocina y estados de preparación |
| `gastronomia_caja` | Caja de gastronomía, cobros y anulaciones |
| `gastronomia_salon` | Gestión de mesas/salón |
| `gastronomia_delivery` | Gestión de repartos |
| `gastronomia_delivery_gps` | Acceso a localización GPS de repartidores |
| `gastronomia_reportes` | Reportes y exportación CSV |

Los administradores (`es_admin`) tienen acceso completo automáticamente.

### Funcionalidades

- **POS touch:** carga rápida de pedidos con modificadores y precios por canal.
- **Cocina (KDS):** pantalla de producción con estados, **sonidos configurables**
  (perfiles *clásico* / *suave* / *urgente*, volumen, preferencias por usuario).
- **Salón:** mesas, estados y asignación de mozos.
- **Caja:** cobros, sesión de caja, anulaciones con autorización.
- **Delivery con GPS:** seguimiento de repartidores (con privacidad por permiso).
- **Menú TV:** pantalla pública de productos.
- **Reportes:** ventas, ticket promedio, productos más vendidos, **exportación CSV**
  (compatible Excel con BOM UTF-8).
- **Stock:** control y preview de disponibilidad.

### Endpoints API clave

- `GET /api/gastronomia/cocina/preferencias-sonido` · `POST ...` (guardar)
- `GET /gastronomia/reportes/resumen`
- `GET /gastronomia/reportes/exportar.csv`

---

## Tienda Online (`tienda_online/`)

Catálogo web React para que los clientes finales armen pedidos. Se comunica con el
backoffice **únicamente** vía API REST (`/api/tienda/...`). Soporta modalidades de
gastronomía (presupuesto, entrega, retiro) e integración con el módulo de ventas.

```powershell
cd tienda_online
npm install
npm run dev       # desarrollo (Vite)
npm run build     # producción -> dist/ (servido por el backend Flask)
```

---

## Testing

```powershell
# Entorno de tests (Windows)
.\scripts\setup_test_env.ps1

# Backend + build frontend
.\scripts\run_tests.ps1

# Solo backend, o un subset
.\scripts\run_tests.ps1 -SkipFrontend
.\scripts\run_tests.ps1 test_gastronomia_cocina.py -q

# O directamente
npm test
```

`conftest.py` usa SQLite aislada en memoria y desactiva IA/WhatsApp reales.

---

## Reglas de desarrollo

Ver [`AGENTS.md`](AGENTS.md). Resumen:

1. **Aislamiento:** `tienda_online/` es un frontend separado; no invadir el backoffice.
2. **Clean code:** ningún archivo > **600 líneas**. Dividir en componentes/hooks/services.
3. **Reutilizar antes de duplicar:** buscar implementación existente.
4. **Despliegue:** una instancia por cliente, sin infra multi-tenant compartida.
5. **Compatibilidad:** nuevos campos en modelos con `default` o que admitan `NULL`.
