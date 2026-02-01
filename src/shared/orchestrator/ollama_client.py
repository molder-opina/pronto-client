"""
Ollama Client

Cliente para interactuar con modelos locales vía API OpenAI-compatible.
"""

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx


@dataclass
class OllamaResponse:
    """Respuesta de Ollama."""

    content: str
    model: str
    tokens: int
    finish_reason: str


class OllamaClient:
    """Cliente para Ollama con API compatible con OpenAI."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.chat_endpoint = f"{base_url}/v1/chat/completions"
        self.embeddings_endpoint = f"{base_url}/v1/embeddings"
        self.tags_endpoint = f"{base_url}/api/tags"

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> OllamaResponse:
        """
        Genera completación usando Ollama.

        Args:
            model: ID del modelo
            messages: Mensajes en formato OpenAI
            temperature: Temperatura de generación
            max_tokens: Máximo de tokens
            stream: Si es streaming

        Returns:
            OllamaResponse
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.chat_endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            return OllamaResponse(
                content=choice["message"]["content"],
                model=data["model"],
                tokens=data["usage"]["total_tokens"],
                finish_reason=choice["finish_reason"],
            )

    async def complete_streaming(
        self, model: str, messages: list[dict[str, str]], temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Genera completación en streaming.

        Yields:
            Chunks de contenido
        """
        payload = {"model": model, "messages": messages, "temperature": temperature, "stream": True}

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", self.chat_endpoint, json=payload) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        data = json.loads(chunk)
                        if "choices" in data:
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content

    async def embed(
        self, model: str, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """
        Genera embeddings usando modelo de embedding.

        Args:
            model: ID del modelo de embedding
            texts: Lista de textos a embeber
            dimensions: Dimensiones deseadas (opcional)

        Returns:
            Lista de vectores de embedding
        """
        payload = {
            "model": model,
            "input": texts,
        }

        if dimensions:
            payload["dimensions"] = dimensions

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(self.embeddings_endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

            return [item["embedding"] for item in data["data"]]

    async def list_models(self) -> list[dict]:
        """Lista modelos disponibles en Ollama."""
        async with httpx.AsyncClient() as client:
            response = await client.get(self.tags_endpoint)
            response.raise_for_status()
            data = response.json()

            return [
                {
                    "name": m["name"],
                    "size": m.get("size", 0),
                    "digest": m.get("digest", ""),
                }
                for m in data.get("models", [])
            ]

    async def check_health(self) -> bool:
        """Verifica si Ollama está disponible."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.tags_endpoint, timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False


# Instancia global del cliente
_ollama_client: OllamaClient | None = None


def get_ollama_client(base_url: str = "http://localhost:11434") -> OllamaClient:
    """Obtiene la instancia global del cliente Ollama."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient(base_url)
    return _ollama_client
