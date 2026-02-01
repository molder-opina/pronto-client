"""
Model Orchestrator

Orquestador principal que integra clasificación, enrutamiento y ejecución de modelos locales.
"""

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from build.shared.orchestrator.classifier import TaskClassifier, get_classifier
from build.shared.orchestrator.config import TaskType
from build.shared.orchestrator.memory import QdrantMemory, get_memory
from build.shared.orchestrator.ollama_client import OllamaClient, OllamaResponse, get_ollama_client
from build.shared.orchestrator.router import ModelRouter, RoutingDecision, get_router


@dataclass
class OrchestratedTask:
    """Tarea orquestada completa."""

    id: str
    original_task: str
    task_type: TaskType
    decision: RoutingDecision
    response: OllamaResponse | None
    context: list[str]
    started_at: float
    completed_at: float | None
    success: bool
    error: str | None


class ModelOrchestrator:
    """
    Orquestador de modelos locales.

    Flujo:
    1. Clasificar tarea → tipo y confianza
    2. Enrutar → mejor modelo para el tipo
    3. Ejecutar → llamada al modelo
    4.记忆 → almacenar contexto en Qdrant
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        qdrant_url: str = "http://localhost:6333",
        collection: str = "ollama_memory",
        embedding_model: str = "nomic-embed-text:latest",
        prefer_speed: bool = False,
        prefer_quality: bool = False,
    ):
        self.classifier = get_classifier()
        self.router = get_router(prefer_speed=prefer_speed, prefer_quality=prefer_quality)
        self.ollama = get_ollama_client(ollama_url)
        self.memory = get_memory(qdrant_url, collection)
        self.embedding_model = embedding_model

        # Historial de tareas
        self.task_history: list[OrchestratedTask] = []

    async def execute(
        self,
        task: str,
        system_prompt: str | None = None,
        context: list[str] | None = None,
        store_memory: bool = True,
        retrieve_context: bool = True,
    ) -> OrchestratedTask:
        """
        Ejecuta una tarea completa con orquestación.

        Args:
            task: Descripción de la tarea
            system_prompt: Prompt del sistema (opcional)
            context: Contexto adicional (opcional)
            store_memory: Si almacenar en memoria
            retrieve_context: Si recuperar contexto relevante

        Returns:
            OrchestratedTask con resultado
        """
        import uuid

        started_at = __import__("time").time()
        task_id = str(uuid.uuid4())[:8]

        # 1. Clasificar tarea
        task_type, confidence = self.classifier.classify(task)

        # 2. Enrutar al mejor modelo
        decision = self.router.route(task, task_type, confidence)

        # 3. Recuperar contexto si necesario
        retrieved_context = []
        if retrieve_context:
            retrieved_context = await self._retrieve_context(task)

        # 4. Construir mensajes
        messages = self._build_messages(
            task=task,
            system_prompt=system_prompt,
            context=context,
            retrieved_context=retrieved_context,
            decision=decision,
        )

        # 5. Ejecutar con el modelo seleccionado
        response = None
        error = None
        success = True

        try:
            response = await self.ollama.complete(
                model=decision.model_id,
                messages=messages,
                temperature=0.3 if task_type == TaskType.CODING else 0.7,
            )
        except Exception as e:
            error = str(e)
            success = False

        completed_at = __import__("time").time()

        # 6. Almacenar en memoria si exitoso
        if success and store_memory and response:
            await self._store_context(task, response.content, decision)

        # Crear resultado
        result = OrchestratedTask(
            id=task_id,
            original_task=task,
            task_type=task_type,
            decision=decision,
            response=response,
            context=retrieved_context,
            started_at=started_at,
            completed_at=completed_at,
            success=success,
            error=error,
        )

        self.task_history.append(result)
        return result

    async def execute_streaming(
        self, task: str, system_prompt: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """
        Ejecuta tarea con respuesta en streaming.

        Yields:
            Diccionarios con chunks de respuesta y metadatos
        """
        task_type, confidence = self.classifier.classify(task)
        decision = self.router.route(task, task_type, confidence)

        messages = self._build_messages(task=task, system_prompt=system_prompt, decision=decision)

        # Yield metadata primero
        yield {
            "type": "metadata",
            "model": decision.model_id,
            "model_name": decision.model_name,
            "task_type": task_type.value,
            "reasoning": decision.reasoning,
        }

        # Yield chunks
        async for chunk in self.ollama.complete_streaming(
            model=decision.model_id, messages=messages
        ):
            yield {"type": "content", "chunk": chunk}

        yield {"type": "done"}

    def _build_messages(
        self,
        task: str,
        system_prompt: str | None,
        context: list[str] | None,
        retrieved_context: list[str],
        decision: RoutingDecision,
    ) -> list[dict[str, str]]:
        """Construye lista de mensajes para el modelo."""
        messages = []

        # System prompt
        base_system = f"Eres un asistente especializado en {decision.task_type.value}. "

        if decision.task_type == TaskType.CODING:
            base_system += "Proporciona código limpio, bien documentado y seguro."
        elif decision.task_type == TaskType.REASONING:
            base_system += "Analiza paso a paso con lógica clara."
        else:
            base_system += "Responde de forma clara y concisa."

        if system_prompt:
            base_system += f" {system_prompt}"

        # Instruction for addressing user by name if profile info is available
        base_system += " Si en el contexto se encuentra una entrada de tipo 'profile' con la clave 'name', dirígete siempre al usuario por ese nombre."

        messages.append({"role": "system", "content": base_system})

        # Contexto recuperado
        if retrieved_context:
            context_text = "Contexto relevante de conversaciones anteriores:\n"
            for i, ctx in enumerate(retrieved_context, 1):
                context_text += f"[{i}] {ctx}\n"
            messages.append({"role": "system", "content": context_text})

        # Contexto adicional
        if context:
            context_text = "Contexto adicional:\n" + "\n".join(context)
            messages.append({"role": "system", "content": context_text})

        # Tarea principal
        messages.append({"role": "user", "content": task})

        return messages

    async def _retrieve_context(self, query: str) -> list[str]:
        """Recupera contexto relevante de la memoria."""
        try:
            # Generar embedding
            embeddings = await self.ollama.embed(model=self.embedding_model, texts=[query])

            # Buscar en Qdrant
            results = await self.memory.search(
                query_embedding=embeddings[0], limit=3, score_threshold=0.6
            )

            return [r.content for r in results]

        except Exception:
            return []

    async def _store_context(self, task: str, response: str, decision: RoutingDecision) -> None:
        """Almacena el contexto de la conversación."""
        try:
            full_content = f"Tarea: {task}\nRespuesta: {response}"

            embeddings = await self.ollama.embed(model=self.embedding_model, texts=[full_content])

            await self.memory.add(
                content=full_content,
                embedding=embeddings[0],
                metadata={"task_type": decision.task_type.value, "model": decision.model_id},
            )

        except Exception:
            pass  # Silenciosamente fallar si no se puede almacenar

    def get_stats(self) -> dict:
        """Obtiene estadísticas del orquestador."""
        total = len(self.task_history)
        successful = sum(1 for t in self.task_history if t.success)
        failed = total - successful

        by_type = {}
        for task in self.task_history:
            ttype = task.task_type.value
            if ttype not in by_type:
                by_type[ttype] = {"total": 0, "success": 0, "avg_time": 0}
            by_type[ttype]["total"] += 1
            if task.success:
                by_type[ttype]["success"] += 1

        return {
            "total_tasks": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "by_task_type": by_type,
            "models_used": list(set(t.decision.model_id for t in self.task_history)),
        }

    def list_models(self) -> list[dict]:
        """Lista modelos disponibles."""
        return self.router.get_available_models()

    async def health_check(self) -> dict:
        """Verifica salud de todos los servicios."""
        ollama_healthy = await self.ollama.check_health()

        return {
            "ollama": {"healthy": ollama_healthy, "url": self.ollama.base_url},
            "models": await self.ollama.list_models() if ollama_healthy else [],
            "memory": {
                "connected": False,
                "url": self.memory.url,
                "collection": self.memory.collection,
            },
        }


# Instancia global
_orchestrator: ModelOrchestrator | None = None


def get_orchestrator(
    ollama_url: str = "http://localhost:11434",
    qdrant_url: str = "http://localhost:6333",
    prefer_speed: bool = False,
    prefer_quality: bool = False,
) -> ModelOrchestrator:
    """Obtiene la instancia global del orquestador."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ModelOrchestrator(
            ollama_url=ollama_url,
            qdrant_url=qdrant_url,
            prefer_speed=prefer_speed,
            prefer_quality=prefer_quality,
        )
    return _orchestrator
