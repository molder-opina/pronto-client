# Pronto - Restaurant Management System

## Overview

Pronto is a comprehensive restaurant management system designed to streamline operations for employees (Waiters, Chefs, Cashiers, Admins) and provide a seamless experience for clients.

## Architecture

The project follows a modular architecture:

- **`clients_app`**: Client-facing mobile web application.
- **`employees_app`**: Employee dashboard with granular role-based access control (RBAC).
- **`api_app`**: Backend API services.
- **`shared`**: Common logic, database models, permissions, and utilities shared across all applications.

## Documentation

Detailed documentation is available in the `docs/` directory:

- [Architecture Overview](docs/ARCHITECTURE_OVERVIEW.md)
- [Implementation Summary](docs/IMPLEMENTATION_SUMMARY.md)
- [Modularization Summary](docs/MODULARIZATION_SUMMARY.md)
- [Testing Guide](docs/TESTING.md)

## Development

### Structure

The source code is located in the `src/` directory, organized by application.

### Running the Project

Refer to `DEPLOYMENT_VERIFICATION.md` or use the provided scripts in `bin/` or `scripts/`.

- `bin/mac/local-dev.sh`: Start local development environment.
- `docker-compose up`: Run services via Docker.

## Recent Updates (Phase 2)

- Consolidated `permissions` and `scope_guard` logic into the `shared` module to eliminate code duplication.
- Enhanced Role-Based Access Control (RBAC) with granular permissions.
- Modularized service architecture.
