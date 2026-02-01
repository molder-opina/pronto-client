"""
Clasificador de Tareas

Analiza las tareas entrantes y determina el tipo apropiado para enrutamiento.
"""

import re
from typing import Dict, List, Optional, Tuple

from build.shared.orchestrator.config import LOCAL_MODELS, TASK_KEYWORDS, TaskType


class TaskClassifier:
    """Clasifica tareas basándose en análisis de contenido."""

    def __init__(self):
        self.task_keywords = TASK_KEYWORDS

    def classify(self, task: str) -> tuple[TaskType, float]:
        """
        Clasifica una tarea y retorna el tipo y confianza.

        Args:
            task: Descripción de la tarea

        Returns:
            Tuple[TaskType, confidence]
        """
        task_lower = task.lower()

        # Calcular puntuaciones por tipo
        scores: dict[TaskType, float] = {}
        for task_type, keywords in self.task_keywords.items():
            score = 0.0
            for keyword in keywords:
                if keyword in task_lower:
                    # Peso mayor para frases más largas
                    if len(keyword) > 4:
                        score += 2.0
                    else:
                        score += 1.0
            scores[task_type] = score

        # Añadir bonus por patrones específicos
        self._apply_pattern_bonus(task_lower, scores)

        # Normalizar puntuaciones
        total = sum(scores.values())
        if total > 0:
            for task_type in scores:
                scores[task_type] /= total

        # Encontrar el tipo con mayor puntuación
        best_type = max(scores, key=scores.get)
        confidence = scores[best_type]

        # Si confianza muy baja, usar SIMPLE como fallback
        if confidence < 0.1:
            return TaskType.SIMPLE, 0.3

        return best_type, confidence

    def _apply_pattern_bonus(self, task_lower: str, scores: dict[TaskType, float]) -> None:
        """Aplica bonus basados en patrones regex."""
        # Patrones de código
        code_patterns = [
            r"def\s+\w+\s*\(",
            r"class\s+\w+",
            r"import\s+\w+",
            r"from\s+\w+",
            r"async\s+def",
            r"@dataclass",
            r"TypeAlias",
            r"Optional\[",
            r"Union\[",
        ]
        for pattern in code_patterns:
            if re.search(pattern, task_lower):
                scores[TaskType.CODING] += 3.0

        # Patrones de análisis
        analysis_patterns = [
            r"performance",
            r"optimiz",
            r"memory",
            r"benchmark",
            r"profile",
        ]
        for pattern in analysis_patterns:
            if re.search(pattern, task_lower):
                scores[TaskType.ANALYSIS] += 2.0

        # Patrones de exploración
        exploration_patterns = [
            r"find\s+all",
            r"search\s+for",
            r"where\s+is",
            r"locate\s+",
            r"grep\s+",
        ]
        for pattern in exploration_patterns:
            if re.search(pattern, task_lower):
                scores[TaskType.EXPLORATION] += 2.5

        # Patrones de investigación
        research_patterns = [
            r"difference\s+between",
            r"vs\.?\s+\w+",
            r"compare",
            r"pros\s+and\s+cons",
            r"best\s+practice",
        ]
        for pattern in research_patterns:
            if re.search(pattern, task_lower):
                scores[TaskType.RESEARCH] += 2.0

    def get_task_complexity(self, task: str) -> str:
        """
        Evalúa la complejidad de una tarea.

        Returns: "low", "medium", o "high"
        """
        task_lower = task.lower()

        # Indicadores de alta complejidad
        high_complexity = [
            r"architectur",
            r"design\s+pattern",
            r"microservice",
            r"distributed",
            r"refactor\w*\s+entire",
            r"create\s+new\s+module",
            r"complex\s+logic",
            r"benchmark",
        ]

        # Indicadores de baja complejidad
        low_complexity = [
            r"^what\s+is",
            r"^how\s+to",
            r"simple",
            r"basic",
            r"fix\s+\w+",
            r"change\s+\w+",
            r"update\s+\w+",
        ]

        for pattern in high_complexity:
            if re.search(pattern, task_lower):
                return "high"

        for pattern in low_complexity:
            if re.search(pattern, task_lower):
                return "low"

        return "medium"

    def suggest_model(
        self, task: str, preferred_type: TaskType | None = None
    ) -> tuple[str, TaskType, float]:
        """
        Sugiere el mejor modelo basándose en la tarea.

        Args:
            task: Descripción de la tarea
            preferred_type: Tipo preferido (opcional)

        Returns:
            Tuple[model_id, task_type, confidence]
        """
        task_type, confidence = self.classify(task)

        # Usar tipo preferido si se especifica
        if preferred_type:
            task_type = preferred_type

        # Obtener modelos recomendados para este tipo
        from build.shared.orchestrator.config import ROUTING_RULES

        recommended_models = ROUTING_RULES.get(task_type, list(LOCAL_MODELS.keys()))

        # Filtrar modelos disponibles
        available_models = [m for m in recommended_models if m in LOCAL_MODELS]

        if not available_models:
            available_models = list(LOCAL_MODELS.keys())

        # Seleccionar el primer modelo disponible
        selected_model = available_models[0]

        return selected_model, task_type, confidence


# Instancia global del clasificador
_task_classifier: TaskClassifier | None = None


def get_classifier() -> TaskClassifier:
    """Obtiene la instancia global del clasificador."""
    global _task_classifier
    if _task_classifier is None:
        _task_classifier = TaskClassifier()
    return _task_classifier
