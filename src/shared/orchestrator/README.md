# Model Orchestrator - Orquestador de Modelos Locales

Sistema de orquestación inteligente para modelos locales de Ollama, similar a lo que hace OpenCode pero específico para tus modelos.

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                     Model Orchestrator                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Classifier │───▶│    Router    │───▶│  Ollama Client   │   │
│  │  (Tarea→Tipo)│    │ (Tipo→Modelo)│    │  (Ejecución)     │   │
│  └─────────────┘    └──────────────┘    └──────────────────┘   │
│                                                 │               │
│                                                 ▼               │
│                                          ┌──────────────┐      │
│                                          │   Qdrant     │      │
│                                          │   Memory     │      │
│                                          └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. Classifier (`config.py` + `classifier.py`)

Clasifica tareas en categorías:

- **CODING**: Code, implement, debug, refactor
- **REASONING**: Analyze, solve, decide, strategy
- **EXPLORATION**: Find, search, grep, locate
- **WRITING**: Write, document, explain
- **SIMPLE**: What, how, calculate
- **ANALYSIS**: Review, audit, assess
- **CREATIVE**: Story, design, brainstorm
- **RESEARCH**: Research, compare, investigate

### 2. Router (`router.py`)

Selecciona el modelo óptimo basado en:

- Compatibilidad tarea-modelo (20%)
- Calidad del modelo (40%)
- Velocidad (30%)
- Confianza de clasificación (10%)

### 3. Ollama Client (`ollama_client.py`)

Cliente async con API OpenAI-compatible para:

- Completaciones
- Streaming
- Embeddings

### 4. Memory (`memory.py`)

Integración con Qdrant para:

- Almacenar conversaciones
- Recuperar contexto relevante
- Búsqueda semántica

## Modelos Configurados

| Modelo                             | Velocidad | Calidad | Uso                         |
| ---------------------------------- | --------- | ------- | --------------------------- |
| `llama3.1:8b-instruct-q4_K_M`      | 9/10      | 7/10    | Tareas rápidas, exploración |
| `qwen2.5:14b-instruct-q4_K_M`      | 6/10      | 8.5/10  | Razonamiento, análisis      |
| `qwen2.5-coder:7b-instruct-q4_K_M` | 8/10      | 8/10    | Coding, debugging           |
| `ministral-3:8b`                   | 7/10      | 7.5/10  | Propósito general           |

## Instalación

```bash
# Asegúrate de tener las dependencias
pip install httpx

# Hacer el CLI ejecutable
chmod +x build/shared/orchestrator/cli.py
```

## Uso

### CLI Basic

```bash
# Ejecutar una tarea
python build/shared/orchestrator/cli.py "Find all Python files in the project"

# Con streaming
python build/shared/orchestrator/cli.py "Write a function to calculate fibonacci" --stream

# Con preferencia de velocidad
python build/shared/orchestrator/cli.py "List all imports" --speed

# Con preferencia de calidad
python build/shared/orchestrator/cli.py "Design a database schema" --quality

# Ver modelos disponibles
python build/shared/orchestrator/cli.py --models

# Ver estado de salud
python build/shared/orchestrator/cli.py --health
```

### Como Biblioteca

```python
import asyncio
from build.shared.orchestrator import get_orchestrator

async def main():
    orchestrator = get_orchestrator()

    # Ejecutar tarea simple
    result = await orchestrator.execute(
        "Create a Python class for handling API requests"
    )

    print(f"Modelo: {result.decision.model_name}")
    print(f"Tipo: {result.task_type.value}")
    print(f"Respuesta: {result.response.content}")

    # Ver estadísticas
    stats = orchestrator.get_stats()
    print(stats)

asyncio.run(main())
```

### Con Contexto y Memoria

```python
from build.shared.orchestrator import get_orchestrator

async def with_context():
    orchestrator = get_orchestrator()

    # Ejecutar con contexto
    result = await orchestrator.execute(
        task="Why is the database slow?",
        system_prompt="You are a database expert",
        context=["Table has 10M rows", "Index on created_at"],
        store_memory=True,
        retrieve_context=True
    )

    print(result.response.content)

asyncio.run(with_context())
```

### Streaming

```python
async def streaming_example():
    orchestrator = get_orchestrator()

    async for chunk in orchestrator.execute_streaming(
        "Write a comprehensive guide about Python async"
    ):
        if chunk["type"] == "metadata":
            print(f"\n--- Usando: {chunk['model_name']} ---\n")
        elif chunk["type"] == "content":
            print(chunk["chunk"], end="", flush=True)
        elif chunk["type"] == "done":
            print("\n--- Fin ---")

asyncio.run(streaming_example())
```

## Flujo de Decisión

```
Tarea Entrante
      │
      ▼
┌─────────────────┐
│  TaskClassifier │──▶ Coding (70%)
│  (Keywords +    │──▶ Reasoning (20%)
│   Regex)        │──▶ Simple (10%)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   ModelRouter   │
│  (Weighted      │   Qwen 2.5 14B (reasoning)
│   Scoring)      │   Qwen Coder 7B (coding)
         │         │   Llama 3.1 8B (exploration)
         ▼         │
┌─────────────────┤
│  Ollama Client  │────▶ API Call
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Qdrant Memory  │────▶ Store/Retrieve
└─────────────────┘
```

## Configuración

Edita `config.py` para modificar:

```python
# Añadir nuevos modelos
LOCAL_MODELS["nuevo-modelo"] = LocalModel(
    name="Nuevo Modelo",
    model_id="nuevo-modelo:latest",
    provider="ollama",
    capabilities=ModelCapabilities(
        max_tokens=8192,
        context_window=131072,
        strengths=["specialty"],
        weaknesses=[],
        speed_rating=8,
        quality_rating=8,
        memory_usage_gb=8
    )
)

# Modificar reglas de enrutamiento
ROUTING_RULES[TaskType.CODING] = [
    "nuevo-modelo",  # Nuevo modelo para código
    "qwen2.5-coder:7b-instruct-q4_K_M",
]
```

## Ejemplo de Salida

````
$ python build/shared/orchestrator/cli.py "Implement a REST API for user management"

🎯 Tarea: Implement a REST API for user management
============================================================

📌 Modelo Seleccionado: Qwen 2.5 Coder 7B
   Tipo de Tarea: coding
   Confianza: 0.85
   Razón: Mejor para código: coding, code_analysis, refactoring
   Tiempo: 2.34s

📝 Respuesta:
------------------------------------------------------------
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

class User(BaseModel):
    name: str
    email: str
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

# Implementación del API...
````

## Requisitos

- Ollama corriendo en `localhost:11434`
- Qdrant corriendo en `localhost:6333`
- Python 3.11+
- Dependencias: `httpx`

## Verificación

```bash
# Verificar servicios
python build/shared/orchestrator/cli.py --health

# Ver modelos
python build/shared/orchestrator/cli.py --models
```

## Próximos Pasos

1. **Fallback inteligente**: Si un modelo falla, intentar con el siguiente
2. **Cache de respuestas**: Evitar re-procesar tareas similares
3. **Métricas detalladas**: Tiempo real por modelo
4. **API REST**: Exponer como servicio HTTP
5. **Web UI**: Interfaz gráfica para selección de modelos
