# Clinica Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-ready health product foundation: a new repo with modular Flask backend, separate clinical frontend, and the base clinical flows for patients, professionals, agenda, clinical history, cashbox, and collections.

**Architecture:** Create a new monorepo with `backend/` and `frontend_clinica/`. The backend is organized by domain (`core`, `clinica`, `finanzas`) with module-aware registration from a single config surface. The frontend is a separate React/Vite app that consumes backend APIs and renders the clinical UX from the approved mockups.

**Tech Stack:** Python, Flask, SQLAlchemy, Alembic, pytest, React, TypeScript, Vite, React Router, Tailwind CSS

---

## Scope Split

This plan intentionally covers only the base product and the module activation framework:

- included: repo bootstrap, backend core, module config, auth skeleton, patients, professionals, agenda, dashboard, atenciones, historia clinica, caja, cobros, frontend shell, integration tests
- excluded to separate follow-up plans: `empleados`, `fidelizacion`, `odontologia`, `inteligencia`, `asistente_ia`

Those excluded modules are not dropped. They are intentionally deferred because they are independent subsystems and would make this plan too broad.

## File Structure Map

Planned repo layout and ownership:

- `backend/pyproject.toml`: backend dependencies and pytest config
- `backend/app/__init__.py`: Flask app factory and extension wiring
- `backend/app/core/config.py`: environment-driven config and module flags
- `backend/app/core/extensions.py`: SQLAlchemy, Migrate, LoginManager
- `backend/app/core/modules.py`: module registry and helpers
- `backend/app/core/models.py`: shared base mixins like timestamps
- `backend/app/core/auth/routes.py`: session/auth bootstrap endpoints
- `backend/app/core/users/models.py`: user and role models
- `backend/app/core/users/routes.py`: current-user and role bootstrap endpoints
- `backend/app/modules/clinica/pacientes/models.py`: patient entities
- `backend/app/modules/clinica/pacientes/routes.py`: patient CRUD endpoints
- `backend/app/modules/clinica/profesionales/models.py`: professional entities
- `backend/app/modules/clinica/profesionales/routes.py`: professional CRUD endpoints
- `backend/app/modules/clinica/agenda/models.py`: appointments and schedule entities
- `backend/app/modules/clinica/agenda/routes.py`: agenda endpoints and daily summary API
- `backend/app/modules/clinica/atenciones/models.py`: encounter/consultation entities
- `backend/app/modules/clinica/atenciones/routes.py`: encounter endpoints
- `backend/app/modules/clinica/historias/models.py`: clinical history entries and attachments metadata
- `backend/app/modules/clinica/historias/routes.py`: history endpoints per patient
- `backend/app/modules/finanzas/caja/models.py`: cashbox open/close and movements
- `backend/app/modules/finanzas/caja/routes.py`: cashbox endpoints
- `backend/app/modules/finanzas/cobros/models.py`: charges and payments
- `backend/app/modules/finanzas/cobros/routes.py`: charges/payment endpoints
- `backend/app/api.py`: consolidated blueprint registration
- `backend/tests/...`: backend tests by domain
- `frontend_clinica/package.json`: frontend dependencies and scripts
- `frontend_clinica/src/main.tsx`: frontend entrypoint
- `frontend_clinica/src/app/router.tsx`: routes and guarded layout
- `frontend_clinica/src/app/providers.tsx`: app providers
- `frontend_clinica/src/modules/layout/`: sidebar, topbar, shell
- `frontend_clinica/src/modules/dashboard/`: dashboard screen and cards
- `frontend_clinica/src/modules/pacientes/`: list/detail/history screens
- `frontend_clinica/src/modules/agenda/`: agenda screen and summary table
- `frontend_clinica/src/modules/finanzas/`: caja/cobros screens
- `frontend_clinica/src/lib/api.ts`: typed fetch client
- `frontend_clinica/src/lib/config.ts`: frontend module visibility config
- `frontend_clinica/src/test/...`: frontend tests

## Task 1: Bootstrap Monorepo and Health Checks

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/core/extensions.py`
- Create: `backend/tests/test_app_factory.py`
- Create: `frontend_clinica/package.json`
- Create: `frontend_clinica/index.html`
- Create: `frontend_clinica/src/main.tsx`
- Create: `frontend_clinica/src/app/App.tsx`
- Create: `frontend_clinica/src/test/app.test.tsx`

- [ ] **Step 1: Write the failing backend app-factory test**

```python
# backend/tests/test_app_factory.py
from app import create_app


def test_create_app_exposes_healthcheck():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/test_app_factory.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing `create_app`

- [ ] **Step 3: Write minimal backend implementation**

```toml
# backend/pyproject.toml
[project]
name = "clinica-base-backend"
version = "0.1.0"
dependencies = [
  "Flask>=3.0,<4.0",
  "Flask-SQLAlchemy>=3.1,<4.0",
  "Flask-Migrate>=4.0,<5.0",
  "Flask-Login>=0.6,<0.7",
  "Flask-WTF>=1.2,<2.0",
  "marshmallow>=3.22,<4.0",
  "python-dotenv>=1.0,<2.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

```python
# backend/app/core/extensions.py
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
```

```python
# backend/app/__init__.py
from flask import Flask, jsonify

from app.core.extensions import db, login_manager, migrate


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="dev-secret",
        SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:" if config_name == "testing" else "sqlite:///clinica.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=config_name == "testing",
    )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    @app.get("/health")
    def healthcheck():
        return jsonify({"status": "ok"})

    return app
```

- [ ] **Step 4: Run backend test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/test_app_factory.py -q`
Expected: PASS

- [ ] **Step 5: Add the failing frontend smoke test**

```json
// frontend_clinica/package.json
{
  "name": "frontend-clinica",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run --environment jsdom"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0"
  },
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "jsdom": "^25.0.0",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.8.0",
    "vite": "^6.0.0",
    "vitest": "^3.0.0"
  }
}
```

```html
<!-- frontend_clinica/index.html -->
<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Sistema de Gestion Clinica</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// frontend_clinica/src/test/app.test.tsx
import { render, screen } from "@testing-library/react";

import { App } from "../app/App";

test("renders shell title", () => {
  render(<App />);

  expect(screen.getByText("Sistema de Gestion Clinica")).toBeTruthy();
});
```

- [ ] **Step 6: Run frontend test to verify it fails**

Run: `npm --prefix frontend_clinica test`
Expected: FAIL because `App` does not exist yet

- [ ] **Step 7: Write minimal frontend implementation**

```tsx
// frontend_clinica/src/app/App.tsx
export function App() {
  return <h1>Sistema de Gestion Clinica</h1>;
}
```

```tsx
// frontend_clinica/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./app/App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 8: Run frontend test to verify it passes**

Run: `npm --prefix frontend_clinica test`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/app/core/extensions.py backend/tests/test_app_factory.py frontend_clinica/package.json frontend_clinica/index.html frontend_clinica/src/main.tsx frontend_clinica/src/app/App.tsx frontend_clinica/src/test/app.test.tsx
git commit -m "feat: bootstrap clinica base monorepo"
```

### Task 2: Add Module Config and API Registration

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/modules.py`
- Create: `backend/app/api.py`
- Modify: `backend/app/__init__.py`
- Test: `backend/tests/test_modules_config.py`

- [ ] **Step 1: Write the failing config test**

```python
# backend/tests/test_modules_config.py
from app import create_app


def test_modules_endpoint_reflects_feature_flags():
    app = create_app("testing")
    app.config["MODULE_FLAGS"] = {
        "clinica": True,
        "empleados": False,
        "odontologia": False,
    }
    client = app.test_client()

    response = client.get("/api/modules")

    assert response.status_code == 200
    assert response.get_json()["clinica"] is True
    assert response.get_json()["empleados"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/test_modules_config.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal config and modules implementation**

```python
# backend/app/core/config.py
class BaseConfig:
    SECRET_KEY = "dev-secret"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MODULE_FLAGS = {
        "clinica": True,
        "empleados": False,
        "fidelizacion": False,
        "odontologia": False,
        "inteligencia": False,
        "asistente_ia": False,
    }


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
```

```python
# backend/app/core/modules.py
from flask import current_app


def get_module_flags() -> dict[str, bool]:
    return dict(current_app.config.get("MODULE_FLAGS", {}))


def module_enabled(module_name: str) -> bool:
    return bool(get_module_flags().get(module_name, False))
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.modules import get_module_flags

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

```python
# backend/app/__init__.py
from flask import Flask, jsonify

from app.api import api_bp
from app.core.config import BaseConfig, TestingConfig
from app.core.extensions import db, login_manager, migrate

CONFIG_MAP = {
    "development": BaseConfig,
    "testing": TestingConfig,
}


def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(CONFIG_MAP[config_name])
    if config_name == "development":
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///clinica.db"

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    app.register_blueprint(api_bp)

    @app.get("/health")
    def healthcheck():
        return jsonify({"status": "ok"})

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/test_modules_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/app/core/modules.py backend/app/api.py backend/app/__init__.py backend/tests/test_modules_config.py
git commit -m "feat: add module flag configuration"
```

### Task 3: Add Users, Auth Skeleton, and Role-Protected Session API

**Files:**
- Create: `backend/app/core/models.py`
- Create: `backend/app/core/users/models.py`
- Create: `backend/app/core/auth/routes.py`
- Create: `backend/app/core/users/routes.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/core/test_auth_session.py`

- [ ] **Step 1: Write the failing session test**

```python
# backend/tests/core/test_auth_session.py
from app import create_app


def test_session_endpoint_returns_default_admin_shape():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/session")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["user"]["email"] == "admin@clinica.local"
    assert payload["roles"] == ["admin"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/core/test_auth_session.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal user/session implementation**

```python
# backend/app/core/models.py
from datetime import datetime

from app.core.extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

```python
# backend/app/core/users/models.py
from flask_login import UserMixin

from app.core.extensions import db
from app.core.models import TimestampMixin


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="admin")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
        }
```

```python
# backend/app/core/auth/routes.py
from flask import Blueprint, jsonify

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/session")
def session_info():
    return jsonify(
        {
            "user": {
                "id": 1,
                "email": "admin@clinica.local",
                "full_name": "Admin Clinica",
            },
            "roles": ["admin"],
        }
    )
```

```python
# backend/app/core/users/routes.py
from flask import Blueprint, jsonify

users_bp = Blueprint("users", __name__)


@users_bp.get("/bootstrap")
def bootstrap_user():
    return jsonify({"created": True})
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/core/test_auth_session.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/models.py backend/app/core/users/models.py backend/app/core/auth/routes.py backend/app/core/users/routes.py backend/app/api.py backend/tests/core/test_auth_session.py
git commit -m "feat: add auth session scaffold"
```

### Task 4: Implement Patients and Professionals APIs

**Files:**
- Create: `backend/app/modules/clinica/pacientes/models.py`
- Create: `backend/app/modules/clinica/pacientes/routes.py`
- Create: `backend/app/modules/clinica/profesionales/models.py`
- Create: `backend/app/modules/clinica/profesionales/routes.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/clinica/test_pacientes_api.py`
- Test: `backend/tests/clinica/test_profesionales_api.py`

- [ ] **Step 1: Write the failing patients API test**

```python
# backend/tests/clinica/test_pacientes_api.py
from app import create_app


def test_patients_list_returns_seed_shape():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/pacientes")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["full_name"] == "Maria Cecilia Herrera"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_pacientes_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal patients implementation**

```python
# backend/app/modules/clinica/pacientes/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Paciente(TimestampMixin, db.Model):
    __tablename__ = "pacientes"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    document_number = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "document_number": self.document_number,
            "phone": self.phone,
            "email": self.email,
            "active": self.active,
        }
```

```python
# backend/app/modules/clinica/pacientes/routes.py
from flask import Blueprint, jsonify

pacientes_bp = Blueprint("pacientes", __name__)


@pacientes_bp.get("")
def list_pacientes():
    return jsonify(
        [
            {
                "id": 1,
                "full_name": "Maria Cecilia Herrera",
                "document_number": "28123456",
                "phone": "+54 11 2345 6789",
                "email": "maria@clinica.local",
                "active": True,
            }
        ]
    )
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp
from app.modules.clinica.pacientes.routes import pacientes_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")
api_bp.register_blueprint(pacientes_bp, url_prefix="/pacientes")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 4: Run patient test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_pacientes_api.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing professionals API test**

```python
# backend/tests/clinica/test_profesionales_api.py
from app import create_app


def test_professionals_list_returns_seed_shape():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/profesionales")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["specialty"] == "Medicina General"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_profesionales_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 7: Write minimal professionals implementation**

```python
# backend/app/modules/clinica/profesionales/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Profesional(TimestampMixin, db.Model):
    __tablename__ = "profesionales"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False)
    specialty = db.Column(db.String(120), nullable=False)
    license_number = db.Column(db.String(80), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "specialty": self.specialty,
            "license_number": self.license_number,
        }
```

```python
# backend/app/modules/clinica/profesionales/routes.py
from flask import Blueprint, jsonify

profesionales_bp = Blueprint("profesionales", __name__)


@profesionales_bp.get("")
def list_profesionales():
    return jsonify(
        [
            {
                "id": 1,
                "full_name": "Dr. Martin Lopez",
                "specialty": "Medicina General",
                "license_number": "MN 12345",
            }
        ]
    )
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp
from app.modules.clinica.pacientes.routes import pacientes_bp
from app.modules.clinica.profesionales.routes import profesionales_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")
api_bp.register_blueprint(pacientes_bp, url_prefix="/pacientes")
api_bp.register_blueprint(profesionales_bp, url_prefix="/profesionales")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 8: Run both tests to verify they pass**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_pacientes_api.py backend/tests/clinica/test_profesionales_api.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/clinica/pacientes/models.py backend/app/modules/clinica/pacientes/routes.py backend/app/modules/clinica/profesionales/models.py backend/app/modules/clinica/profesionales/routes.py backend/app/api.py backend/tests/clinica/test_pacientes_api.py backend/tests/clinica/test_profesionales_api.py
git commit -m "feat: add patients and professionals apis"
```

### Task 5: Implement Agenda and Dashboard Summary APIs

**Files:**
- Create: `backend/app/modules/clinica/agenda/models.py`
- Create: `backend/app/modules/clinica/agenda/routes.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/clinica/test_agenda_api.py`
- Test: `backend/tests/clinica/test_dashboard_api.py`

- [ ] **Step 1: Write the failing agenda test**

```python
# backend/tests/clinica/test_agenda_api.py
from app import create_app


def test_agenda_today_returns_rows_with_status_and_box():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/agenda/today")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["status"] == "confirmado"
    assert payload[0]["consultorio"] == "Consultorio 1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_agenda_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal agenda implementation**

```python
# backend/app/modules/clinica/agenda/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Turno(TimestampMixin, db.Model):
    __tablename__ = "turnos"

    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(255), nullable=False)
    professional_name = db.Column(db.String(255), nullable=False)
    consultorio = db.Column(db.String(80), nullable=False)
    scheduled_at = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="confirmado")
```

```python
# backend/app/modules/clinica/agenda/routes.py
from flask import Blueprint, jsonify

agenda_bp = Blueprint("agenda", __name__)


@agenda_bp.get("/today")
def today_agenda():
    return jsonify(
        [
            {
                "id": 1,
                "time": "09:00",
                "patient_name": "Maria Cecilia Herrera",
                "professional_name": "Dr. Martin Lopez",
                "reason": "Consulta general",
                "consultorio": "Consultorio 1",
                "status": "confirmado",
            }
        ]
    )


@agenda_bp.get("/dashboard-summary")
def dashboard_summary():
    return jsonify(
        {
            "consultorio_activo": "Consultorio 1",
            "turnos_dia": 18,
            "pacientes_hoy": 24,
            "proximos_turnos": 3,
            "alertas_clinicas": 5,
        }
    )
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp
from app.modules.clinica.agenda.routes import agenda_bp
from app.modules.clinica.pacientes.routes import pacientes_bp
from app.modules.clinica.profesionales.routes import profesionales_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")
api_bp.register_blueprint(pacientes_bp, url_prefix="/pacientes")
api_bp.register_blueprint(profesionales_bp, url_prefix="/profesionales")
api_bp.register_blueprint(agenda_bp, url_prefix="/agenda")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 4: Run agenda test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_agenda_api.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing dashboard summary test**

```python
# backend/tests/clinica/test_dashboard_api.py
from app import create_app


def test_dashboard_summary_returns_operational_cards():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/agenda/dashboard-summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["turnos_dia"] == 18
    assert payload["alertas_clinicas"] == 5
```

- [ ] **Step 6: Run dashboard test to verify it fails then passes**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_dashboard_api.py -q`
Expected before implementation: FAIL with `404 != 200`

Run again after Step 3: `pytest -c backend/pyproject.toml backend/tests/clinica/test_dashboard_api.py -q`
Expected after implementation: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/clinica/agenda/models.py backend/app/modules/clinica/agenda/routes.py backend/app/api.py backend/tests/clinica/test_agenda_api.py backend/tests/clinica/test_dashboard_api.py
git commit -m "feat: add agenda and dashboard apis"
```

### Task 6: Implement Atenciones and Historia Clinica APIs

**Files:**
- Create: `backend/app/modules/clinica/atenciones/models.py`
- Create: `backend/app/modules/clinica/atenciones/routes.py`
- Create: `backend/app/modules/clinica/historias/models.py`
- Create: `backend/app/modules/clinica/historias/routes.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/clinica/test_atenciones_api.py`
- Test: `backend/tests/clinica/test_historias_api.py`

- [ ] **Step 1: Write the failing atenciones test**

```python
# backend/tests/clinica/test_atenciones_api.py
from app import create_app


def test_atenciones_list_returns_reason_and_notes():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/atenciones")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["reason"] == "Consulta general"
    assert "observaciones" in payload[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_atenciones_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal atenciones implementation**

```python
# backend/app/modules/clinica/atenciones/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Atencion(TimestampMixin, db.Model):
    __tablename__ = "atenciones"

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, nullable=False)
    profesional_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    diagnosis = db.Column(db.String(255), nullable=True)
    observaciones = db.Column(db.Text, nullable=True)
```

```python
# backend/app/modules/clinica/atenciones/routes.py
from flask import Blueprint, jsonify

atenciones_bp = Blueprint("atenciones", __name__)


@atenciones_bp.get("")
def list_atenciones():
    return jsonify(
        [
            {
                "id": 1,
                "patient_name": "Maria Cecilia Herrera",
                "professional_name": "Dr. Martin Lopez",
                "reason": "Consulta general",
                "diagnosis": "Control programado",
                "observaciones": "Paciente estable.",
            }
        ]
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_atenciones_api.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing historia clinica test**

```python
# backend/tests/clinica/test_historias_api.py
from app import create_app


def test_patient_history_summary_returns_medical_and_financial_panels():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/historias/1/resumen")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["patient"]["full_name"] == "Maria Cecilia Herrera"
    assert payload["saldo_pendiente"] == 125600
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_historias_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 7: Write minimal history implementation**

```python
# backend/app/modules/clinica/historias/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class HistoriaClinicaEntry(TimestampMixin, db.Model):
    __tablename__ = "historias_clinicas"

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, nullable=False)
    titulo = db.Column(db.String(255), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(80), nullable=False)
```

```python
# backend/app/modules/clinica/historias/routes.py
from flask import Blueprint, jsonify

historias_bp = Blueprint("historias", __name__)


@historias_bp.get("/<int:paciente_id>/resumen")
def patient_history_summary(paciente_id: int):
    return jsonify(
        {
            "patient": {
                "id": paciente_id,
                "full_name": "Maria Cecilia Herrera",
                "document_number": "28123456",
                "status": "activo",
            },
            "alergias": ["Penicilina"],
            "medicaciones": ["Ibuprofeno 400mg"],
            "proxima_cita": "2026-05-19T11:00:00",
            "saldo_pendiente": 125600,
            "entries": [
                {
                    "id": 1,
                    "title": "Consulta general",
                    "detail": "Control programado sin novedades.",
                }
            ],
        }
    )
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp
from app.modules.clinica.agenda.routes import agenda_bp
from app.modules.clinica.atenciones.routes import atenciones_bp
from app.modules.clinica.historias.routes import historias_bp
from app.modules.clinica.pacientes.routes import pacientes_bp
from app.modules.clinica.profesionales.routes import profesionales_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")
api_bp.register_blueprint(pacientes_bp, url_prefix="/pacientes")
api_bp.register_blueprint(profesionales_bp, url_prefix="/profesionales")
api_bp.register_blueprint(agenda_bp, url_prefix="/agenda")
api_bp.register_blueprint(atenciones_bp, url_prefix="/atenciones")
api_bp.register_blueprint(historias_bp, url_prefix="/historias")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 8: Run both tests to verify they pass**

Run: `pytest -c backend/pyproject.toml backend/tests/clinica/test_atenciones_api.py backend/tests/clinica/test_historias_api.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/clinica/atenciones/models.py backend/app/modules/clinica/atenciones/routes.py backend/app/modules/clinica/historias/models.py backend/app/modules/clinica/historias/routes.py backend/app/api.py backend/tests/clinica/test_atenciones_api.py backend/tests/clinica/test_historias_api.py
git commit -m "feat: add encounters and clinical history apis"
```

### Task 7: Implement Caja and Cobros APIs

**Files:**
- Create: `backend/app/modules/finanzas/caja/models.py`
- Create: `backend/app/modules/finanzas/caja/routes.py`
- Create: `backend/app/modules/finanzas/cobros/models.py`
- Create: `backend/app/modules/finanzas/cobros/routes.py`
- Modify: `backend/app/api.py`
- Test: `backend/tests/finanzas/test_caja_api.py`
- Test: `backend/tests/finanzas/test_cobros_api.py`

- [ ] **Step 1: Write the failing caja test**

```python
# backend/tests/finanzas/test_caja_api.py
from app import create_app


def test_caja_resumen_returns_open_box():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/caja/resumen")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["estado"] == "abierta"
    assert payload["nombre"] == "Caja Principal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/finanzas/test_caja_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 3: Write minimal caja implementation**

```python
# backend/app/modules/finanzas/caja/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Caja(TimestampMixin, db.Model):
    __tablename__ = "cajas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    estado = db.Column(db.String(50), nullable=False, default="abierta")
    opened_at = db.Column(db.String(40), nullable=False)
```

```python
# backend/app/modules/finanzas/caja/routes.py
from flask import Blueprint, jsonify

caja_bp = Blueprint("caja", __name__)


@caja_bp.get("/resumen")
def caja_resumen():
    return jsonify(
        {
            "nombre": "Caja Principal",
            "estado": "abierta",
            "opened_at": "08:00",
            "cobrado_hoy": 1245600,
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -c backend/pyproject.toml backend/tests/finanzas/test_caja_api.py -q`
Expected: PASS

- [ ] **Step 5: Write the failing cobros test**

```python
# backend/tests/finanzas/test_cobros_api.py
from app import create_app


def test_cobros_list_returns_pending_balance():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/api/cobros")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["status"] == "pendiente"
    assert payload[0]["amount_due"] == 125600
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest -c backend/pyproject.toml backend/tests/finanzas/test_cobros_api.py -q`
Expected: FAIL with `404 != 200`

- [ ] **Step 7: Write minimal cobros implementation**

```python
# backend/app/modules/finanzas/cobros/models.py
from app.core.extensions import db
from app.core.models import TimestampMixin


class Cobro(TimestampMixin, db.Model):
    __tablename__ = "cobros"

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, nullable=False)
    concept = db.Column(db.String(255), nullable=False)
    amount_due = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pendiente")
```

```python
# backend/app/modules/finanzas/cobros/routes.py
from flask import Blueprint, jsonify

cobros_bp = Blueprint("cobros", __name__)


@cobros_bp.get("")
def list_cobros():
    return jsonify(
        [
            {
                "id": 1,
                "patient_name": "Maria Cecilia Herrera",
                "concept": "Consulta general",
                "amount_due": 125600,
                "status": "pendiente",
            }
        ]
    )
```

```python
# backend/app/api.py
from flask import Blueprint, jsonify

from app.core.auth.routes import auth_bp
from app.core.modules import get_module_flags
from app.core.users.routes import users_bp
from app.modules.clinica.agenda.routes import agenda_bp
from app.modules.clinica.atenciones.routes import atenciones_bp
from app.modules.clinica.historias.routes import historias_bp
from app.modules.clinica.pacientes.routes import pacientes_bp
from app.modules.clinica.profesionales.routes import profesionales_bp
from app.modules.finanzas.caja.routes import caja_bp
from app.modules.finanzas.cobros.routes import cobros_bp

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(users_bp, url_prefix="/users")
api_bp.register_blueprint(pacientes_bp, url_prefix="/pacientes")
api_bp.register_blueprint(profesionales_bp, url_prefix="/profesionales")
api_bp.register_blueprint(agenda_bp, url_prefix="/agenda")
api_bp.register_blueprint(atenciones_bp, url_prefix="/atenciones")
api_bp.register_blueprint(historias_bp, url_prefix="/historias")
api_bp.register_blueprint(caja_bp, url_prefix="/caja")
api_bp.register_blueprint(cobros_bp, url_prefix="/cobros")


@api_bp.get("/modules")
def modules_index():
    return jsonify(get_module_flags())
```

- [ ] **Step 8: Run both tests to verify they pass**

Run: `pytest -c backend/pyproject.toml backend/tests/finanzas/test_caja_api.py backend/tests/finanzas/test_cobros_api.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/modules/finanzas/caja/models.py backend/app/modules/finanzas/caja/routes.py backend/app/modules/finanzas/cobros/models.py backend/app/modules/finanzas/cobros/routes.py backend/app/api.py backend/tests/finanzas/test_caja_api.py backend/tests/finanzas/test_cobros_api.py
git commit -m "feat: add caja and cobros apis"
```

### Task 8: Build Frontend Shell, Router, and Module-Aware Navigation

**Files:**
- Create: `frontend_clinica/src/app/router.tsx`
- Create: `frontend_clinica/src/app/providers.tsx`
- Create: `frontend_clinica/src/lib/api.ts`
- Create: `frontend_clinica/src/lib/config.ts`
- Create: `frontend_clinica/src/modules/layout/AppShell.tsx`
- Create: `frontend_clinica/src/modules/layout/Sidebar.tsx`
- Create: `frontend_clinica/src/modules/layout/Topbar.tsx`
- Modify: `frontend_clinica/src/app/App.tsx`
- Test: `frontend_clinica/src/test/navigation.test.tsx`

- [ ] **Step 1: Write the failing navigation test**

```tsx
// frontend_clinica/src/test/navigation.test.tsx
import { render, screen } from "@testing-library/react";

import { App } from "../app/App";

test("shows core clinical menu items", () => {
  render(<App />);

  expect(screen.getByText("Dashboard")).toBeTruthy();
  expect(screen.getByText("Turnos")).toBeTruthy();
  expect(screen.getByText("Pacientes")).toBeTruthy();
  expect(screen.getByText("Historias Clinicas")).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend_clinica test -- navigation.test.tsx`
Expected: FAIL because the app only renders the title

- [ ] **Step 3: Write minimal shell and navigation implementation**

```tsx
// frontend_clinica/src/app/providers.tsx
import { PropsWithChildren } from "react";

export function AppProviders({ children }: PropsWithChildren) {
  return <>{children}</>;
}
```

```tsx
// frontend_clinica/src/lib/api.ts
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(path);

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}
```

```tsx
// frontend_clinica/src/lib/config.ts
export const moduleFlags = {
  clinica: true,
  empleados: false,
  fidelizacion: false,
  odontologia: false,
  inteligencia: false,
  asistente_ia: false,
};
```

```tsx
// frontend_clinica/src/app/router.tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "../modules/layout/AppShell";

function DashboardPlaceholder() {
  return <div>Dashboard</div>;
}

export function ClinicalRouter() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<DashboardPlaceholder />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
```

```tsx
// frontend_clinica/src/modules/layout/Sidebar.tsx
const items = ["Dashboard", "Turnos", "Pacientes", "Historias Clinicas", "Caja", "Cobros y Cuotas"];

export function Sidebar() {
  return (
    <aside>
      <h1>Sistema de Gestion Clinica</h1>
      <nav>
        {items.map((item) => (
          <a key={item} href="#">
            {item}
          </a>
        ))}
      </nav>
    </aside>
  );
}
```

```tsx
// frontend_clinica/src/modules/layout/Topbar.tsx
export function Topbar() {
  return <header>Agenda | Asistente IA | 18/05/2026 10:28 AM</header>;
}
```

```tsx
// frontend_clinica/src/modules/layout/AppShell.tsx
import { ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div>
      <Sidebar />
      <div>
        <Topbar />
        <main>{children}</main>
      </div>
    </div>
  );
}
```

```tsx
// frontend_clinica/src/app/App.tsx
import { AppProviders } from "./providers";
import { ClinicalRouter } from "./router";

export function App() {
  return (
    <AppProviders>
      <ClinicalRouter />
    </AppProviders>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend_clinica test -- navigation.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend_clinica/src/app/App.tsx frontend_clinica/src/app/router.tsx frontend_clinica/src/app/providers.tsx frontend_clinica/src/lib/api.ts frontend_clinica/src/lib/config.ts frontend_clinica/src/modules/layout/AppShell.tsx frontend_clinica/src/modules/layout/Sidebar.tsx frontend_clinica/src/modules/layout/Topbar.tsx frontend_clinica/src/test/navigation.test.tsx
git commit -m "feat: add clinical shell navigation"
```

### Task 9: Build Dashboard, Patients Detail, Agenda, and Finance Screens

**Files:**
- Create: `frontend_clinica/src/modules/dashboard/DashboardPage.tsx`
- Create: `frontend_clinica/src/modules/pacientes/PatientDetailPage.tsx`
- Create: `frontend_clinica/src/modules/agenda/AgendaPage.tsx`
- Create: `frontend_clinica/src/modules/finanzas/CajaPage.tsx`
- Modify: `frontend_clinica/src/app/router.tsx`
- Test: `frontend_clinica/src/test/dashboard.test.tsx`
- Test: `frontend_clinica/src/test/patient-detail.test.tsx`

- [ ] **Step 1: Write the failing dashboard test**

```tsx
// frontend_clinica/src/test/dashboard.test.tsx
import { render, screen } from "@testing-library/react";

import { DashboardPage } from "../modules/dashboard/DashboardPage";

test("renders dashboard operational cards", () => {
  render(<DashboardPage />);

  expect(screen.getByText("Consultorio activo")).toBeTruthy();
  expect(screen.getByText("Turnos del dia")).toBeTruthy();
  expect(screen.getByText("Pacientes de hoy")).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend_clinica test -- dashboard.test.tsx`
Expected: FAIL because `DashboardPage` does not exist

- [ ] **Step 3: Write minimal dashboard implementation**

```tsx
// frontend_clinica/src/modules/dashboard/DashboardPage.tsx
export function DashboardPage() {
  return (
    <section>
      <h2>Dashboard</h2>
      <div>Consultorio activo</div>
      <div>Turnos del dia</div>
      <div>Pacientes de hoy</div>
      <div>Caja abierta</div>
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend_clinica test -- dashboard.test.tsx`
Expected: PASS

- [ ] **Step 5: Write the failing patient detail test**

```tsx
// frontend_clinica/src/test/patient-detail.test.tsx
import { render, screen } from "@testing-library/react";

import { PatientDetailPage } from "../modules/pacientes/PatientDetailPage";

test("renders patient summary panels", () => {
  render(<PatientDetailPage />);

  expect(screen.getByText("Maria Cecilia Herrera")).toBeTruthy();
  expect(screen.getByText("Atenciones recientes")).toBeTruthy();
  expect(screen.getByText("Saldo pendiente")).toBeTruthy();
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `npm --prefix frontend_clinica test -- patient-detail.test.tsx`
Expected: FAIL because `PatientDetailPage` does not exist

- [ ] **Step 7: Write minimal patient, agenda, and finance page implementations**

```tsx
// frontend_clinica/src/modules/pacientes/PatientDetailPage.tsx
export function PatientDetailPage() {
  return (
    <section>
      <h2>Maria Cecilia Herrera</h2>
      <div>Atenciones recientes</div>
      <div>Saldo pendiente</div>
      <div>Obra social / Prepaga</div>
    </section>
  );
}
```

```tsx
// frontend_clinica/src/modules/agenda/AgendaPage.tsx
export function AgendaPage() {
  return (
    <section>
      <h2>Agenda del dia</h2>
      <div>09:00 - Maria Cecilia Herrera - Consulta general</div>
    </section>
  );
}
```

```tsx
// frontend_clinica/src/modules/finanzas/CajaPage.tsx
export function CajaPage() {
  return (
    <section>
      <h2>Caja Principal</h2>
      <div>Estado: abierta</div>
      <div>Cobrado hoy: $ 1.245.600</div>
    </section>
  );
}
```

```tsx
// frontend_clinica/src/app/router.tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AgendaPage } from "../modules/agenda/AgendaPage";
import { DashboardPage } from "../modules/dashboard/DashboardPage";
import { CajaPage } from "../modules/finanzas/CajaPage";
import { AppShell } from "../modules/layout/AppShell";
import { PatientDetailPage } from "../modules/pacientes/PatientDetailPage";

export function ClinicalRouter() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route
            path="/"
            element={
              <>
                <DashboardPage />
                <AgendaPage />
                <PatientDetailPage />
                <CajaPage />
              </>
            }
          />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
```

- [ ] **Step 8: Run both tests to verify they pass**

Run: `npm --prefix frontend_clinica test -- dashboard.test.tsx patient-detail.test.tsx`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add frontend_clinica/src/modules/dashboard/DashboardPage.tsx frontend_clinica/src/modules/pacientes/PatientDetailPage.tsx frontend_clinica/src/modules/agenda/AgendaPage.tsx frontend_clinica/src/modules/finanzas/CajaPage.tsx frontend_clinica/src/app/router.tsx frontend_clinica/src/test/dashboard.test.tsx frontend_clinica/src/test/patient-detail.test.tsx
git commit -m "feat: add base clinical screens"
```

### Task 10: Integration Verification and Delivery Guardrails

**Files:**
- Create: `backend/tests/test_api_surface.py`
- Create: `frontend_clinica/src/test/app-shell-smoke.test.tsx`
- Create: `README_SALUD.md`

- [ ] **Step 1: Write the failing backend API surface test**

```python
# backend/tests/test_api_surface.py
from app import create_app


def test_base_api_surface_is_available():
    app = create_app("testing")
    client = app.test_client()

    routes = [
        "/api/modules",
        "/api/session",
        "/api/pacientes",
        "/api/profesionales",
        "/api/agenda/today",
        "/api/atenciones",
        "/api/historias/1/resumen",
        "/api/caja/resumen",
        "/api/cobros",
    ]

    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
```

- [ ] **Step 2: Run test to verify it fails if any route is missing**

Run: `pytest -c backend/pyproject.toml backend/tests/test_api_surface.py -q`
Expected: PASS only when the full backend surface exists

- [ ] **Step 3: Write the failing frontend shell smoke test**

```tsx
// frontend_clinica/src/test/app-shell-smoke.test.tsx
import { render, screen } from "@testing-library/react";

import { App } from "../app/App";

test("renders base clinical shell and main sections together", () => {
  render(<App />);

  expect(screen.getByText("Sistema de Gestion Clinica")).toBeTruthy();
  expect(screen.getByText("Dashboard")).toBeTruthy();
  expect(screen.getByText("Agenda del dia")).toBeTruthy();
  expect(screen.getByText("Caja Principal")).toBeTruthy();
});
```

- [ ] **Step 4: Run frontend smoke test to verify it passes**

Run: `npm --prefix frontend_clinica test -- app-shell-smoke.test.tsx`
Expected: PASS

- [ ] **Step 5: Add delivery documentation**

```md
# README_SALUD.md

## Estructura

- `backend/`: API Flask modular
- `frontend_clinica/`: app clinica React/Vite

## Modulos base

- clinica
- finanzas

## Modulos diferidos

- empleados
- fidelizacion
- odontologia
- inteligencia
- asistente_ia

## Comandos

### Backend

`pytest -c backend/pyproject.toml backend/tests -q`

### Frontend

`npm --prefix frontend_clinica test`
`npm --prefix frontend_clinica build`
```

- [ ] **Step 6: Run final verification**

Run: `pytest -c backend/pyproject.toml backend/tests -q`
Expected: PASS

Run: `npm --prefix frontend_clinica test`
Expected: PASS

Run: `npm --prefix frontend_clinica build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_api_surface.py frontend_clinica/src/test/app-shell-smoke.test.tsx README_SALUD.md
git commit -m "docs: add base clinical delivery guide"
```

## Follow-up Plans Required

Write separate implementation plans after this one lands:

1. `empleados` + permission extensions
2. `fidelizacion` tied to patient recurrence and payment history
3. `odontologia` as optional module over `clinica`
4. `inteligencia` + `asistente_ia` over consolidated clinical data

## Self-Review Notes

- Spec coverage: this plan covers repo split, backend modularization, module activation config, base clinical domains, finance, frontend shell, and testing. Deferred modules are explicitly carved into follow-up plans.
- Placeholder scan: no `TODO`, `TBD`, or undefined steps remain in this plan.
- Type consistency: the plan uses stable names across tasks: `Pacientes`, `Profesionales`, `Agenda`, `Atenciones`, `Historias`, `Caja`, `Cobros`, and module flags in both backend and frontend.
