"""
Model Router

Selecciona el modelo óptimo basándose en criterios de rendimiento, costo y calidad.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from build.shared.orchestrator.config import LOCAL_MODELS, ROUTING_RULES, LocalModel, TaskType


@dataclass
class RoutingDecision:
    """Decisión de enrutamiento."""

    model_id: str
    model_name: str
    task_type: TaskType
    reasoning: str
    confidence: float
    estimated_time_ms: float


class ModelRouter:
    """Router inteligente de modelos locales."""

    def __init__(
        self, prefer_speed: bool = False, prefer_quality: bool = False, allow_fallback: bool = True
    ):
        self.prefer_speed = prefer_speed
        self.prefer_quality = prefer_quality
        self.allow_fallback = allow_fallback
        self.models = LOCAL_MODELS
        self.routing_rules = ROUTING_RULES

    def route(self, task: str, task_type: TaskType, confidence: float = 0.5) -> RoutingDecision:
        """
        Determina el mejor modelo para una tarea.

        Args:
            task: Descripción de la tarea
            task_type: Tipo de tarea clasificado
            confidence: Confianza de la clasificación

        Returns:
            RoutingDecision con el modelo seleccionado
        """
        # Obtener candidatos para este tipo de tarea
        candidates = self.routing_rules.get(task_type, list(self.models.keys()))

        # Filtrar modelos disponibles
        available = [m for m in candidates if m in self.models]

        if not available:
            available = list(self.models.keys())

        # Aplicar estrategia de selección
        if self.prefer_quality:
            selected = self._select_by_quality(available)
        elif self.prefer_speed:
            selected = self._select_by_speed(available)
        else:
            selected = self._select_balanced(available, task_type, confidence)

        model = self.models[selected]

        # Calcular tiempo estimado
        estimated_time = self._estimate_inference_time(model, task)

        return RoutingDecision(
            model_id=model.model_id,
            model_name=model.name,
            task_type=task_type,
            reasoning=self._get_reasoning(task_type, model),
            confidence=confidence,
            estimated_time_ms=estimated_time,
        )

    def _select_by_quality(self, candidates: list[str]) -> str:
        """Selecciona el modelo de mayor calidad."""
        return max(candidates, key=lambda m: self.models[m].capabilities.quality_rating)

    def _select_by_speed(self, candidates: list[str]) -> str:
        """Selecciona el modelo más rápido."""
        return max(candidates, key=lambda m: self.models[m].capabilities.speed_rating)

    def _select_balanced(
        self, candidates: list[str], task_type: TaskType, confidence: float
    ) -> str:
        """Selección balanceada basada en el tipo de tarea."""
        scores = {}

        for model_id in candidates:
            model = self.models[model_id]
            score = 0.0

            # Calidad del modelo (40%)
            score += model.capabilities.quality_rating * 0.4

            # Velocidad (30%)
            score += model.capabilities.speed_rating * 0.3

            # Compatibilidad con tipo de tarea (20%)
            task_compatibility = self._get_task_compatibility(model_id, task_type)
            score += task_compatibility * 0.2

            # Bonus por confianza baja (usar modelo más capaz)
            if confidence < 0.5:
                score += model.capabilities.quality_rating * 0.1

            scores[model_id] = score

        return max(scores, key=scores.get)

    def _get_task_compatibility(self, model_id: str, task_type: TaskType) -> float:
        """Calcula compatibilidad modelo-tarea."""
        model = self.models.get(model_id)
        if not model:
            return 0.0

        strengths = model.capabilities.strengths
        task_strengths = {
            TaskType.CODING: ["coding"],
            TaskType.REASONING: ["reasoning", "analysis", "math"],
            TaskType.EXPLORATION: ["fast_inference"],
            TaskType.WRITING: ["general_purpose"],
            TaskType.SIMPLE: ["fast_inference", "general_purpose"],
            TaskType.ANALYSIS: ["reasoning", "analysis"],
            TaskType.CREATIVE: ["general_purpose"],
            TaskType.RESEARCH: ["reasoning", "analysis", "multilingual"],
        }

        relevant = task_strengths.get(task_type, [])
        matches = sum(1 for s in strengths if s in relevant)
        return matches / max(len(relevant), 1)

    def _estimate_inference_time(self, model: LocalModel, task: str) -> float:
        """Estima tiempo de inferencia en milisegundos."""
        # Estimación base basada en velocidad y longitud
        base_time = 1000  # 1 segundo base
        token_count = len(task.split()) * 1.3  # Estimación de tokens

        # Ajustar por velocidad del modelo (más rápido = menor tiempo)
        speed_factor = 10 / model.capabilities.speed_rating

        return base_time * speed_factor * (token_count / 100)

    def _get_reasoning(self, task_type: TaskType, model: LocalModel) -> str:
        """Genera explicación de la decisión."""
        reasons = {
            TaskType.CODING: f"Mejor para código: {', '.join(model.capabilities.strengths[:3])}",
            TaskType.REASONING: f"Alta capacidad de razonamiento: {model.capabilities.quality_rating}/10",
            TaskType.EXPLORATION: f"Respuesta rápida ({model.capabilities.speed_rating}/10) para exploración",
            TaskType.WRITING: f"Buenas capacidades de generación: {model.capabilities.quality_rating}/10",
            TaskType.SIMPLE: f"Modelo rápido y eficiente para consultas simples",
            TaskType.ANALYSIS: f"Excelente para análisis: {model.capabilities.strengths[:2]}",
            TaskType.CREATIVE: f"Balanceado para tareas creativas",
            TaskType.RESEARCH: f"Bueno para investigación y comparación",
        }
        return reasons.get(task_type, "Modelo de uso general")

    def get_available_models(self) -> list[dict]:
        """Lista modelos disponibles con sus características."""
        return [
            {
                "id": m.model_id,
                "name": m.name,
                "provider": m.provider,
                "speed": m.capabilities.speed_rating,
                "quality": m.capabilities.quality_rating,
                "strengths": m.capabilities.strengths,
                "memory_gb": m.capabilities.memory_usage_gb,
            }
            for m in self.models.values()
        ]

    def check_model_health(self, model_id: str) -> bool:
        """Verifica si un modelo está disponible."""
        # Aquí se integraría con Ollama para verificar disponibilidad
        return model_id in self.models


# Instancia global del router
_model_router: ModelRouter | None = None


def get_router(prefer_speed: bool = False, prefer_quality: bool = False) -> ModelRouter:
    """Obtiene la instancia global del router."""
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter(prefer_speed=prefer_speed, prefer_quality=prefer_quality)
    return _model_router
