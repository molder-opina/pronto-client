# Pronto Architecture Documentation

**Last Updated:** 2026-01-25
**Version:** Post-Refactor v2.0

---

## Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [Data Flow](#data-flow)
4. [Module Organization](#module-organization)
5. [Import Conventions](#import-conventions)
6. [Template Architecture](#template-architecture)
7. [Session Management](#session-management)
8. [Permissions System](#permissions-system)
9. [Service Layer](#service-layer)
10. [Frontend Architecture](#frontend-architecture)

---

## Overview

Pronto is a full-stack restaurant management system with:

- **Customer-facing app** (menu browsing, ordering, checkout)
- **Employee dashboard** (orders, kitchen, payments, admin)
- **Unified API** (REST endpoints for both apps)

**Tech Stack:**

- Backend: Python 3.11, Flask, SQLAlchemy
- Frontend: TypeScript, Vue.js, Vite
- Database: PostgreSQL 13 (Supabase)
- Cache: Redis 7
- Testing: Playwright (E2E), Vitest (Unit)

---

## Directory Structure

### Top-Level Structure

```
pronto-app/
├── src/                  # All application code
│   ├── clients_app/        # Customer-facing app
│   ├── employees_app/      # Employee dashboard
│   ├── api_app/            # Unified API gateway
│   ├── shared/             # Shared code and resources
│   ├── admin/              # Admin app (future)
│   ├── waiter/             # Waiter app (future)
│   ├── chef/               # Chef app (future)
│   └── cashier/            # Cashier app (future)
├── config/                 # Configuration files
├── bin/                    # Shell scripts
├── e2e-tests/              # E2E tests
├── docs/                   # Documentation
└── dist/                   # Built frontend assets
```

### Shared Module (Central Hub)

```
src/shared/
├── __init__.py
├── models.py               # SQLAlchemy ORM models (all tables)
├── db.py                   # Database session management
├── config.py               # Configuration loader
├── permissions.py          # ⭐ Centralized permissions system
├── multi_scope_session.py  # Session management by role
├── constants.py            # Application constants
├── error_catalog.py        # Error definitions
├── audit_middleware.py     # Request auditing
├── logging_config.py       # Logging setup
├── auth/                   # Authentication
│   └── service.py          # Auth service
├── services/               # ⭐ Business logic (centralized)
│   ├── employee_service.py
│   ├── menu_service.py
│   ├── order_service.py
│   ├── role_service.py
│   ├── analytics_service.py
│   ├── payment_providers/
│   └── [20+ more services]
├── static/                 # ⭐ Shared static assets
│   ├── css/
│   │   ├── tokens.css      # Design tokens
│   │   ├── components/     # UI components (25+ files)
│   │   ├── dashboard.css
│   │   ├── waiter.css
│   │   └── reports.css
│   └── js/
│       ├── src/
│       │   ├── modules/    # TypeScript modules (40+ files)
│       │   ├── core/       # Core utilities
│       │   └── entrypoints/
│       └── [legacy JS files]
└── templates/              # ⭐ Shared Jinja2 templates
    └── includes/
        ├── _waiter_section.html
        ├── _chef_section.html
        ├── _cashier_section.html
        ├── _admin_sections.html
        └── [more includes]
```

### Employees App (Employee Dashboard)

```
src/employees_app/
├── app.py                  # Flask app factory
├── Dockerfile              # Container definition
├── decorators.py           # Route decorators
├── routes/                 # Flask blueprints
│   ├── auth.py             # Main auth
│   ├── dashboard.py        # Dashboard routes
│   ├── roles.py            # Role management
│   ├── waiter/
│   │   └── auth.py         # Waiter login
│   ├── chef/
│   │   └── auth.py         # Chef login
│   ├── cashier/
│   │   └── auth.py         # Cashier login
│   ├── admin/
│   │   └── auth.py         # Admin login
│   └── api/                # API endpoints
│       ├── orders.py
│       ├── menu.py
│       ├── sessions.py
│       └── [more APIs]
├── services/               # App-specific services (mostly empty now)
│   └── __init__.py
├── templates/              # Jinja2 templates
│   ├── base.html
│   ├── dashboard_waiter.html    # ⭐ Role-specific
│   ├── dashboard_chef.html      # ⭐ Role-specific
│   ├── dashboard_cashier.html   # ⭐ Role-specific
│   ├── dashboard_admin.html     # ⭐ Role-specific
│   ├── dashboard.html           # Original (fallback)
│   ├── includes/                # ⭐ Modular components
│   │   ├── _dashboard_base.html
│   │   ├── _notifications_panel.html
│   │   ├── _waiter_section.html
│   │   ├── _chef_section.html
│   │   ├── _cashier_section.html
│   │   ├── _admin_sections.html
│   │   └── _dashboard_scripts.html
│   └── [more templates]
└── static/                 # App-specific static files
    ├── css/
    └── js/
```

### Clients App (Customer-Facing)

```
src/clients_app/
├── app.py                  # Flask app factory
├── routes/
│   ├── menu.py             # Menu browsing
│   ├── cart.py             # Cart management
│   ├── checkout.py         # Checkout flow
│   └── api/                # Client APIs
├── templates/
│   ├── menu.html
│   ├── cart.html
│   ├── checkout.html
│   └── [more templates]
└── static/
    └── js/
        └── src/
            ├── modules/
            │   ├── menu-flow.ts
            │   ├── cart-manager.ts
            │   └── checkout-handler.ts
            └── entrypoints/
```

---

## Data Flow

### Request Flow (Employee Dashboard)

```
User Request (waiter login)
    ↓
Nginx/Gunicorn (port 6081)
    ↓
Multi-Scope Session Interface
    ↓
Flask App (employees_app/app.py)
    ↓
Blueprint Route (routes/waiter/auth.py)
    ↓
Role Validation (shared/permissions.py)
    ↓
Service Layer (shared/services/employee_service.py)
    ↓
Database (SQLAlchemy → PostgreSQL)
    ↓
Session Creation (multi_scope_session.py)
    ↓
Template Rendering (dashboard_waiter.html)
    ↓
Response (HTML + Set-Cookie: sess_waiter)
```

### Dashboard Template Rendering

```
routes/dashboard.py
    ↓
active_scope = session['active_scope']  # 'waiter', 'chef', etc.
    ↓
template_map = {
    'waiter': 'dashboard_waiter.html',
    'chef': 'dashboard_chef.html',
    'cashier': 'dashboard_cashier.html',
    'admin': 'dashboard_admin.html'
}
    ↓
template_name = template_map.get(active_scope)
    ↓
render_template(template_name, context)
    ↓
Jinja2 includes modular sections
    ↓
Response (role-specific HTML, ~47% smaller for waiter/chef/cashier)
```

---

## Module Organization

### Centralized vs Distributed

**Centralized in `shared/`:**

- ✅ Services (business logic)
- ✅ Models (database)
- ✅ Permissions system
- ✅ Session management
- ✅ Core utilities
- ✅ Shared static assets

**Distributed in apps:**

- Routes/Blueprints (app-specific)
- Templates (with shared includes)
- App-specific configuration
- App factories

**Why Centralized?**

- Single source of truth
- No code duplication
- Easier to maintain
- Promotes reusability
- Better testing

---

## Import Conventions

### ✅ CORRECT Imports

```python
# Services (ALWAYS from shared)
from shared.services.menu_service import list_menu
from shared.services.order_service import create_order
from shared.services.employee_service import get_employee_by_id

# Permissions (ALWAYS from shared)
from shared.permissions import Permission, has_permission

# Models (from shared)
from shared.models import Order, MenuItem, Employee

# Database (from shared)
from shared.db import get_session

# Constants (from shared)
from shared.constants import OrderStatus, SessionStatus

# Auth (from shared)
from shared.auth.service import Roles
```

### ❌ WRONG Imports (Deprecated)

```python
# These will fail:
from employees_app.services.menu_service import list_menu  # ❌ Moved
from employees_app.permissions import Permission  # ❌ Moved
from employees_app.scope_guard import ScopeGuard  # ❌ Removed
```

### Pattern: Always Check Shared First

When adding a new import:

1. Check if it exists in `shared/` first
2. If yes, import from `shared.*`
3. If no, consider if it should be in `shared/`
4. Only use app-specific imports for app-specific code

---

## Template Architecture

### Modular Template System

Dashboard templates use an include-based architecture:

**Main Templates (Role-Specific):**

```jinja2
{% extends "base.html" %}
{% block content %}
  {% include 'includes/_dashboard_base.html' %}
  {% include 'includes/_waiter_section.html' %}
  {% include 'includes/_dashboard_scripts.html' %}
{% endblock %}
```

**Include Files:**
| Include | Size | Purpose |
|---------|------|---------|
| `_dashboard_base.html` | 2.3 KB | Auth checks, CSS, base structure |
| `_notifications_panel.html` | 2.6 KB | Waiter call notifications |
| `_waiter_section.html` | 37 KB | Waiter board UI |
| `_chef_section.html` | 7.5 KB | Kitchen display system |
| `_cashier_section.html` | 22 KB | Payment processing UI |
| `_admin_sections.html` | 113 KB | Menu, config, reports, employees |
| `_dashboard_scripts.html` | 70 KB | JavaScript modules |

**Benefits:**

1. **Reusability** - Same includes across templates
2. **Smaller Payloads** - Only load needed sections
3. **Easier Maintenance** - Edit one include, affects all
4. **Better Testing** - Test components independently

### Template Rendering Flow

```
User requests /dashboard?context=waiter
    ↓
routes/dashboard.py determines active_scope = 'waiter'
    ↓
Selects template: dashboard_waiter.html
    ↓
Template extends base.html
    ↓
Includes _dashboard_base.html (auth, CSS)
    ↓
Includes _notifications_panel.html (waiter calls)
    ↓
Includes _waiter_section.html (waiter board)
    ↓
Includes _dashboard_scripts.html (JS)
    ↓
Renders final HTML (~112 KB vs 258 KB monolithic)
```

---

## Session Management

### Multi-Scope Session System

Each role has isolated sessions via path-based cookies:

```python
# shared/multi_scope_session.py

SCOPE_CONFIGS = {
    "/waiter": {
        "cookie_name": "sess_waiter",
        "cookie_path": "/waiter",
    },
    "/chef": {
        "cookie_name": "sess_chef",
        "cookie_path": "/chef",
    },
    "/cashier": {
        "cookie_name": "sess_cashier",
        "cookie_path": "/cashier",
    },
    "/admin": {
        "cookie_name": "sess_admin",
        "cookie_path": "/admin",
    },
}
```

**How It Works:**

1. User logs in to `/waiter/login`
2. System sets `sess_waiter` cookie with `path=/waiter`
3. Cookie only sent for requests to `/waiter/*`
4. Other roles don't see this cookie
5. Prevents session leakage between roles

**Session Data:**

```python
session['employee_id'] = employee.id
session['employee_email'] = employee.email
session['employee_role'] = employee.role
session['active_scope'] = 'waiter'  # Current console
```

---

## Permissions System

### Permission Levels

```python
# shared/permissions.py

class Permission:
    # Orders
    ORDERS_VIEW = "orders:view"
    ORDERS_CREATE = "orders:create"
    ORDERS_CANCEL = "orders:cancel"

    # Kitchen
    KITCHEN_VIEW = "kitchen:view"
    KITCHEN_ACCEPT = "kitchen:accept"
    KITCHEN_COMPLETE = "kitchen:complete"

    # Payments
    PAYMENTS_VIEW = "payments:view"
    PAYMENTS_PROCESS = "payments:process"

    # Menu
    MENU_VIEW = "menu:view"
    MENU_CREATE = "menu:create"
    MENU_EDIT = "menu:edit"
    MENU_DELETE = "menu:delete"
    MENU_EDIT_PRICE = "menu:edit_price"

    # Config
    CONFIG_VIEW = "config:view"
    CONFIG_EDIT = "config:edit"

    # Reports
    REPORTS_VIEW = "reports:view"

    # Employees
    EMPLOYEES_VIEW = "employees:view"
    EMPLOYEES_MANAGE_PERMISSIONS = "employees:manage_permissions"
```

### Role-Permission Mapping

```python
ROLE_PERMISSIONS = {
    "waiter": [
        Permission.ORDERS_VIEW,
        Permission.ORDERS_CREATE,
        # ... waiter permissions
    ],
    "chef": [
        Permission.KITCHEN_VIEW,
        Permission.KITCHEN_ACCEPT,
        # ... chef permissions
    ],
    "cashier": [
        Permission.PAYMENTS_VIEW,
        Permission.PAYMENTS_PROCESS,
        # ... cashier permissions
    ],
    "admin": [
        # ALL permissions
    ]
}
```

### Usage

```python
# In routes
from shared.permissions import has_permission, Permission

if has_permission(employee_role, Permission.MENU_EDIT):
    # Allow menu editing
else:
    # Deny access
```

---

## Service Layer

### Service Organization

All services in `shared/services/` follow consistent patterns:

**Example: menu_service.py**

```python
def list_menu(include_inactive=False):
    """List all menu items."""
    with get_session() as db:
        query = db.query(MenuItem)
        if not include_inactive:
            query = query.filter(MenuItem.is_active == True)
        items = query.all()
        return [item.to_dict() for item in items]

def create_menu_item(data):
    """Create new menu item."""
    with get_session() as db:
        item = MenuItem(**data)
        db.add(item)
        db.commit()
        return item.to_dict()
```

**Naming Conventions:**

- `list_*` - Get multiple records
- `get_*` - Get single record
- `create_*` - Create new record
- `update_*` - Update existing record
- `delete_*` - Delete record
- `*_by_id` - Lookup by ID
- `*_by_*` - Lookup by other field

**Transaction Management:**

- Always use `with get_session() as db:`
- Commit only on success
- Rollback on exception (automatic with context manager)

---

## Frontend Architecture

### TypeScript Modules

Frontend organized into focused modules:

```
src/shared/static/js/src/modules/
├── waiter-board.ts       # Waiter dashboard logic
├── kitchen-board.ts      # Chef/kitchen logic
├── cashier-board.ts      # Cashier/payment logic
├── menu-manager.ts       # Menu CRUD
├── orders-board.ts       # Order management
├── payments-flow.ts      # Payment processing
├── realtime.ts           # WebSocket/SSE
├── toast.ts              # Notifications
└── [35+ more modules]
```

**Module Pattern:**

```typescript
// modules/example-manager.ts
export class ExampleManager {
  constructor() {
    this.init();
  }

  init() {
    // Setup
  }

  // Methods
}

// Auto-initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    new ExampleManager();
  });
} else {
  new ExampleManager();
}
```

### Build System (Vite)

```bash
# Build for employees
PRONTO_TARGET=employees npm run build
# → dist/employees/dashboard.js

# Build for clients
PRONTO_TARGET=clients npm run build
# → dist/clients/menu.js
```

**Entry Points:**

- `src/entrypoints/dashboard.ts` → Employee dashboard
- `src/entrypoints/base.ts` → Common base
- `src/entrypoints/menu.ts` → Client menu

---

## Best Practices

### 1. Services

- ✅ Always import from `shared.services.*`
- ✅ Use services for business logic
- ✅ Keep routes thin (just request/response)
- ✅ Services should be stateless
- ✅ Use context managers for DB sessions

### 2. Permissions

- ✅ Check permissions at route level
- ✅ Use decorators when possible
- ✅ Always verify in backend (never trust frontend)
- ✅ Log permission denials for audit

### 3. Templates

- ✅ Use includes for reusable components
- ✅ Keep templates focused (one responsibility)
- ✅ Leverage role-specific templates
- ✅ Minimize inline JavaScript (use modules)

### 4. Frontend

- ✅ Use TypeScript modules (not inline scripts)
- ✅ Follow module pattern for organization
- ✅ Build with Vite (not manual bundling)
- ✅ Sanitize all user input (XSS prevention)

### 5. Security

- ✅ Validate roles on every protected route
- ✅ Use path-scoped session cookies
- ✅ Sanitize HTML before insertion
- ✅ Never trust client-side data
- ✅ Log security events

---

## Troubleshooting

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'employees_app.services'`

**Solution:** Update import to use `shared.services.*`

### Template Not Found

**Problem:** `jinja2.exceptions.TemplateNotFound: includes/_section.html`

**Solution:** Check template path, ensure include file exists

### Session Issues

**Problem:** User logged in but still redirected to login

**Solution:** Check multi_scope_session.py configuration, verify cookie path

---

**For more details, see:**

- CLAUDE.md - Development guidance
- CHANGELOG.md - Recent changes
- docs/ - Additional documentation
- /Users/molder/OneDrive/pronto-backup/ - Refactoring documentation
