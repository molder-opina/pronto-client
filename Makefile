# =============================================================================
# Makefile para Pronto App - Herramientas de Calidad de Código
# =============================================================================

.PHONY: help install install-dev setup-dev clean lint format type-check security test test-cov ci pre-commit check-all validate-server security-scan llm-security

# Variables
PYTHON := python3
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
BLACK := $(PYTHON) -m black
MYPY := $(PYTHON) -m mypy
BANDIT := $(PYTHON) -m bandit
PRE_COMMIT := pre-commit

# Directorios a analizar
SRC_DIRS := build scripts bin
TEST_DIRS := tests

# Colores para output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# =============================================================================
# Help
# =============================================================================

help:  ## Mostrar este mensaje de ayuda
	@echo "$(GREEN)Pronto App - Comandos disponibles:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Instalación y configuración
# =============================================================================

install:  ## Instalar dependencias de producción
	@echo "$(GREEN)Instalando dependencias de producción...$(NC)"
	$(PIP) install -r requirements.txt

install-dev:  ## Instalar dependencias de desarrollo
	@echo "$(GREEN)Instalando dependencias de desarrollo...$(NC)"
	$(PIP) install -r requirements-dev.txt

setup-dev: install-dev  ## Configurar entorno de desarrollo completo
	@echo "$(GREEN)Configurando pre-commit hooks...$(NC)"
	$(PRE_COMMIT) install
	$(PRE_COMMIT) install --hook-type commit-msg
	@echo "$(GREEN)¡Entorno de desarrollo configurado!$(NC)"

# =============================================================================
# Limpieza
# =============================================================================

clean:  ## Limpiar archivos temporales y caché
	@echo "$(YELLOW)Limpiando archivos temporales...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .coverage.*
	@echo "$(GREEN)¡Limpieza completada!$(NC)"

# =============================================================================
# Linting y Formateo
# =============================================================================

lint:  ## Ejecutar linter (ruff) con auto-fix
	@echo "$(GREEN)Ejecutando ruff linter...$(NC)"
	$(RUFF) check $(SRC_DIRS) --fix

lint-check:  ## Ejecutar linter sin modificar archivos
	@echo "$(GREEN)Ejecutando ruff linter (solo check)...$(NC)"
	$(RUFF) check $(SRC_DIRS)

format:  ## Formatear código con ruff (o black)
	@echo "$(GREEN)Formateando código con ruff...$(NC)"
	$(RUFF) format $(SRC_DIRS)
	# Si prefieres black, comenta la línea anterior y descomenta esta:
	# $(BLACK) $(SRC_DIRS)

format-check:  ## Verificar formateo sin modificar
	@echo "$(GREEN)Verificando formateo...$(NC)"
	$(RUFF) format --check $(SRC_DIRS)

imports:  ## Ordenar imports con ruff
	@echo "$(GREEN)Ordenando imports...$(NC)"
	$(RUFF) check --select I --fix $(SRC_DIRS)

# =============================================================================
# Type Checking
# =============================================================================

type-check:  ## Ejecutar chequeo de tipos con mypy
	@echo "$(GREEN)Ejecutando mypy...$(NC)"
	$(MYPY) $(SRC_DIRS) || true

# =============================================================================
# Seguridad
# =============================================================================

security:  ## Ejecutar análisis de seguridad con bandit
	@echo "$(GREEN)Ejecutando bandit (análisis de seguridad)...$(NC)"
	$(BANDIT) -r $(SRC_DIRS) -c pyproject.toml

security-report:  ## Generar reporte completo de seguridad
	@echo "$(GREEN)Generando reporte de seguridad...$(NC)"
	$(BANDIT) -r $(SRC_DIRS) -c pyproject.toml -f json -o bandit-report.json
	$(BANDIT) -r $(SRC_DIRS) -c pyproject.toml -f html -o bandit-report.html
	@echo "$(GREEN)Reportes generados: bandit-report.json, bandit-report.html$(NC)"

security-scan:  ## Ejecutar todos los scans de seguridad (pre-commit)
	@echo "$(GREEN)Ejecutando scans completos de seguridad...$(NC)"
	./scripts/validate-security.sh

llm-security:  ## Ejecutar validaciones de seguridad LLM/RAG
	@echo "$(GREEN)Ejecutando validaciones de seguridad LLM/RAG...$(NC)"
	./scripts/validate-llm-security.sh

validate-server: lint-check format-check type-check security test  ## Validaciones estrictas como en servidor
	@echo "$(GREEN)✓ Validaciones de servidor completadas$(NC)"

full-security:  ## Ejecutar todas las validaciones de seguridad
	@echo "$(GREEN)Ejecutando todas las validaciones de seguridad...$(NC)"
	$(MAKE) security
	./scripts/validate-security.sh
	@echo "$(GREEN)✓ Validaciones de seguridad completadas$(NC)"
	@echo "$(GREEN)✓ Validaciones de servidor completadas$(NC)"
	@echo "$(GREEN)✓ Quick check completado$(NC)"

# =============================================================================
# Desarrollo
# =============================================================================

dev-run:  ## Ejecutar aplicación en modo desarrollo
	@echo "$(GREEN)Iniciando aplicación en modo desarrollo...$(NC)"
	docker-compose up

dev-stop:  ## Detener aplicación
	@echo "$(YELLOW)Deteniendo aplicación...$(NC)"
	docker-compose down

dev-restart:  ## Reiniciar aplicación
	@echo "$(YELLOW)Reiniciando aplicación...$(NC)"
	docker-compose restart

dev-logs:  ## Ver logs de la aplicación
	docker-compose logs -f

# =============================================================================
# Documentación
# =============================================================================

docs:  ## Ver documentación de herramientas
	@echo "$(GREEN)Documentación de herramientas:$(NC)"
	@echo ""
	@echo "$(YELLOW)Ruff:$(NC) https://docs.astral.sh/ruff/"
	@echo "$(YELLOW)Black:$(NC) https://black.readthedocs.io/"
	@echo "$(YELLOW)MyPy:$(NC) https://mypy.readthedocs.io/"
	@echo "$(YELLOW)Bandit:$(NC) https://bandit.readthedocs.io/"
	@echo "$(YELLOW)Pytest:$(NC) https://docs.pytest.org/"
	@echo "$(YELLOW)Pre-commit:$(NC) https://pre-commit.com/"
	@echo ""

# =============================================================================
# Default
# =============================================================================

.DEFAULT_GOAL := help
