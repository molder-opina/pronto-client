# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pronto is a restaurant management system with customer ordering and employee dashboard applications. It uses Python Flask for the backend, TypeScript/Vue.js for the frontend, PostgreSQL for data, and Redis for sessions/real-time features.

## Common Commands

### macOS Development

```bash
bin/mac/start.sh                    # Start all services
bin/mac/start.sh client employee    # Start specific services
bin/mac/start.sh --seed             # Start with seed data
bin/mac/rebuild.sh employee         # Rebuild and restart a service
bin/mac/stop.sh                     # Stop services
bin/mac/status.sh                   # Check service status
bin/mac/logs.sh client              # View logs
```

### Linux/Production

```bash
bin/up.sh                           # Start services
bin/up.sh --seed                    # Start with seed data
bin/rebuild.sh employee             # Rebuild specific service
bin/down.sh                         # Stop services
```

### Frontend Build

```bash
npm run build:employees             # Build employees app bundle
npm run build:clients               # Build clients app bundle
PRONTO_TARGET=employees npm run dev # Dev server with HMR
PRONTO_TARGET=clients npm run dev   # Dev server with HMR
```

### Testing

```bash
npm run lint                        # ESLint check
npm run test                        # Vitest unit tests
npm run test:e2e                    # Playwright E2E tests
npm run test:e2e:headed             # E2E with visible browser
npm run test:qa                     # Run QA test suite
```

### Database

```bash
bin/postgres-up.sh                  # Start PostgreSQL container
bin/postgres-psql.sh                # Interactive psql shell
bin/apply_migration.sh              # Apply Alembic migrations
```

## Architecture

### Application Structure

```
src/
├── clients_app/          # Customer-facing app (menu, cart, checkout)
├── employees_app/        # Employee dashboard (orders, kitchen, payments)
│   ├── routes/           # Flask blueprints by role
│   │   ├── admin/        # Admin routes
│   │   ├── waiter/       # Waiter routes
│   │   ├── chef/         # Chef routes
│   │   ├── cashier/      # Cashier routes
│   │   ├── api/          # API endpoints
│   │   └── system/       # System admin routes
│   └── templates/        # Jinja2 templates
│       └── includes/     # Modular template components
├── api_app/              # Unified API gateway
├── shared/               # Shared code across ALL apps
│   ├── models.py         # SQLAlchemy ORM models
│   ├── db.py             # Database connection
│   ├── config.py         # Configuration loading
│   ├── permissions.py    # Centralized permissions
│   ├── multi_scope_session.py  # Session management by role
│   ├── services/         # Business logic (30+ services)
│   └── auth/             # Authentication service
└── static_content/       # Compiled static assets for nginx
```

### Frontend Build Targets (vite.config.ts)

The `PRONTO_TARGET` env variable selects the build target:

- `employees`: Builds from `src/employees_app/static/js/src/` → `dist/employees/`
- `clients`: Builds from `src/clients_app/static/js/src/` → `dist/clients/`

Entrypoints are in `entrypoints/` subdirectories (e.g., `dashboard.ts`, `menu.ts`).

### Multi-Scope Session System

Employee roles (waiter, chef, cashier, admin) use isolated session cookies via `src/shared/multi_scope_session.py`. Each role gets its own cookie path and name to prevent session conflicts.

### Service Ports

| Service  | Port |
| -------- | ---- |
| client   | 6080 |
| employee | 6081 |
| api      | 6082 |
| static   | 9088 |
| postgres | 5432 |
| redis    | 6379 |

## Key Patterns

### Services (src/shared/services/)

**All services are centralized in `shared/services/`.** Always import from there:

```python
# ✅ CORRECT:
from shared.services.menu_service import list_menu
from shared.services.order_service import get_dashboard_metrics
from shared.services.employee_service import get_employee_by_id

# ❌ WRONG:
from employees_app.services.menu_service import list_menu
```

Key services: `employee_service`, `menu_service`, `order_service`, `role_service`, `price_service`, `analytics_service`, `payment_providers/`, `notification_service`, `business_config_service`.

### Permissions (src/shared/permissions.py)

```python
from shared.permissions import Permission, get_user_permissions, has_permission
```

Permission levels: `ORDERS_VIEW`, `KITCHEN_VIEW`, `PAYMENTS_PROCESS`, `MENU_EDIT`, `CONFIG_EDIT`, `EMPLOYEES_MANAGE_PERMISSIONS`.

### TypeScript Modules

Frontend code is in `static/js/src/modules/`:

- `menu-flow.ts` - Menu orchestration
- `cart-manager.ts` - Cart state with localStorage persistence
- `modal-manager.ts` - Item details and modifier selection
- `checkout-handler.ts` - Payment flow
- `kitchen-board.ts` - Kitchen display system
- `waiter-board.ts` - Waiter order management

### Dashboard Templates

Role-specific templates in `employees_app/templates/`:

```python
template_map = {
    "waiter": "dashboard_waiter.html",
    "chef": "dashboard_chef.html",
    "cashier": "dashboard_cashier.html",
    "admin": "dashboard_admin.html",
}
```

Modular includes in `templates/includes/`: `_dashboard_base.html`, `_waiter_section.html`, `_chef_section.html`, `_cashier_section.html`, `_admin_sections.html`, `_dashboard_scripts.html`.

### Configuration

Two-tier config:

1. Environment files: `config/general.env`, `config/secrets.env`
2. Runtime database config: `BusinessConfigService`

## Static Content Workflow

Compiled JS/CSS is synced to nginx container via `bin/sync-static-content.sh`:

```bash
bin/sync-static-content.sh          # Compile + copy + upload to container
bin/sync-static-content.sh compile  # Only compile bundles
bin/sync-static-content.sh status   # Show sync status
```

## E2E Tests

Playwright tests in `tests/e2e/`. Config in `playwright.config.ts` defines projects for `employees` (port 6081) and `clients` (port 6080).

Run single test:

```bash
npx playwright test tests/e2e/qa-complete.spec.ts --headed
```
