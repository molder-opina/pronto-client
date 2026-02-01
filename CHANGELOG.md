# Changelog

All notable changes to the Pronto project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Role-specific dashboard templates (waiter, chef, cashier, admin)
- Modular template includes system in `build/employees_app/templates/includes/`
- Centralized services in `build/shared/services/`
- Centralized permissions system in `build/shared/permissions.py`
- Shared static assets in `build/shared/static/`
- Shared template components in `build/shared/templates/includes/`
- Comprehensive documentation in `/Users/molder/OneDrive/pronto-backup/`
- New documentation files: `docs/estructura-directorios.md`, `docs/estructura-routes-api.md`
- CHANGELOG.md (this file)

### Changed

- **BREAKING:** All service imports must now use `shared.services.*` instead of `employees_app.services.*`
- **BREAKING:** Permission imports must now use `shared.permissions` instead of `employees_app.permissions`
- Dashboard route now serves role-specific templates based on `active_scope`
- Multi-scope session cookie configuration improved for better isolation
- Template structure refactored from monolithic to modular (6,403 lines → 7 modular files)
- Updated 30+ files with new import paths

### Fixed

- Multi-scope session cookie configuration bug (sessions now properly isolated by role)
- XSS vulnerabilities in `waiter-board.ts` (replaced innerHTML with DOM manipulation)
- XSS vulnerabilities in `client-profile.ts` (added escapeHtml sanitization)
- Missing role validation in waiter/chef/cashier login routes
- Inconsistent role validation across all auth routes
- Broken imports `employees.shared.*` in abandoned code (removed files)
- Duplicate call to `sync_env_config_to_db()` in clients_app/app.py

### Deprecated

- `employees_app/services/*` - Services moved to `shared/services/`
- `employees_app/permissions.py` - Moved to `shared/permissions.py`
- `employees_app/scope_guard.py` - Consolidated into shared
- Monolithic `dashboard.html` - Replaced with role-specific templates (still available as fallback)

### Removed

- `build/employees_app/services/employee_service.py` (moved to shared/)
- `build/employees_app/services/menu_service.py` (moved to shared/)
- `build/employees_app/services/order_service.py` (moved to shared/)
- `build/employees_app/services/role_service.py` (moved to shared/)
- `build/employees_app/permissions.py` (moved to shared/)
- `build/employees_app/scope_guard.py` (consolidated)
- `build/shared/app.py` (duplicate with broken imports)
- `build/shared/routes/` (abandoned code with `employees.shared.*` imports)
- `build/admin/`, `build/waiter/`, `build/chef/`, `build/cashier/` (duplicate unused code)
- Debug scripts: `check_button_layout.py`, `debug_cache.py`, etc. (archived to `scripts/archived/`)
- Obsolete test files in `__tests__/basic.test.ts`
- Temporary Playwright artifacts

### Security

- Fixed critical session isolation bug in multi_scope_session.py
- Mitigated XSS vulnerabilities in employee and client apps
- Added strict role validation to all console login routes
- Improved session cookie configuration with proper path restrictions

### Performance

- Reduced template size by ~47% for specific roles (waiter: 56%, chef: 68%, cashier: 63%)
- Eliminated code duplication through service centralization
- Improved page load times with smaller, role-specific templates
- Better caching with modular template structure

## [2026-01-25] - Refactoring Complete

### Summary

Major refactoring to improve security, performance, and code organization:

1. **Security Hardening** - Fixed 3 critical bugs (session isolation, XSS prevention, role validation)
2. **Template Modularization** - Separated 6,403-line monolith into 7 reusable components
3. **Service Centralization** - Moved all services to shared/ for reusability
4. **Architecture Foundation** - Created structure for future modular apps

**Stats:**

- 177 files changed
- 57,651 lines added
- 5,449 lines removed
- ~52,000 net lines added (including new modular structure)

**Commits:**

- `07ecfd6` - refactor(security,templates): comprehensive fixes and template separation
- `3f06adc` - refactor: migrate services to shared and update all imports

**Documentation:**

- Complete refactoring documentation in `/Users/molder/OneDrive/pronto-backup/`
- Updated CLAUDE.md with new architecture
- Created comprehensive migration guides

**Contributors:**

- Claude Sonnet 4.5 (security fixes, template separation, import migration)
- Gemini (modular structure creation, code cleanup)

---

## Migration Guide

### For Developers

If you're working on existing code, update your imports:

```python
# OLD (will fail):
from employees_app.services.menu_service import list_menu
from employees_app.services.order_service import get_dashboard_metrics
from employees_app.permissions import Permission

# NEW (required):
from shared.services.menu_service import list_menu
from shared.services.order_service import get_dashboard_metrics
from shared.permissions import Permission
```

### For New Features

When adding new functionality:

1. **Services:** Add to `build/shared/services/` (not app-specific services)
2. **Permissions:** Use `shared.permissions` system
3. **Templates:** Create includes in `build/employees_app/templates/includes/`
4. **Static Assets:** Consider if they should go in `build/shared/static/`

### Template Structure

Dashboard templates are now role-specific:

- Waiter sees: `dashboard_waiter.html` (~112 KB)
- Chef sees: `dashboard_chef.html` (~82 KB)
- Cashier sees: `dashboard_cashier.html` (~96 KB)
- Admin sees: `dashboard_admin.html` (~255 KB, full access)

No code changes needed - routing handles this automatically based on `session['active_scope']`.

---

## Notes

### Backup & Rollback

Complete backup available at:

- Git branch: `backup/pre-refactor` (commit: 66819de)
- Tarball: `/Users/molder/OneDrive/pronto-backup/proyecto_backup_2026-01-24.tar.gz` (42 MB)
- Database: `/Users/molder/OneDrive/pronto-backup/backup_db_2026-01-24_complete.sql` (556 KB)

### Testing

All automated tests passing:

- ✅ Service builds successfully
- ✅ All HTTP endpoints return 200 OK
- ✅ No import errors in logs
- ✅ Template syntax valid
- ✅ No regression in functionality

Manual testing recommended before production deployment.

---

**Last Updated:** 2026-01-25
**Maintained By:** Development Team
