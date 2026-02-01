"""
Configuración del Orquestador de Modelos Locales

Define los modelos disponibles, sus capacidades y características.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class TaskType(Enum):
    """Tipos de tareas que el orquestador puede manejar."""

    CODING = "coding"
    REASONING = "reasoning"
    EXPLORATION = "exploration"
    WRITING = "writing"
    SIMPLE = "simple"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    RESEARCH = "research"


@dataclass
class ModelCapabilities:
    """Capacidades de un modelo."""

    max_tokens: int
    context_window: int
    strengths: list[str]
    weaknesses: list[str]
    speed_rating: float  # 1-10 (10 = fastest)
    quality_rating: float  # 1-10
    memory_usage_gb: float


@dataclass
class LocalModel:
    """Modelo local configurado."""

    name: str
    model_id: str
    provider: str
    capabilities: ModelCapabilities
    is_embedding: bool = False
    dimensions: int | None = None


# Configuración de modelos locales (Ollama)
LOCAL_MODELS = {
    "llama3.1:8b-instruct-q4_K_M": LocalModel(
        name="Llama 3.1 8B",
        model_id="llama3.1:8b-instruct-q4_K_M",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=131072,
            strengths=["general_purpose", "fast_inference", "english", "coding_basic"],
            weaknesses=["deep_reasoning", "large_context"],
            speed_rating=9,
            quality_rating=7,
            memory_usage_gb=8,
        ),
    ),
    "qwen2.5:14b-instruct-q4_K_M": LocalModel(
        name="Qwen 2.5 14B",
        model_id="qwen2.5:14b-instruct-q4_K_M",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=131072,
            strengths=["reasoning", "analysis", "coding", "multilingual", "math"],
            weaknesses=["creative_writing"],
            speed_rating=6,
            quality_rating=8.5,
            memory_usage_gb=14,
        ),
    ),
    "qwen2.5-coder:7b-instruct-q4_K_M": LocalModel(
        name="Qwen 2.5 Coder 7B",
        model_id="qwen2.5-coder:7b-instruct-q4_K_M",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=131072,
            strengths=["coding", "code_analysis", "refactoring", "debugging"],
            weaknesses=["creative_writing", "simple_conversation"],
            speed_rating=8,
            quality_rating=8,
            memory_usage_gb=7,
        ),
    ),
    "ministral-3:8b": LocalModel(
        name="Ministral 3 8B",
        model_id="ministral-3:8b",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=131072,
            strengths=["general_purpose", "balanced"],
            weaknesses=["specialized_tasks"],
            speed_rating=7,
            quality_rating=7.5,
            memory_usage_gb=8,
        ),
    ),
}

# Modelos de embedding
EMBEDDING_MODELS = {
    "nomic-embed-text:latest": LocalModel(
        name="Nomic Embed Text",
        model_id="nomic-embed-text:latest",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=8192,
            strengths=["code", "text", "fast"],
            weaknesses=[],
            speed_rating=9,
            quality_rating=7.5,
            memory_usage_gb=1,
        ),
        is_embedding=True,
        dimensions=768,
    ),
    "mxbai-embed-large:latest": LocalModel(
        name="Mxbai Embed Large",
        model_id="mxbai-embed-large:latest",
        provider="ollama",
        capabilities=ModelCapabilities(
            max_tokens=8192,
            context_window=8192,
            strengths=["high_quality", "semantic"],
            weaknesses=["slower"],
            speed_rating=6,
            quality_rating=8.5,
            memory_usage_gb=2,
        ),
        is_embedding=True,
        dimensions=1024,
    ),
}

# Reglas de enrutamiento por tipo de tarea
ROUTING_RULES: dict[TaskType, list[str]] = {
    TaskType.CODING: [
        "qwen2.5-coder:7b-instruct-q4_K_M",  # Mejor para código
        "qwen2.5:14b-instruct-q4_K_M",
        "llama3.1:8b-instruct-q4_K_M",
    ],
    TaskType.REASONING: [
        "qwen2.5:14b-instruct-q4_K_M",  # Mejor razonamiento
        "ministral-3:8b",
        "llama3.1:8b-instruct-q4_K_M",
    ],
    TaskType.EXPLORATION: [
        "llama3.1:8b-instruct-q4_K_M",  # Rápido para grep/search
        "qwen2.5:14b-instruct-q4_K_M",
        "qwen2.5-coder:7b-instruct-q4_K_M",
    ],
    TaskType.WRITING: [
        "llama3.1:8b-instruct-q4_K_M",
        "ministral-3:8b",
        "qwen2.5:14b-instruct-q4_K_M",
    ],
    TaskType.SIMPLE: [
        "llama3.1:8b-instruct-q4_K_M",  # Rápido para tareas simples
        "ministral-3:8b",
    ],
    TaskType.ANALYSIS: [
        "qwen2.5:14b-instruct-q4_K_M",  # Mejor análisis
        "ministral-3:8b",
        "llama3.1:8b-instruct-q4_K_M",
    ],
    TaskType.CREATIVE: ["llama3.1:8b-instruct-q4_K_M", "ministral-3:8b"],
    TaskType.RESEARCH: [
        "qwen2.5:14b-instruct-q4_K_M",
        "llama3.1:8b-instruct-q4_K_M",
        "qwen2.5-coder:7b-instruct-q4_K_M",
    ],
}

# Palabras clave para clasificación de tareas
TASK_KEYWORDS: dict[TaskType, list[str]] = {
    TaskType.CODING: [
        "code",
        "implement",
        "function",
        "class",
        "debug",
        "refactor",
        "api",
        "endpoint",
        "database",
        "query",
        "script",
        "test",
    ],
    TaskType.REASONING: [
        "analyze",
        "reason",
        "logic",
        "solve",
        "problem",
        "decision",
        "strategy",
        "evaluate",
        "compare",
        "improve",
    ],
    TaskType.EXPLORATION: [
        "find",
        "search",
        "grep",
        "locate",
        "where",
        "look",
        "explore",
        "list",
        "show",
        "get",
        "retrieve",
    ],
    TaskType.WRITING: [
        "write",
        "document",
        "explain",
        "describe",
        "summarize",
        "create",
        "generate",
        "compose",
        "draft",
    ],
    TaskType.SIMPLE: ["what", "how", "why", "is", "are", "does", "calculate", "convert"],
    TaskType.ANALYSIS: [
        "analyze",
        "review",
        "audit",
        "assess",
        "examine",
        "investigate",
        "profile",
        "metrics",
        "statistics",
    ],
    TaskType.CREATIVE: [
        "creative",
        "story",
        "poem",
        "design",
        "brainstorm",
        "idea",
        "concept",
        "innovative",
    ],
    TaskType.RESEARCH: [
        "research",
        "investigate",
        "study",
        "learn",
        "understand",
        "explain",
        "compare",
        "difference",
        "versus",
    ],
}
