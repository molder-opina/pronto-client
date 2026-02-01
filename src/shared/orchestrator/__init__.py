"""
Model Orchestrator Package

Orquestador de modelos locales para Ollama con enrutamiento inteligente.
"""

from build.shared.orchestrator.classifier import TaskClassifier, get_classifier
from build.shared.orchestrator.config import EMBEDDING_MODELS, LOCAL_MODELS, TaskType
from build.shared.orchestrator.memory import QdrantMemory, get_memory
from build.shared.orchestrator.ollama_client import OllamaClient, get_ollama_client
from build.shared.orchestrator.orchestrator import (
    ModelOrchestrator,
    OrchestratedTask,
    get_orchestrator,
)
from build.shared.orchestrator.router import ModelRouter, RoutingDecision, get_router

__all__ = [
    "EMBEDDING_MODELS",
    "LOCAL_MODELS",
    "ModelOrchestrator",
    "ModelRouter",
    "OllamaClient",
    "OrchestratedTask",
    "QdrantMemory",
    "RoutingDecision",
    "TaskClassifier",
    "TaskType",
    "get_classifier",
    "get_memory",
    "get_ollama_client",
    "get_orchestrator",
    "get_router",
]
