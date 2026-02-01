# 🔒 Validadores de Seguridad - Guía Completa

## 📊 Resumen de Validadores Configurados

### ✅ Validadores Activos (Automáticos)

| Herramienta            | Tipo               | Velocidad | Configuración | Estado    |
| ---------------------- | ------------------ | --------- | ------------- | --------- |
| **Bandit**             | Seguridad Python   | Rápida    | Automática    | ✅ Activo |
| **Gitleaks**           | Secrets            | Rápida    | Automática    | ✅ Activo |
| **Semgrep**            | Seguridad Estática | Media     | Automática    | ✅ Activo |
| **detect-private-key** | Claves Privadas    | Rápida    | Automática    | ✅ Activo |

### ⚠️ Validadores Opcionales (Requieren Configuración)

| Herramienta              | Tipo                  | Velocidad | Requisito   | Estado        |
| ------------------------ | --------------------- | --------- | ----------- | ------------- |
| **Solvent**              | IA Seguridad          | Lenta     | API Key     | ⚠️ Comentario |
| **NVIDIA Garak**         | LLM/RAG Security      | Lenta     | Instalación | ⚠️ Comentario |
| **RAG Security Scanner** | LLM/RAG Security      | Media     | Instalación | ⚠️ Comentario |
| **LLM Security Checker** | LLM Endpoint Security | Media     | Instalación | ⚠️ Comentario |

---

## 🛠️ Comandos Disponibles

### Validaciones Generales

```bash
# Ejecutar todas las validaciones (incluyendo estilo)
make check-all
./scripts/validate.sh

# Ejecutar solo validaciones de seguridad
make security-scan
./scripts/validate-security.sh

# Ejecutar solo validaciones de seguridad LLM/RAG
make llm-security
./scripts/validate-llm-security.sh

# Validaciones estrictas como en servidor
make validate-server
```

### Validaciones Individuales

```bash
# Linter y Formatter
make lint          # Ruff con auto-fix
make format        # Ruff format
make format-check  # Verificar formateo sin modificar

# Type Checking
make type-check    # MyPy

# Seguridad
make security      # Bandit
make security-scan # Todos los security checks
make llm-security # LLM/RAG security checks

# Testing
make test          # Pytest
make test-cov      # Pytest con cobertura
make test-fast     # Tests rápidos (sin slow)
```

---

## 🤖 Validadores LLM/RAG

### NVIDIA Garak

**Descripción:** Scanner de vulnerabilidades para LLM/RAG desarrollado por NVIDIA

**Instalación:**

```bash
pip install garak
```

**Uso:**

```bash
# Ejecutar scan básico
garak

# Ejecutar scan con verbose
garak --verbose

# Ejecutar scan específico
garak --model gpt-4 --probes prompt_injection
```

**Detecta:**

- Prompt injection
- Data exfiltration
- Hallucinations
- Bias y fairness
- Security vulnerabilities

**Más información:** https://github.com/NVIDIA/garak

---

### RAG Security Scanner

**Descripción:** Scanner de seguridad para sistemas RAG (Retrieval Augmented Generation)

**Instalación:**

```bash
pip install git+https://github.com/olegnazarov/rag-security-scanner.git
```

**Uso:**

```bash
# Ejecutar scan
rag_security_scanner scan

# Scan específico
rag_security_scanner scan --directory ./src
```

**Detecta:**

- RAG injection
- Unauthorized data access
- Information leakage
- Prompt injection in retrieval

**Más información:** https://github.com/olegnazarov/rag-security-scanner

---

### LLM Security Checker

**Descripción:** Herramienta de evaluación de seguridad para endpoints LLM

**Instalación:**

```bash
pip install git+https://github.com/bolbolabadi/llm-security-checker.git
```

**Uso:**

```bash
# Ejecutar evaluación
llm_security_checker

# Evaluación con configuración específica
llm_security_checker --url https://api.openai.com/v1/completions
```

**Detecta:**

- Prompt injection (371 attack payloads)
- Data exfiltration
- 100+ prompt injection variants
- 13 security tests
- Parallel scanning

**Más información:** https://github.com/bolbolabadi/llm-security-checker

---

## 🤖 Cómo Activar Validadores LLM/RAG

### Opción 1: Usar Scripts Manualmente

```bash
# Ejecutar validación LLM/RAG
./scripts/validate-llm-security.sh

# O usar Make
make llm-security
```

### Opción 2: Activar en Pre-commit

Descomentar las secciones correspondientes en `.pre-commit-config.yaml`:

```yaml
# NVIDIA Garak
- repo: local
  hooks:
    - id: garak-check
      name: Garak LLM Security Scanner
      entry: bash -c 'pip show garak > /dev/null 2>&1 || pip install garak; garak --verbose'
      language: system
      pass_filenames: false
      stages: [pre-commit]

# RAG Security Scanner
- repo: local
  hooks:
    - id: rag-security-check
      name: RAG Security Scanner
      entry: bash -c 'python3 -m pip show rag-security-scanner > /dev/null 2>&1 || pip install git+https://github.com/olegnazarov/rag-security-scanner.git; rag_security_scanner scan'
      language: system
      pass_filenames: false
      stages: [pre-commit]
```

Luego reinstalar hooks:

```bash
pre-commit install
```

---

## 🤖 Solvent (Revisión de Seguridad con IA)

### Instalación

```bash
pip install solvent
```

### Configuración

Elegir y configurar una API key:

```bash
# Opción A: OpenAI (GPT-4)
export OPENAI_API_KEY="sk-..."

# Opción B: Anthropic (Claude)
export ANTHROPIC_API_KEY="sk-ant-..."

# Opción C: Google Gemini
export GEMINI_API_KEY="..."

# Opción D: Otros proveedores
export AZURE_OPENAI_API_KEY="..."
export COHERE_API_KEY="..."
```

### Activación en Pre-commit

Descomentar en `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/mbocevski/solvent
  rev: v0.1.0
  hooks:
    - id: solvent
      args:
        - --model=gpt-4o-mini # o claude-3-haiku, gemini-flash, etc.
        - --severity=critical
```

Reinstalar hooks:

```bash
pre-commit install
```

### Modelos Disponibles

- `gpt-4o` - OpenAI GPT-4o (más potente)
- `gpt-4o-mini` - OpenAI GPT-4o mini (más rápido)
- `claude-3-opus` - Anthropic Claude 3 Opus
- `claude-3-haiku` - Anthropic Claude 3 Haiku (rápido)
- `gemini-flash` - Google Gemini Flash
- `deepseek` - DeepSeek

**Más información:** https://github.com/mbocevski/solvent

---

## 📊 Comparativo de Herramientas

| Herramienta              | Tipo     | Velocidad | Configuración | Costo  | Estado      |
| ------------------------ | -------- | --------- | ------------- | ------ | ----------- |
| **Bandit**               | Python   | Rápida    | Automática    | Gratis | ✅ Activo   |
| **Gitleaks**             | Secrets  | Rápida    | Automática    | Gratis | ✅ Activo   |
| **Semgrep**              | Estática | Media     | Automática    | Gratis | ✅ Activo   |
| **detect-private-key**   | Secrets  | Rápida    | Automática    | Gratis | ✅ Activo   |
| **Solvent**              | IA       | Lenta     | API Key       | API    | ⚠️ Opcional |
| **NVIDIA Garak**         | LLM/RAG  | Lenta     | Instalación   | Gratis | ⚠️ Opcional |
| **RAG Security Scanner** | LLM/RAG  | Media     | Instalación   | Gratis | ⚠️ Opcional |
| **LLM Security Checker** | LLM      | Media     | Instalación   | Gratis | ⚠️ Opcional |

---

## 🔄 Flujo de Trabajo Recomendado

### Para Proyectos Generales (sin LLM/RAG)

```bash
# 1. Editar archivos
vim archivo.py

# 2. Validar antes de commitear
make check-all
# o
./scripts/validate.sh

# 3. Si todo pasa, commitear
git add .
git commit -m "mi cambio"
# Pre-commit se ejecuta automáticamente
```

### Para Proyectos con LLM/RAG

```bash
# 1. Editar archivos
vim archivo_llm.py

# 2. Validar antes de commitear
make check-all          # Validaciones generales
make llm-security       # Validaciones LLM/RAG
# o
./scripts/validate-llm-security.sh

# 3. Si todo pasa, commitear
git add .
git commit -m "mi cambio"
```

### Para Commits Urgentes (Saltar Validaciones)

```bash
# Saltar pre-commit hooks
git commit --no-verify -m "hotfix: urgente"

# ⚠️ No recomendado excepto en emergencias
```

---

## 📖 Recursos Adicionales

### Documentación

- **Pre-commit:** https://pre-commit.com/
- **Bandit:** https://bandit.readthedocs.io/
- **Gitleaks:** https://github.com/gitleaks/gitleaks
- **Semgrep:** https://semgrep.dev/
- **Ruff:** https://docs.astral.sh/ruff/

### Seguridad Python

- **OWASP Python Security:** https://owasp.org/www-project-python-security/
- **CWE Top 25:** https://cwe.mitre.org/top25/

### Seguridad LLM/RAG

- **OWASP LLM Top 10:** https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **NVIDIA Garak:** https://github.com/NVIDIA/garak

---

## 🆘 Troubleshooting

### Solvent: API Key Error

```bash
# Verificar que la API key esté configurada
echo $OPENAI_API_KEY
echo $ANTHROPIC_API_KEY

# Configurar temporalmente
export OPENAI_API_KEY="sk-..."
```

### Garak: Installation Error

```bash
# Instalar manualmente
pip install garak

# Verificar instalación
garak --version
```

### Pre-commit: Hook Not Found

```bash
# Reinstalar hooks
pre-commit uninstall
pre-commit install

# Verificar hooks instalados
ls .git/hooks/
```

### Slow Pre-commit Hooks

```bash
# Desactivar hooks lentos (LLM/RAG, Solvent)
# Comentarlos en .pre-commit-config.yaml

# O ejecutar solo cuando sea necesario
make llm-security  # Ejecutar manualmente
```

---

## 📝 Notas

1. **Validadores LLM/RAG** son opcionales y solo necesarios si tu proyecto usa LLM/RAG
2. **Solvent** requiere API key y tiene costo por uso de la API
3. **Todos los validadores** pueden ejecutarse manualmente con `make` o scripts
4. **Pre-commit hooks** se ejecutan automáticamente antes de cada commit
5. **Para saltar hooks** usar `git commit --no-verify` (no recomendado)
