# Testing para Pronto App

Este documento describe el suite de tests configurado para Pronto App - Sistema de Gestión de Restaurantes.

## Estructura de Tests

```
pronto-app/
├── tests/                          # Backend tests (pytest)
│   ├── conftest.py                 # Fixtures compartidas
│   ├── unit/                       # Tests unitarios
│   │   ├── test_models.py
│   │   ├── test_services.py
│   │   └── test_table_utils.py
│   └── integration/                # Tests de integración
│       ├── test_auth_api.py
│       ├── test_business_config_api.py
│       └── test_recommendations_api.py
├── build/                          # Frontend tests (Vitest)
│   ├── employees_app/static/js/src/components/__tests__/
│   │   ├── EmployeesManager.test.vue
│   │   └── OrderForm.test.vue
│   ├── clients_app/static/js/src/components/__tests__/
│   │   └── MenuCard.test.vue
│   └── test-setup.ts               # Setup de Vitest
├── e2e-tests/                      # E2E tests (Playwright)
│   ├── playwright.config.ts        # Configuración de Playwright
│   └── tests/
│       ├── employees/              # Tests para app de empleados
│       │   ├── auth.spec.ts
│       │   ├── orders.spec.ts
│       │   └── menu.spec.ts
│       └── clients/                # Tests para app de clientes
│           └── client-app.spec.ts
├── vitest.config.ts                # Configuración de Vitest
├── pyproject.toml                  # Configuración de pytest
└── run-all-tests.sh                # Script para ejecutar todos los tests
```

## Configuración

### Backend (pytest)

Pronto App ya tiene pytest configurado en `requirements-dev.txt` y `pyproject.toml`:

```bash
# Instalar dependencias
pip install -r requirements-dev.txt

# Ejecutar tests
pytest
```

### Frontend (Vitest)

Vitest está configurado para componentes Vue.js:

```bash
# Instalar dependencias (si no están instaladas)
npm install

# Ejecutar tests
npm run test
```

### E2E (Playwright)

Playwright está configurado para pruebas de extremo a extremo:

```bash
# Instalar dependencias E2E
cd e2e-tests
npm install
npx playwright install

# Ejecutar tests E2E
npm run test
```

## Ejecutar Tests

### Ejecutar todos los tests

```bash
./run-all-tests.sh
```

### Solo backend

```bash
./run-all-tests.sh --backend
# o
pytest
```

### Solo frontend

```bash
./run-all-tests.sh --frontend
# o
npm run test
```

### Solo E2E

```bash
./run-all-tests.sh --e2e
# o
cd e2e-tests && npm run test
```

### Solo tests unitarios

```bash
./run-all-tests.sh --unit
# o
pytest -m unit
```

### Solo tests de integración

```bash
./run-all-tests.sh --integration
# o
pytest -m integration
```

### Con reporte de cobertura

```bash
./run-all-tests.sh --coverage
# o
pytest --cov=build --cov-report=html
npm run test:coverage
```

### Modo verbose

```bash
./run-all-tests.sh --verbose
```

## Scripts Disponibles

### Backend (pytest)

```bash
pytest                           # Ejecutar todos los tests
pytest -v                         # Modo verbose
pytest -m unit                    # Solo tests unitarios
pytest -m integration             # Solo tests de integración
pytest --cov=build                # Con cobertura de código
pytest --cov=build --cov-report=html # Reporte HTML de cobertura
pytest -x                         # Detener al primer fallo
pytest -k "auth"                  # Ejecutar tests que contengan "auth"
pytest -n auto                    # Ejecución paralela
```

### Frontend (Vitest)

```bash
npm run test                      # Ejecutar tests en modo watch
npm run test -- --run             # Ejecutar tests una vez
npm run test:ui                   # Interfaz UI de Vitest
npm run test:coverage             # Con cobertura de código
npm run test -- -u                 # Modo update snapshots
npm run test -- --reporter=verbose # Modo verbose
```

### E2E (Playwright)

```bash
cd e2e-tests
npm run test                      # Ejecutar tests headless
npm run test:ui                   # Interfaz UI de Playwright
npm run test:headed               # Ejecutar con navegador visible
npm run test:debug                # Modo debug interactivo
npm run test:employees            # Solo tests de empleados
npm run test:clients              # Solo tests de clientes
npm run report                     # Ver reporte HTML
```

## Tests Creados

### Backend (pytest)

**Unit Tests:**

- `test_models.py` - Modelos de base de datos
- `test_services.py` - Servicios de negocio
- `test_table_utils.py` - Utilidades de tablas

**Integration Tests:**

- `test_auth_api.py` - API de autenticación
- `test_business_config_api.py` - API de configuración de negocio
- `test_recommendations_api.py` - API de recomendaciones

**Fixtures Disponibles:**

- `test_db_engine` - Motor de base de datos de prueba
- `db_session` - Sesión de base de datos
- `employee_app` - App Flask de empleados
- `client_app` - App Flask de clientes
- `employee_client` - Cliente de prueba para app de empleados
- `client_client` - Cliente de prueba para app de clientes
- `sample_employee` - Empleado de prueba
- `sample_customer` - Cliente de prueba
- `sample_category` - Categoría de menú de prueba
- `sample_menu_item` - Item de menú de prueba
- `sample_menu_items` - Múltiples items de menú de prueba
- `authenticated_session` - Sesión autenticada

### Frontend (Vitest)

**Componentes de Empleados:**

- `EmployeesManager.test.vue` - Gestor de empleados
- `OrderForm.test.vue` - Formulario de órdenes

**Componentes de Clientes:**

- `MenuCard.test.vue` - Tarjeta de item de menú

### E2E (Playwright)

**Tests de Empleados:**

- `auth.spec.ts` - Autenticación de empleados
- `orders.spec.ts` - Gestión de órdenes
- `menu.spec.ts` - Gestión de menú

**Tests de Clientes:**

- `client-app.spec.ts` - Aplicación de clientes

## Flujos Probados

### Backend

- ✅ Creación y autenticación de usuarios
- ✅ Gestión de empleados y clientes
- ✅ CRUD de items de menú
- ✅ Creación y actualización de órdenes
- ✅ Procesamiento de pagos
- ✅ Consultas y búsquedas
- ✅ Validaciones de negocio

### Frontend

- ✅ Renderizado de componentes
- ✅ Manejo de eventos
- ✅ Validaciones de formularios
- ✅ Estado del componente
- ✅ Emisiones de eventos
- ✅ Props y slots

### E2E

- ✅ Login de empleados
- ✅ Navegación entre páginas
- ✅ Creación de órdenes
- ✅ Actualización de estados
- ✅ Gestión de menú
- ✅ Carrito de compras
- ✅ Checkout
- ✅ Búsqueda y filtros
- ✅ Flujo completo de cliente

## Uso con OpenCode

El suite de tests está diseñado para trabajar con OpenCode de las siguientes maneras:

### 1. Detección de Regresiones

OpenCode puede ejecutar automáticamente los tests después de cambios para detectar regresiones:

```bash
# Después de cada cambio
./run-all-tests.sh
```

### 2. Documentación de Bugs

Crear tests que reproduzcan bugs para documentar el problema:

```python
# tests/integration/test_bug_reproduction.py
def test_bug_payment_calculation(employee_client, sample_order):
    """Bug: El total de la orden no incluye el IVA"""
    response = employee_client.get(f'/api/orders/{sample_order.id}')
    assert response.json['total'] == expected_with_iva  # Este test fallará
```

### 3. Verificación de Fixes

Confirmar que el fix resuelve el problema:

```bash
# 1. OpenCode identifica el problema
# 2. Crea el test que reproduce el bug (falla)
# 3. OpenCode corrige el código
# 4. Ejecuta el test (pasa) -> Fix verificado
```

### 4. Mejora de Cobertura

Agregar tests para código sin cubrir:

```bash
# Verificar cobertura
pytest --cov=build --cov-report=html

# Identificar archivos con baja cobertura
# OpenCode puede agregar tests para mejorarla
```

### 5. Tests Basados en Escenarios

OpenCode puede crear tests basados en escenarios reales del negocio:

```python
# Escenario: Cliente hace pedido y paga con tarjeta
def test_client_order_with_card_payment(client_client, sample_menu_item):
    # Paso 1: Cliente selecciona items
    # Paso 2: Agrega al carrito
    # Paso 3: Realiza checkout
    # Paso 4: Paga con tarjeta
    # Paso 5: Verifica confirmación
    pass
```

## Configuración de Marcadores

Los tests pueden marcarse para ejecución selectiva:

```python
import pytest

@pytest.mark.unit
def test_unit_example():
    """Test unitario rápido"""
    pass

@pytest.mark.integration
def test_integration_example():
    """Test de integración más lento"""
    pass

@pytest.mark.slow
def test_slow_example():
    """Test lento que puede omitirse"""
    pass
```

Ejecución selectiva:

```bash
pytest -m unit              # Solo unitarios
pytest -m integration       # Solo integración
pytest -m "not slow"        # Excluir tests lentos
```

## CI/CD

Para integración continua, puedes agregar lo siguiente a tu pipeline:

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt
          npm install
          cd e2e-tests && npm install && npx playwright install --with-deps

      - name: Run tests
        run: ./run-all-tests.sh --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [Vitest Documentation](https://vitest.dev/)
- [Playwright Documentation](https://playwright.dev/)
- [Vue Test Utils](https://test-utils.vuejs.org/)
- [Testing Library Vue](https://testing-library.com/vue)

## Mejores Prácticas

1. **Escribir tests independientes**: Cada test debe funcionar de forma aislada
2. **Usar nombres descriptivos**: Los nombres de los tests deben describir qué están probando
3. **Usar fixtures**: Reutiliza fixtures para configuración común
4. **Mock dependencias externas**: Evita llamar a servicios externos en tests
5. **Prueba casos edge case**: No solo el camino feliz
6. **Mantener tests rápidos**: Los tests unitarios deben ser rápidos
7. **Actualizar tests cuando el código cambia**: Los tests deben evolucionar con el código

## Resumen

Pronto App tiene un suite de pruebas completo con:

- ✅ Tests de backend (pytest) - Unitarios y de integración
- ✅ Tests de frontend (Vitest) - Componentes Vue.js
- ✅ Tests E2E (Playwright) - Flujos completos
- ✅ Configuración de cobertura
- ✅ Script unificado para ejecutar todos los tests
- ✅ Fixtures reutilizables
- ✅ Integración lista para CI/CD

Este suite permite a OpenCode detectar y resolver problemas de forma automatizada y eficiente.
