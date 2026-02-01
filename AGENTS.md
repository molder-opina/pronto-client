# Development Principles

- **Reuse before Creation**: Before implementing a new function, always verify if a similar one already exists. If it exists, reuse, extend, or parameterize it.
- **Import Conventions**: **Always check `src/shared/` first.** If a service, model, or utility exists in shared, import it from there. Do not duplicate logic in app-specific folders.
- **Modularization**: If a new function must be created, design it to be modular and reusable across the project. For shell scripts, extract reusable logic into `bin/lib/` libraries.
- **Shell Script Limits**: Maintain scripts below 300 lines. If they grow larger, modularize them using the shared helpers in `bin/lib/`.
- **Documentation**: All new reusable modules and significant shared functions must be documented in this file for future reference.

## Frontend Modules

### Notifications Module (TypeScript) (`notifications.ts`)

Centralized module for handling visual notifications across the application. Located at `src/shared/static/js/src/modules/notifications.ts`.

**Usage:**

```typescript
import { showNewOrderNotification, notifyAction } from '../notifications';

// Show a visual notification for a new order
showNewOrderNotification('Mesa 5 - Orden #123');

// Show a toast notification for an action
notifyAction(feedbackElement, 'Acción completada');
```

**Functions:**

- `showNewOrderNotification(message: string, duration?: number)`: Displays a custom-styled notification (with bell icon and animation) at the top-right of the screen. Auto-closes after `duration` (default 3000ms).
- `notifyAction(feedbackEl: HTMLElement | null, message: string)`: Uses the global `showToast` if available, otherwise updates the text content of the provided `feedbackEl`. Use this for user feedback after actions (e.g., "Order accepted").

### Shared Vanilla JS Modules

These modules are located in `src/shared/static/js/` and synchronized to `clients_app` and `employees_app`.

#### NotificationManager (`notifications.js`)

Handles real-time notifications via Server-Sent Events (SSE).

**Key Methods:**

- `connect()`: Establishes connection to the SSE stream.
- `on(eventType, callback)`: Registers a listener for a specific event type.
- `off(eventType, callback)`: Removes a listener.
- `showUINotification(data)`: Displays a visual notification toast.
- `reconnect()`: Handles automatic reconnection with exponential backoff.

#### KeyboardShortcutsManager (`keyboard-shortcuts.js`)

A generic, configurable keyboard shortcuts system.

**Key Methods:**

- `register(combo, options)`: Registers a new shortcut. `combo` e.g., 'ctrl+k', 'shift+?'.
- `unregister(combo)`: Removes a shortcut.
- `setContext(context)`: Switches the active shortcut context (default: 'global').
- `showHelp()`: Displays a generated modal with all registered shortcuts (Default: `Ctrl+?` or `Alt+Shift+H`).

#### Pagination & Search (`pagination.js`)

Generic managers for handling list pagination, text search, and filtering.

**Key Classes:**

- `PaginationManager`: Handles page numbers, next/prev, items per page selector, and localStorage persistence.
- `SearchFilterManager`: Handles text search with debouncing.
- `FilterManager`: Handles checkbox and radio button filter state.

#### GlobalLoading (`loading.js`)

Centralized loading overlay controller that automatically hooks into `fetch` calls.

#### ProntoRealtime (`realtime.js`)

Lightweight polling-based realtime event system.

## System Libraries

### Backend (Python)

**Core Framework:**

- `Flask`: Microframework web application.
- `Flask-Cors`: Handling Cross-Origin Resource Sharing (CORS).
- `Flask-WTF`: Simple integration of Flask and WTForms.

**Database & Storage:**

- `SQLAlchemy`: SQL Toolkit and Object Relational Mapper (ORM).
- `psycopg2-binary`: PostgreSQL adapter for Python.
- `redis`: Redis client for caching and session storage.
- `supabase`: Client for Supabase services.

**Security & Validation:**

- `cryptography`: Cryptographic recipes and primitives.
- `pydantic`: Data validation using Python type hints.
- `email-validator`: Robust email syntax validation.

**Utilities & External Services:**

- `requests`: Elegant HTTP library.
- `openai`: OpenAI API client.
- `Pillow`: Python Imaging Library (fork).
- `qrcode[pil]`: QR Code image generation.
- `python-dotenv`: Read key-value pairs from .env file.
- `python-json-logger`: JSON log formatter.

### Frontend (Node.js/Vue)

**Core & Build:**

- `Vue.js` (v3): Progressive JavaScript Framework.
- `Vite`: Next generation frontend tooling.
- `TypeScript`: Strongly typed programming language.

**Styling & UI:**

- `TailwindCSS`: Utility-first CSS framework.
- `PostCSS`: Tool for transforming CSS with JavaScript.
- `Autoprefixer`: Parse CSS and add vendor prefixes.
- `Lucide`: Beautiful & consistent icon toolkit.

**Testing:**

- `Vitest`: Blazing fast unit test framework.
- `Playwright`: End-to-end testing for modern web apps.

### Development & Quality Assurance

**Code Quality:**

- `Ruff`: Extremely fast Python linter and formatter.
- `Black`: The uncompromising Python code formatter.
- `MyPy`: Optional static typing for Python.
- `ESLint`: Pluggable JavaScript linter.
- `Prettier`: Opinionated code formatter.

**Security Analysis:**

- `Bandit`: Security linter for Python.
- `Safety`: Checks installed dependencies for known security vulnerabilities.

**Testing (Backend):**

- `Pytest`: Mature full-featured Python testing tool.
- `ChromaDB`: Vector database for AI/ML embeddings (Development).

## Application Overview

**Name:** Pronto Restaurant Management System (`pronto-app`)

**Core Technologies:**

- **Backend:** Python 3.11+, Flask, SQLAlchemy, PostgreSQL, Redis
- **Frontend:** Vue.js 3, Vite, TailwindCSS, Vanilla JS (Legacy Modules)
- **Infrastructure:** Docker, Docker Compose, Nginx

**Container Services:**
The application is composed of the following Docker services:

1.  `redis` (`redis:7-alpine`): In-memory data structure store, used as a database, cache, and message broker.
2.  `postgres` (`postgres:13-alpine`): Primary relational database.
3.  `client` (`pronto-client`): Customer-facing web application (Flask). Serves the digital menu and ordering system.
4.  `employee` (`pronto-employee`): Staff management dashboard (Flask). Handles orders, kitchen display system (KDS), and administration.
5.  `static` (`pronto-static`): Nginx server for serving static content (images, assets).
6.  `api` (`pronto-api`): Dedicated API service for external integrations and mobile apps (Flask).

## Architecture & Security

### JWT Authentication (Stateless)

The system uses **JWT (JSON Web Tokens)** for stateless authentication for employee applications.

**Core Components:**

- **`src/shared/jwt_service.py`** - Token generation, validation, and utilities
- **`src/shared/jwt_middleware.py`** - Middleware, decorators, and scope guard
- **`src/employees_app/decorators.py`** - Application-level decorators

**Token Types:**

1. **Access Token** (24 hours default)
   - Contains: employee_id, name, email, role, additional_roles, active_scope
   - Used for API authentication
   - Stored in HTTP-only cookie or Authorization header

2. **Refresh Token** (7 days default)
   - Contains: employee_id only
   - Used to obtain new access tokens
   - Stored in HTTP-only cookie

**Available Decorators:**

```python
from shared.jwt_middleware import jwt_required, scope_required, role_required, admin_required
from employees_app.decorators import login_required, web_login_required

# API routes (returns JSON)
@jwt_required  # Requires valid JWT
@scope_required("waiter")  # Requires specific scope
@role_required(["waiter", "cashier"])  # Requires one of these roles
@admin_required  # Requires admin or super_admin role

# Web routes (redirects to login)
@web_login_required  # Redirects if not authenticated
@web_admin_required  # Redirects if not admin
@web_role_required(["waiter"])  # Redirects if wrong role
```

**Usage Examples:**

```python
# Get current user info
from shared.jwt_middleware import get_current_user, get_employee_id, get_employee_role

user = get_current_user()  # Full JWT payload
employee_id = get_employee_id()  # Just the ID
role = get_employee_role()  # Just the role
```

**Scope Guard (Perimeter Architecture):**

The system uses JWT-based scope isolation to prevent scope confusion attacks:

- **Routes:** `/waiter/api/*`, `/chef/api/*`, `/cashier/api/*`, `/admin/api/*`, `/system/api/*`
- **Validation:** Middleware validates that `jwt.active_scope` matches the URL scope
- **Enforcement:** Automatic via `apply_jwt_scope_guard(app)` in app initialization

**Security Features:**

- ✅ **Stateless** - No server-side session storage for employees
- ✅ **HTTP-only cookies** - Protected from XSS
- ✅ **Secure flag** - HTTPS in production
- ✅ **SameSite=Lax** - CSRF protection
- ✅ **Token expiration** - Access: 24h, Refresh: 7 days
- ✅ **Scope isolation** - Prevents scope confusion
- ✅ **Role validation** - Granular access control
- ✅ **Rate limiting** - Login: 5/min, Refresh: 10/min

**CRITICAL: No Flask Session for Employee Auth**

⚠️ **Flask session MUST NOT be used for employee authentication**

- **NEVER use `from flask import session` for employee auth data**
- **NEVER use `session.get("employee_id")`** - Use `get_employee_id()` instead
- **NEVER use `session.get("employee_role")`** - Use `get_employee_role()` instead
- **NEVER use `session.get("active_scope")`** - Use `get_active_scope()` instead
- **NEVER use `session.clear()`** in logout - Delete cookies instead

**Correct patterns:**

```python
# ✅ CORRECT: Use JWT helpers
from shared.jwt_middleware import get_current_user, get_employee_id

employee_id = get_employee_id()
user = get_current_user()
employee_role = user.get("employee_role")

# ✅ CORRECT: Delete cookies in logout
response.delete_cookie("access_token", path="/")
response.delete_cookie("refresh_token", path="/")

# ❌ WRONG: Flask session for auth
from flask import session
employee_id = session.get("employee_id")  # DON'T DO THIS
session.clear()  # DON'T DO THIS (except for flash messages cleanup if needed)
```

**Flask session may ONLY be used for:**

- SQLAlchemy database sessions (`db_session.get(Model, id)`)
- Client-facing web sessions (`session.get("customer_id")` in `clients_app`)
- Flash messages (in web routes only, not API)

**Validation:**

The pre-commit developer agent checks for:

- `session.get("employee")` patterns - ERROR
- `session.get("active_scope")` patterns - ERROR
- `from flask import session` in employee routes - WARNING

**Configuration:**

```bash
# config/secrets.env
SECRET_KEY=<your-secret-key>  # Used for JWT signing

# config/general.env
JWT_ACCESS_TOKEN_EXPIRES_HOURS=24
JWT_REFRESH_TOKEN_EXPIRES_DAYS=7
```

**Security Validators:**
The project enforces security checks via `pre-commit` and `make` commands:

- `make security-scan`: Runs Bandit, Semgrep, and Gitleaks.
- `make check-all`: Runs all linters and security checks.

## Testing & Validation

**Main Entry Point:**

- `./run-all-tests.sh`: Runs all tests (Backend, Frontend, E2E).

**Specific Commands:**

- **Backend:** `pytest` (Unit/Integration)
- **Frontend:** `npm run test` (Vitest for Vue components)
- **E2E:** `npm run test` in `e2e-tests/` (Playwright)
- **Security:** `make security-scan`

**Workflow:**

1.  Run `./run-all-tests.sh` to detect regressions.
2.  Write a reproduction test for bugs.
3.  Verify fixes with the specific test.

**⭐ Quality Mandate: No Test, No Feature**

Every new functionality MUST be accompanied by its corresponding tests:

- **Console-specific tests:** Add tests to the Vitest suite of the modified console (e.g., `src/employees_app/static/js/src/components/__tests__/`).
- **Integration/Backend tests:** Add tests to the `tests/` directory (Unit or Integration).

## Directory Structure Reference

**Multi-Tier "Employees" Directory Pattern:**

El proyecto utiliza un patrón de nombres compartido entre directorios con diferentes propósitos. Esto es por diseño y NO es un error de duplicación:

| Directorio                                     | Propósito                      | Contenido                                              |
| ---------------------------------------------- | ------------------------------ | ------------------------------------------------------ |
| `src/employees_app/`                         | **Aplicación Flask principal** | Rutas, templates, configuración de la app de empleados |
| `src/shared/static/js/dist/employees`        | **Assets JS compartidos**      | Versión compilada de módulos frontend compartidos      |
| `src/employees_app/static/js/dist/employees` | **Assets JS locales**          | Versión compilada para uso interno de la app           |
| `e2e-tests/tests/employees`                    | **Tests E2E**                  | Suite de pruebas end-to-end para empleados             |

**Explicación del Flujo:**

1. Los módulos frontend en `src/shared/static/js/src/modules/` se compilan
2. El output se guarda en `src/shared/static/js/dist/` (compartido entre apps)
3. Cada app (employees, clients) puede tener su propia versión local en `static/js/dist/`
4. E2E tests acceden al sistema como si fueran usuarios reales

**Importante:** Cuando se trabaje con código de empleados, siempre verificar el contexto:

- `src/employees_app/` - Código fuente y templates de la aplicación
- `src/shared/` - Código compartido que debe reutilizarse primero
- NO crear versiones duplicadas de servicios en `src/employees_app/`

---

- `src/shared/`: **Central Hub**. Services, Models, Permissions, Config. **Check here first.**
- `src/clients_app/`: Customer-facing Flask app.
- `src/employees_app/`: Employee dashboard Flask app.
- `src/api_app/`: External API.
- `tests/`: Backend pytest suite.
- `e2e-tests/`: Playwright suite.
- `docs/`: Detailed architectural documentation.
- `scripts/`: Utility scripts for maintenance, migrations, and QA tasks.
- `scripts/maintenance/`: Database maintenance, cleanup, and fix scripts.
- `scripts/qa/`: Testing and QA automation scripts.
- `docs/qa/`: QA reports and testing documentation.

## Utility Scripts (`scripts/`)

The `scripts/` directory contains utility scripts for database maintenance, migrations, testing, and QA automation. **Use these scripts for development tasks, not `bin/` scripts which are for production deployment.**

### Directory Structure

```
scripts/
├── *.py                    # General utility scripts (migrations, seeding, etc.)
├── *.sh                    # Shell scripts for automation
├── *.sql                   # SQL migration scripts
├── maintenance/            # Database maintenance and fix scripts
│   ├── check_*.py         # Diagnostic scripts
│   ├── clean_*.py         # Cleanup operations
│   ├── fix_*.py           # Data fix scripts
│   ├── list_*.py          # List/query scripts
│   └── *.sh               # Maintenance shell scripts
├── qa/                     # QA and testing scripts
│   ├── qa_*.py            # QA automation scripts
│   ├── test_*.py          # Test scripts
│   ├── test_*.sh          # Test shell scripts
│   └── run_tests.py       # Test runner
└── sql/                    # SQL migration scripts
    └── *.sql              # Database migrations
```

### When to Use Each Directory

| Directory              | Use When...                                            | Examples                                             |
| ---------------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| `scripts/`             | Running migrations, seeding data, or general utilities | `python scripts/apply_partial_delivery_migration.py` |
| `scripts/maintenance/` | Fixing data issues, checking DB state, cleanup tasks   | `python scripts/maintenance/clean_db.py`             |
| `scripts/qa/`          | Running tests, QA automation, verification scripts     | `python scripts/qa/qa_full_cycle.py`                 |
| `scripts/sql/`         | Applying database schema changes                       | `psql < scripts/sql/*.sql`                           |

### Common Commands

```bash
# Database migrations
python scripts/apply_*.py
python scripts/migrate_*.py

# Maintenance tasks
python scripts/maintenance/check_db.py
python scripts/maintenance/clean_db.py
python scripts/maintenance/fix_*.py

# QA and testing
python scripts/qa/qa_full_cycle.py
python scripts/qa/test_*.py
bash scripts/qa/test_*.sh

# Seeding data
python scripts/seed_*.py
```

## Scripts & Operations

The `bin/` directory contains essential scripts for managing the application lifecycle, testing, and maintenance. **Always use these scripts instead of raw `docker compose` commands** to ensure environment variables and contexts are handled correctly.

### Lifecycle & Deployment

- **`bin/up.sh`**: Starts the full application stack in normal mode.
- **`bin/down.sh`**: Stops and removes all containers, networks, and orphans.
- **`bin/rebuild.sh`**: **Primary update script.** Refactored modular script (~300 lines) that orchestrates builds using shared libraries.
- **`bin/build.sh`**: Only builds the Docker images (does not start them).
- **`bin/restart.sh`**: Restarts containers without rebuilding.
- **`bin/status.sh`**: Displays the status of running containers and lists accessible URLs.
- **`bin/validate-seed.sh`**: Automated database health check and seed data provisioning.

### Modularization & Shell Libraries

To maintain readability and prevent scripts from becoming monoliths, large operations are modularized into shared libraries.

**Shared Libraries (`bin/lib/`):**

- `bin/lib/build_helpers.sh`: Common build and dependency preparation logic (TypeScript bundles, Python wheels).
- `bin/lib/cleanup_helpers.sh`: Robust container and image removal functions.
- `bin/lib/static_helpers.sh`: Static content synchronization and placeholder management for Nginx.
- `bin/lib/docker_runtime.sh`: Docker/Podman runtime detection and CLI abstraction.
- `bin/lib/stack_helpers.sh`: Stack-level management and service discovery.

**Python Utilities (`bin/python/`):**
Complex logic better handled by Python is stored in this subdirectory and called by bash wrappers.

- `bin/python/validate_and_seed.py`: Centralized database validation and automated seed data provisioning.

**Maintenance & Legacy (`bin/maintenance/`):**
One-time migration scripts (e.g., `migrate-supabase-to-postgres.py`) or infrequently used tasks are isolated here to keep the main `bin/` directory clean.

### Testing & Quality Assurance

- **`bin/test-all.sh`**: Runs the complete integration test suite.

### Static Content Management

El proyecto utiliza un servidor centralizado de contenido estático que sirve assets compartidos (CSS, imágenes, íconos, branding) para todas las aplicaciones (clientes y empleados).

#### Arquitectura de Contenido Estático

El proyecto utiliza un servidor centralizado de contenido estático que sirve assets compartidos para todas las aplicaciones (clientes y empleados).

**Dos contextos diferentes:**

| Contexto               | Propósito                                   | Variables                      |
| ---------------------- | ------------------------------------------- | ------------------------------ |
| **Host/Navegador**     | Acceso desde el navegador del usuario       | `PRONTO_STATIC_CONTAINER_HOST` |
| **Contenedores/Linux** | Comunicación entre apps y servidor estático | `NGINX_HOST`, `NGINX_PORT`     |

**URLs por entorno:**

| Entorno   | Host/Navegador                       | Contenedores/Linux    |
| --------- | ------------------------------------ | --------------------- |
| **macOS** | `http://localhost:9088` (pod Docker) | `http://static:80`    |
| **Linux** | `http://IP:9088` (nginx externo)     | `http://localhost:80` |

#### Configuración en `config/general.env`

```bash
# ═══════════════════════════════════════════════════════════════════════════════
# Static Content Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# NGINX_HOST: Host del servidor nginx (contenedor Docker o localhost en Linux)
# NGINX_PORT: Puerto del servidor nginx (80 interno, 9088 externo)
NGINX_HOST=static
NGINX_PORT=80

# PRONTO_STATIC_CONTAINER_HOST: URL para acceso desde el navegador/host
# macOS: http://localhost:9088
# Linux: http://IP_O_HOSTNAME:9088
PRONTO_STATIC_CONTAINER_HOST=http://localhost:9088
```

#### Variables de Entorno en Aplicaciones

Las aplicaciones reciben ambas configuraciones vía `docker-compose.yml`:

```yaml
environment:
  # Para comunicación entre contenedores (Linux)
  NGINX_HOST: '${NGINX_HOST:-static}'
  NGINX_PORT: '${NGINX_PORT:-80}'
  # Para acceso desde navegador (macOS)
  PRONTO_STATIC_CONTAINER_HOST: '${PRONTO_STATIC_CONTAINER_HOST:-http://localhost:9088}'
```

La variable `STATIC_HOST_URL` se mantiene para compatibilidad pero está deprecada.
/assets/
├── css/ # Hojas de estilo compartidas
│ └── notifications.css # Estilos de notificaciones
├── pronto/ # Assets generales del sistema
└── cafeteria-\*/ # Branding por slug de restaurante
├── icons/ # Íconos y logos
├── banners/ # Banners promocionales
└── products/ # Imágenes de productos

````

#### Configuración por Entorno

**macOS (Desarrollo):**
- **Servidor:** Pod Docker `pronto-static`
- **URL:** `http://localhost:9088`
- **Configuración:** Automática vía `docker-compose.yml`
- **Requisito:** El contenedor `pronto-static` DEBE estar ejecutándose

**Linux (Producción):**
- **Servidor:** Nginx instalado en el sistema
- **URL:** `http://HOSTNAME_O_IP:9088` (configurable)
- **Configuración:** Manual (nginx.conf)
- **Requisito:** Nginx DEBE estar configurado para servir en puerto 9088

**Docker (Red Interna):**
- **Servidor:** Servicio interno `static`
- **URL:** `http://static:80`
- **Uso:** Solo para comunicación entre contenedores

#### Configuración en `config/general.env`

```bash
# ═══════════════════════════════════════════════════════════════════════════════
# Static Content Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# PRONTO_STATIC_CONTAINER_HOST: URL para acceso desde el navegador/host
# macOS: http://localhost:9088 (pod static)
# Linux: http://IP_O_HOSTNAME:9088 (nginx externo)
PRONTO_STATIC_CONTAINER_HOST=http://localhost:9088

# STATIC_ASSETS_PATH: Ruta URL base para assets
STATIC_ASSETS_PATH=/assets

# STATIC_ASSETS_ROOT: Ruta física del servidor para assets
STATIC_ASSETS_ROOT=/var/www/pronto-static/assets

# NGINX_HOST/NGINX_PORT: Para comunicación entre contenedores (Linux)
NGINX_HOST=static
NGINX_PORT=80

# IMPORTANTE:
#   - En macOS: El pod 'pronto-static' DEBE estar ejecutándose
#   - En Linux: Nginx DEBE estar configurado para servir en puerto 9088
#   - Los aplicativos usan PRONTO_STATIC_CONTAINER_HOST para URLs del navegador
#   - Usar variables cortas en templates: assets_css_clients, assets_js_employees, etc.
```

#### Variables de Entorno en Aplicaciones

Todas las aplicaciones (client, employee, api) reciben `PRONTO_STATIC_CONTAINER_HOST` vía `docker-compose.yml`:

```yaml
environment:
  PRONTO_STATIC_CONTAINER_HOST: '${PRONTO_STATIC_CONTAINER_HOST:-http://localhost:9088}'
```

#### Scripts de Gestión

**`bin/static-host-detector.sh`** - Detecta y configura la URL del servidor estático:

```bash
./bin/static-host-detector.sh detect          # Mostrar URL detectada
./bin/static-host-detector.sh export          # Exportar PRONTO_STATIC_CONTAINER_HOST
./bin/static-host-detector.sh status          # Estado de servicios
./bin/static-host-detector.sh update-config   # Actualizar config/general.env
```

**`bin/sync-static-content.sh`** - Sincroniza contenido estático:

```bash
./bin/sync-static-content.sh all      # Compilar, copiar y subir (default)
./bin/sync-static-content.sh compile  # Solo compilar JS bundles
./bin/sync-static-content.sh copy     # Solo copiar assets a static_content/
./bin/sync-static-content.sh upload   # Solo subir a servidor estático
./bin/sync-static-content.sh status   # Mostrar estado del contenido
```

#### Validación Automática

Los scripts `bin/up.sh` y `bin/rebuild.sh` incluyen validación automática del servidor estático:

```bash
# Función: validate_static_pod (en bin/lib/static_helpers.sh)
# Verifica:
#   1. En macOS: Que el contenedor 'pronto-static' esté ejecutándose
#   2. En Linux: Que nginx esté configurado y sirviendo en puerto NGINX_PORT
#   3. Que el contenido estático sea accesible vía HTTP
#
# Retorna advertencias pero NO bloquea el despliegue
```

**Ejemplo de salida:**

```
╔══════════════════════════════════════════════════════════════════════╗
║          Validación de Servidor de Contenido Estático               ║
╚══════════════════════════════════════════════════════════════════════╝

>> Sistema: macOS (desarrollo)
>> Verificando pod static: pronto-static
   ✅ Contenedor 'pronto-static' está ejecutándose
>> Verificando accesibilidad: http://localhost:9088
   ✅ Servidor estático accesible (HTTP 200)
   ✅ Contenido estático accesible (assets/css/notifications.css)

✅ Validación completada
   URL configurada: http://localhost:9088
```

#### Checklist de Validación

Al iniciar o reconstruir aplicativos, el sistema valida:

- ✅ **Existencia del pod/servicio static** (advertencia si no existe)
- ✅ **Accesibilidad HTTP** del servidor estático
- ✅ **Disponibilidad de archivos** de prueba (notifications.css)
- ⚠️ **No bloquea el inicio** si falla (solo advertencias)

#### Troubleshooting

**Problema:** Contenido estático no se carga (404 en /assets/)

**Solución macOS:**

```bash
# Verificar que el contenedor static esté ejecutándose
docker ps | grep pronto-static

# Si no está ejecutándose, iniciarlo
docker-compose up -d static

# Verificar accesibilidad
curl http://localhost:9088/assets/css/notifications.css
```

**Solución Linux:**

```bash
# Verificar que nginx esté ejecutándose
sudo systemctl status nginx

# Verificar configuración de nginx
sudo nginx -t

# Reiniciar nginx si es necesario
sudo systemctl restart nginx

# Verificar accesibilidad
curl http://localhost:9088/assets/css/notifications.css
```

**Problema:** Variables de entorno no se actualizan

**Solución:**

```bash
# Reconstruir aplicativos para aplicar nuevas variables
bin/rebuild.sh client employee

# Verificar variables dentro del contenedor
docker exec pronto-client printenv | grep STATIC
docker exec pronto-employee printenv | grep STATIC
```

#### Uso en Código

**Backend (Python):**

```python
from flask import current_app

# Usar funciones helper del módulo branding.py
from employees_app.routes.api.branding import get_assets_css, get_assets_js, get_assets_images

# Obtener URLs de assets
css_url = get_assets_css()           # http://localhost:9088/assets/css
js_url = get_assets_js()             # http://localhost:9088/assets/js
images_url = get_assets_images()     # http://localhost:9088/assets/pronto

# Construir URL completa
logo_url = f"{get_assets_images()}/{restaurant_slug}/icons/logo.png"
```

**Frontend (JavaScript/TypeScript):**

```typescript
// Usar configuración global con variables cortas
const assetsCss = window.APP_CONFIG?.assets_css_clients || '';
const assetsJs = window.APP_CONFIG?.assets_js_clients || '';

// Construir URL de imagen
const imageUrl = `${assetsJs}/${productId}.js`;
```

**Templates (Jinja2):**

```html
<!-- ✅ CORRECTO: Usar variables cortas -->
<link rel="stylesheet" href="{{ assets_css_clients }}/menu.css" />
<script src="{{ assets_js_clients }}/menu.js"></script>

<!-- ❌ INCORRECTO: No hardcodear URLs -->
<link rel="stylesheet" href="{{ pronto_static_container_host }}/assets/css/clients/menu.css" />
```

#### Variables de Assets Disponibles

| Variable               | Descripción           | Ejemplo                                      |
| ---------------------- | --------------------- | -------------------------------------------- |
| `assets_css`           | CSS base compartido   | `http://localhost:9088/assets/css`           |
| `assets_css_clients`   | CSS de clients        | `http://localhost:9088/assets/css/clients`   |
| `assets_css_employees` | CSS de employees      | `http://localhost:9088/assets/css/employees` |
| `assets_js`            | JS base compartido    | `http://localhost:9088/assets/js`            |
| `assets_js_clients`    | JS de clients         | `http://localhost:9088/assets/js/clients`    |
| `assets_js_employees`  | JS de employees       | `http://localhost:9088/assets/js/employees`  |
| `assets_images`        | Imágenes de productos | `http://localhost:9088/assets/pronto`        |

#### Regla de Validación (Pre-commit)

El agente `developer.sh` valida que:

- ✅ Los templates usen variables cortas (`assets_css_clients`, etc.)
- ✅ El código Python use funciones helper (`get_assets_css()`, etc.)
- ❌ No haya URLs hardcodeadas de contenido estático

```bash
# Ejemplo de validación:
# ❌ ERROR: href="{{ pronto_static_container_host }}/assets/css/clients/menu.css"
# ✅ CORRECTO: href="{{ assets_css_clients }}/menu.css"
```

#### Reglas Importantes

1. **Usar variables cortas para assets** - NO hardcodear URLs de contenido estático
   - Templates: Usar `{{ assets_css_clients }}`, `{{ assets_js_employees }}`, etc.
   - Python: Usar funciones helper `get_assets_css()`, `get_assets_js()`, etc.
2. **Usar `PRONTO_STATIC_CONTAINER_HOST`** solo si es necesario (acceso desde navegador)
3. **Usar `NGINX_HOST` y `NGINX_PORT`** para comunicación entre contenedores/apps
4. **En macOS:** El pod `pronto-static` DEBE estar ejecutándose antes de iniciar aplicativos
5. **En Linux:** Nginx DEBE estar configurado para servir en puerto 9088
6. **Los scripts de bin/** validan automáticamente pero NO bloquean el inicio
7. **Contenido estático** se sincroniza automáticamente en Linux con `sync_static_content()`
8. **Variables de entorno** se pasan a contenedores vía `docker-compose.yml`

### Database & Maintenance

- **`bin/cleanup-old-sessions.sh`**: Removes old or invalid session data.
- **`bin/postgres-*.sh`**: Suite of scripts for managing the local PostgreSQL container.

### Initialization & Provisioning

- **`bin/init/init.sh`**: **Master initialization script.** Orchestrates the entire setup process.

### Typical Workflows

1.  **Start fresh:** `bin/down.sh && bin/up.sh --seed`
2.  **Apply code changes:** `bin/rebuild.sh`
3.  **Apply config change:** `bin/restart.sh`
4.  **Verify health:** `bin/status.sh && bin/test-all.sh`

## Git Workflow

- **Pre-Commit Review:** Before executing `git add`, always review the changes broadly (`git status`, `git diff`) to understand what is being staged.
- **Documentation Sync:** If the changes introduce new patterns, scripts, modules, or libraries, check if this file needs to be updated.

## Database Safety Guidelines

### ⚠️ CRITICAL: Do Not Delete Test Data Directly

**Never execute DELETE, TRUNCATE, or DROP commands directly on the database.**

The database contains essential test data:

- `pronto_menu_categories` (12 categories)
- `pronto_menu_items` (94 products)
- `pronto_employees` (10 employees)

**If data is deleted:**

1. Run the seeding script inside the employee container:

   ```bash
   docker exec pronto-employee python3 -c "
   import sys
   sys.path.insert(0, '/opt/pronto/build')
   from shared.config import load_config
   from shared.db import get_session, init_engine
   from shared.services.seed import load_seed_data

   config = load_config('employee')
   init_engine(config)
   with get_session() as session:
       load_seed_data(session)
       session.commit()
       print('Seed completed successfully')
   "
   ```

**To prevent accidental deletion:**

- Use `bin/cleanup-old-sessions.sh` for session cleanup only (it preserves menu data)
- Use `scripts/maintenance/clean_db.py` for specific table cleanup (it only removes orders, sessions, notifications)
- Never run `DELETE FROM menu_categories` or `DELETE FROM menu_items`
- The `bin/mac/rebuild.sh` script with `--keep-sessions` flag preserves all data
- **Direct database deletion requires explicit confirmation** - always use `--confirm` or `--yes` flags when available, and double-check the query before execution

## Specialized Agents (Pre-commit Hooks)

The project includes a "Review Committee" of specialized automated agents that verify code quality before every commit. These run as local pre-commit hooks:

- **👨‍💻 Developer Agent (`bin/agents/developer.sh`):**
  - Checks for `TODO`/`FIXME` markers (warning).
  - Ensures no `print()` statements remain in production Python code (error).
  - **Valida uso de variables cortas para assets estáticos** (error):
    - Templates deben usar `{{ assets_css_clients }}`, `{{ assets_js_employees }}`, etc.
    - Python debe usar funciones helper `get_assets_css()`, `get_assets_js()`, etc.

- **👩‍🎨 Designer Agent (`bin/agents/designer.sh`):**
  - Detects unoptimized images (>1MB).
  - Checks for excessive use of `!important` in CSS.
  - Verifies basic accessibility (missing `alt` tags).

- **🗄️ DB Specialist Agent (`bin/agents/db_specialist.sh`):**
  - Validates migration file naming conventions.
  - Warns about destructive SQL operations (`DROP TABLE`).
  - Ensures `models.py` exists.

- **🛡️ Sysadmin Agent (`bin/agents/sysadmin.sh`):**
  - Prevents committing `.env` files.
  - Checks Dockerfiles for `USER` definition (non-root best practice).
  - Validates shell script headers (`shebang`).

- **🧪 QA/Tester Agent (`bin/agents/qa_tester.sh`):**
  - Prevents focused tests (`.only`, `fit`, `fdescribe`) that skip the full suite.
  - Ensures test integrity.

- **✍️ Scribe Agent (`bin/agents/scribe.sh`):**
  - Checks for `TODO` markers in documentation.
  - Verifies existence of critical files.

- **🐳 Container Specialist Agent (`bin/agents/container_specialist.sh`):**
  - Warns about `latest` tags in `docker-compose.yml`.
  - Checks for `apt-get` cleanup in Dockerfiles.
  - Detects multiple `CMD`/`ENTRYPOINT` instructions.
  - Verifies presence of `HEALTHCHECK` in compose config.

- **🍽️ Business Expert Agent (`bin/agents/business_expert.sh`):**
  - Validates presence of key domain terms.
  - Ensures currency formatting functions are utilized.
  - Verifies existence of critical business configuration services.

- **🤵 Waiter Agent (`bin/agents/waiter_agent.sh`):**
  - Validates templates and modules related to the waiter console.
  - Checks for table assignment logic and board functionality.

- **👨‍💼 Admin Agent (`bin/agents/admin_agent.sh`):**
  - Validates administrative modules and business configuration.
  - Ensures permission systems are correctly referenced.

- **💰 Cashier Agent (`bin/agents/cashier_agent.sh`):**
  - Validates payment modules and cashier views.
  - Checks for integration with payment providers.

- **👑 Super Admin Agent (`bin/agents/super_admin_agent.sh`):**
  - Validates system integrity and global security middleware.
  - Ensures ScopeGuard and core app protections are active.

- **👨‍🍳 Chef Agent (`bin/agents/chef_agent.sh`):**
  - Validates the kitchen display system and chef views.
  - Ensures correct order state transitions for the kitchen.

- **🔍 Audit Agent (`bin/agents/audit_agent.sh`):**
  - Performs multi-model code review using 3 AI models (Claude, Minimax, GLM4).
  - Provides independent security, performance, and maintainability assessments.
  - Generates comprehensive audit reports with consensus recommendations.
  - Usage: `./bin/agents/audit_agent.sh [--all-files | file1 file2 ...]`
  - Reports saved to: `.audit_reports/audit_YYYYMMDD_HHMMSS.md`

**To run agents manually:**

```bash
./bin/agents/developer.sh
# or via pre-commit
pre-commit run agent-developer --all-files

# Run multi-model audit
./bin/agents/audit_agent.sh --all-files
```

---

## Agent Review Strategies

These strategies should be used by AI agents when reviewing code or performing large-scale refactoring tasks.

### 1. Analysis Before Action

**Always analyze before modifying:**

- ✅ **Grep first, edit later:** Use `grep -r` to find all references before making changes
- ✅ **Distinguish context:** Understand the meaning of similar patterns in different contexts
- ✅ **Check imports:** Verify what's actually being imported and used
- ✅ **Create inventory:** List all files that need changes before starting

**Example patterns to distinguish:**

```bash
# Flask session vs SQLAlchemy session
session.get("employee_id")  # Flask session - HTTP session
session.get(Employee, id)   # SQLAlchemy session - Database query

# Employee auth vs Client auth
session.get("employee_id")  # Employee authentication
session.get("customer_id")  # Client authentication
```

### 2. Create Automation Tools

**Build scripts for repetitive tasks:**

- ✅ **Refactoring scripts:** Automate find-and-replace with validation
- ✅ **Update scripts:** Consolidate multiple similar scripts into one
- ✅ **Verification scripts:** Check that changes were applied correctly

**Script characteristics:**

- Safe by default (dry-run mode)
- Validate before modifying
- Provide clear output
- Handle errors gracefully

### 3. Document Everything

**Create comprehensive documentation:**

- ✅ **Implementation plan:** Before making changes (what will be done)
- ✅ **Progress tracker:** During the work (what's being done)
- ✅ **Final report:** After completion (what was done)
- ✅ **Update this file:** Reflect architectural changes

**Documentation structure:**

- Clear objective
- Scope and affected files
- Step-by-step plan
- Verification strategy
- Rollback plan

### 4. Incremental Verification

**Verify at each step:**

- ✅ **Test after each file:** Don't wait until the end
- ✅ **Use grep to verify:** Check that old patterns are gone
- ✅ **Run automated tests:** Catch regressions early
- ✅ **Manual spot checks:** Verify critical paths work

**Verification commands:**

```bash
# Check for remaining old patterns
grep -r "old_pattern" src/ --include="*.py" | grep -v __pycache__

# Count successful migrations
grep -r "new_pattern" src/ --include="*.py" | wc -l

# Run tests
pytest tests/ -v
```

### 5. Handle Legacy Code Carefully

**Before deleting legacy code:**

- ✅ **Create backup:** Compress and archive, don't just delete
- ✅ **Check for imports:** Ensure nothing references it
- ✅ **Document decision:** Why it was removed
- ✅ **Keep for 30 days:** In case rollback is needed

**Backup process:**

```bash
# Create backup before deletion
tar -czf archive/backup_$(date +%Y%m%d).tar.gz path/to/legacy/

# Verify no imports
grep -r "legacy_module" src/ --include="*.py"

# Only then delete
rm -rf path/to/legacy/
```

### 6. Distinguish Between Similar Patterns

**Be careful with similar-looking code:**

- ⚠️ **Context matters:** Same syntax, different meaning
- ⚠️ **Check imports:** What's being imported determines behavior
- ⚠️ **Verify usage:** How the code is actually used

**Common patterns to distinguish:**

```python
# Flask session (HTTP session)
from flask import session
user_id = session.get("employee_id")

# SQLAlchemy session (Database session)
from shared.db import get_session
with get_session() as session:
    employee = session.get(Employee, id)

# Client session (keep as-is)
customer_id = session.get("customer_id")
```

### 7. Refactoring Checklist Template

Use this checklist for any large refactoring:

```markdown
## Phase 1: Analysis

- [ ] Identify all files affected
- [ ] Distinguish different contexts
- [ ] Create inventory of changes needed
- [ ] Estimate scope and complexity

## Phase 2: Planning

- [ ] Create implementation plan
- [ ] Get approval if needed
- [ ] Identify automation opportunities
- [ ] Plan verification strategy

## Phase 3: Execution

- [ ] Create automation tools if needed
- [ ] Refactor incrementally (file by file or module by module)
- [ ] Verify after each change
- [ ] Update documentation as you go

## Phase 4: Verification

- [ ] Run automated tests
- [ ] Manual verification of critical paths
- [ ] Check for remaining old patterns
- [ ] Update this file

## Phase 5: Cleanup

- [ ] Remove legacy code (with backup)
- [ ] Clean up temporary files
- [ ] Archive old documentation
- [ ] Create final report
```

### 8. Statistics to Track

**Measure your refactoring:**

- Files modified
- Lines changed
- References removed
- Code duplicated eliminated
- Legacy code removed (MB)
- Tools created
- Documentation generated

**Purpose:**

- Quantify impact
- Justify effort
- Learn from metrics
- Improve future estimates

### 9. Common Pitfalls to Avoid

**Anti-patterns:**

- ❌ **Changing without understanding:** Always analyze first
- ❌ **Modifying all at once:** Incremental changes are safer
- ❌ **Skipping documentation:** Future you will thank present you
- ❌ **Deleting without backup:** Always create archives
- ❌ **Ignoring context:** Same code, different meaning
- ❌ **No verification:** Test early and often

**Best practices:**

- ✅ **Understand before changing**
- ✅ **Change incrementally**
- ✅ **Document continuously**
- ✅ **Backup before deleting**
- ✅ **Consider context**
- ✅ **Verify constantly**

### 10. When to Ask for Help

**Ask the user when:**

- Unclear requirements or ambiguous specifications
- Multiple valid approaches exist
- Breaking changes are necessary
- Architectural decisions are needed
- Security implications are unclear
- Business logic is involved

**Don't ask when:**

- Following established patterns
- Fixing obvious bugs
- Applying documented best practices
- Refactoring for clarity
- Adding tests
- Updating documentation

---

## Chrome MCP Integration

The project includes Chrome MCP (Model Context Protocol) for browser automation and AI model integration.

### Installation

Chrome MCP is already installed as a dependency:

```bash
npm install @eddym06/custom-chrome-mcp --save
```

### Configuration

1. **Set up API Keys**:

   ```bash
   cp .mcp/.env.example .mcp/.env
   # Edit .mcp/.env with your API keys
   ```

2. **Available AI Providers**:
   | Provider | Variable | Models |
   |----------|----------|--------|
   | OpenAI | `OPENAI_API_KEY` | GPT-4, GPT-3.5 |
   | Anthropic | `ANTHROPIC_API_KEY` | Claude |
   | MiniMax | `MINIMAX_API_KEY` | Chinese LLM |
   | GLM | `GLM_API_KEY` | ChatGLM |
   | DeepSeek | `DEEPSEEK_API_KEY` | DeepSeek V3 |

### Usage

**Start the MCP Server**:

```bash
.mcp/start-chrome-mcp.sh

# With custom settings
CHROME_PATH=/usr/bin/chromium HEADLESS=true .mcp/start-chrome-mcp.sh
```

**Available Tools** (90+):

- `navigate`, `click`, `type` - Element interaction
- `screenshot` - Visual capture
- `evaluate` - JavaScript execution
- `network_capture` - Request monitoring
- `accessibility_test` - A11y validation

### Environment Variables

| Variable      | Description            | Default           |
| ------------- | ---------------------- | ----------------- |
| `CHROME_PATH` | Chrome executable path | Platform-specific |
| `HEADLESS`    | Run without UI         | `false`           |
| `MCP_PORT`    | Server port            | `3000`            |

---

**Last Updated:** 2026-01-31
**Maintainers:** Development Team
````
