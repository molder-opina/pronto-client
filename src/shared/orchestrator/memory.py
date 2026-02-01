"""
Memory Store with Qdrant

Almacena y recupera contexto usando Qdrant como vector store.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class MemoryEntry:
    """Entrada de memoria."""

    id: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any]
    created_at: float


class QdrantMemory:
    """Integración con Qdrant para memoria vectorial."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        collection: str = "ollama_memory",
        embedding_model: str = "nomic-embed-text:latest",
        embedding_dimensions: int = 768,
    ):
        self.url = url
        self.collection = collection
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions
        self.client = httpx.AsyncClient()

    async def ensure_collection(self) -> bool:
        """Asegura que la colección existe."""
        check_url = f"{url}/collections/{collection}"

        try:
            response = await self.client.get(check_url)
            if response.status_code == 200:
                return True

            # Crear colección
            create_url = f"{url}/collections/{collection}"
            payload = {"vectors": {"size": self.embedding_dimensions, "distance": "Cosine"}}

            response = await self.client.put(create_url, json=payload)
            return response.status_code in (200, 201)

        except Exception:
            return False

    async def add(
        self, content: str, embedding: list[float], metadata: dict[str, Any] | None = None
    ) -> str:
        """
        Añade una entrada a la memoria.

        Returns:
            ID de la entrada
        """
        import uuid

        entry_id = str(uuid.uuid4())
        payload = {
            "points": [
                {
                    "id": entry_id,
                    "vector": embedding,
                    "payload": {
                        "content": content,
                        "metadata": metadata or {},
                        "created_at": __import__("time").time(),
                    },
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.url}/collections/{self.collection}/points", json=payload
            )
            response.raise_for_status()

        return entry_id

    async def search(
        self, query_embedding: list[float], limit: int = 5, score_threshold: float = 0.7
    ) -> list[MemoryEntry]:
        """
        Busca entradas similares.

        Args:
            query_embedding: Vector de búsqueda
            limit: Número máximo de resultados
            score_threshold: Umbral de similitud

        Returns:
            Lista de entradas ordenadas por relevancia
        """
        payload = {
            "query_vector": query_embedding,
            "limit": limit,
            "score_threshold": score_threshold,
            "with_payload": True,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/collections/{self.collection}/points/search", json=payload
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for point in data.get("result", []):
                results.append(
                    MemoryEntry(
                        id=point["id"],
                        content=point["payload"]["content"],
                        embedding=query_embedding,
                        metadata=point["payload"].get("metadata", {}),
                        created_at=point["payload"].get("created_at", 0),
                    )
                )

            return results

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Recupera una entrada por ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.url}/collections/{self.collection}/points/{entry_id}"
            )
            if response.status_code != 200:
                return None

            data = response.json()
            point = data.get("result", {})
            payload = point.get("payload", {})

            return MemoryEntry(
                id=entry_id,
                content=payload.get("content", ""),
                embedding=[],
                metadata=payload.get("metadata", {}),
                created_at=payload.get("created_at", 0),
            )

    async def delete(self, entry_id: str) -> bool:
        """Elimina una entrada."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.url}/collections/{self.collection}/points/{entry_id}"
            )
            return response.status_code == 200

    async def clear(self) -> bool:
        """Limpia toda la colección."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/collections/{self.collection}/points/delete", json={"filter": {}}
            )
            return response.status_code in (200, 201)

    async def get_stats(self) -> dict[str, Any]:
        """Obtiene estadísticas de la colección."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.url}/collections/{self.collection}")
            if response.status_code != 200:
                return {}

            data = response.json()
            return {
                "points_count": data.get("result", {}).get("points_count", 0),
                "vectors_count": data.get("result", {}).get("vectors_count", 0),
                "status": data.get("result", {}).get("status", "unknown"),
            }


# Instancia global
_qdrant_memory: QdrantMemory | None = None


def get_memory(
    url: str = "http://localhost:6333", collection: str = "ollama_memory"
) -> QdrantMemory:
    """Obtiene la instancia global de memoria."""
    global _qdrant_memory
    if _qdrant_memory is None:
        _qdrant_memory = QdrantMemory(url=url, collection=collection)
    return _qdrant_memory
