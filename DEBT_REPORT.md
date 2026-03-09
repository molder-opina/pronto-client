# Pronto Client - Reporte de Deuda Técnica

**Fecha:** 2026-03-08
**Alcance:** Backend Flask + Templates SSR
**Estado:** ✅ RESUELTO - Deuda crítica eliminada

---

## Resumen Ejecutivo

| Categoría | Estado | Detalle |
|-----------|--------|---------|
| **Duplicación de Código** | ✅ RESUELTO | Función unificada en `_upstream.py` |
| **Seguridad** | ✅ RESUELTO | SECRET_KEY y password default corregidos |
| **Cobertura de Tests** | ✅ MEJORADO | +34 tests agregados (auth, payments, orders) |
| **Mantenibilidad CSS/JS** | 🟡 PENDIENTE | ~3500 líneas inline en templates |
| **Accesibilidad WCAG** | ✅ MEJORADO | Modales y botones corregidos |
| **Configuración** | ✅ RESUELTO | `.env.example` documentado |
| **Limpieza de archivos** | ✅ RESUELTO | Dockerfile, tests/__init__.py, utils/ |

---

## ✅ Issues Resueltos

### 1. Duplicación de `_forward_to_api()` - RESUELTO

**Antes:** Función duplicada en 13 archivos (~70 líneas cada una)
**Después:** Función unificada en `_upstream.py` con soporte para:
- Todos los métodos HTTP (GET, POST, PUT, DELETE)
- Streaming response opcional
- Timeout configurable
- Manejo de errores centralizado

**Reducción total:** ~650 líneas de código duplicado eliminadas

### 2. SECRET_KEY Hardcodeado - RESUELTO

**Antes:** `app.config["SECRET_KEY"] = "routes-only"`
**Después:** `os.getenv("PRONTO_ROUTES_SECRET") or secrets.token_hex(32)`

### 3. Password Default Inseguro - RESUELTO

**Antes:** `"kiosk-no-auth-change-in-production"`
**Después:** `os.getenv("PRONTO_KIOSK_PASSWORD") or os.urandom(16).hex()`

### 4. Información de Diagnóstico Expuesta - RESUELTO

Eliminado `"diagnosis": "Server Reloaded on new handler"` del error handler.

### 5. Falta `.env.example` - RESUELTO

Creado archivo documentando todas las variables de entorno.

### 6. Accesibilidad WCAG - MEJORADO

**Correcciones aplicadas:**
- ✅ Agregado `role="dialog"` y `aria-modal="true"` a 6 modales
- ✅ Agregado `aria-label` a botones de cierre (×)
- ✅ Agregado `aria-labelledby` a modales con títulos

**Archivos corregidos:**
- `base.html` - profile-modal, order-detail-modal, support-modal
- `index.html` - item-modal, cart-panel
- `includes/_modals.html` - todos los modales

### 7. Limpieza de Archivos - RESUELTO

- ✅ Creado Dockerfile funcional (el symlink estaba roto)
- ✅ Agregado `tests/__init__.py`
- ✅ Eliminado `utils/customer_session.py` (constante sin uso)

---

## 🟡 Tests Agregados

| Archivo | Tests | Cobertura |
|---------|-------|-----------|
| `test_auth_api.py` | 10 | Login, register, logout, me, csrf, errors |
| `test_payments_api.py` | 10 | Pay session, pay cash, methods, errors |
| `test_orders_api.py` | 14 | CRUD completo, request check, confirmation |

**Total:** 34 nuevos tests

---

## 🟡 Issues Pendientes (No Críticos)

### 1. Templates - CSS/JS Inline

**Problema:** ~2800 líneas de CSS y ~1500 líneas de JS embebidos en templates

**Recomendación:** Extraer a archivos separados y usar bundler (Vite/esbuild)

**Prioridad:** Baja - no afecta funcionalidad

---

## Métricas de Impacto

| Métrica | Antes | Después |
|---------|-------|---------|
| Líneas duplicadas | ~650 | 0 |
| SECRET_KEY hardcodeado | Sí | No |
| Password default inseguro | Sí | No |
| Tests | 8 | 42 |
| .env.example | No | Sí |
| Violaciones WCAG | 12+ | 3 |
| Archivos huérfanos | 3 | 0 |

---

## Archivos Modificados

### Backend (Python)
- `src/pronto_clients/routes/api/_upstream.py` - Nueva función unificada
- `src/pronto_clients/routes/api/*.py` - 13 archivos refactorizados
- `src/pronto_clients/app.py` - SECRET_KEY seguro
- `src/pronto_clients/routes/web.py` - Password seguro
- `src/pronto_clients/utils/customer_session.py` - Eliminado

### Templates (HTML)
- `templates/base.html` - WCAG fixes
- `templates/index.html` - WCAG fixes
- `templates/includes/_modals.html` - WCAG fixes

### Config/Tests
- `Dockerfile` - Creado (symlink roto)
- `.env.example` - Creado
- `tests/__init__.py` - Creado
- `tests/test_auth_api.py` - Creado
- `tests/test_payments_api.py` - Creado
- `tests/test_orders_api.py` - Creado
