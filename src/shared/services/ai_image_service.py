"""AI-powered image generation helpers."""

from __future__ import annotations

import logging
import os
import secrets
from io import BytesIO
from urllib.parse import quote_plus

import requests
from PIL import Image

from .image_service import ImageService

logger = logging.getLogger(__name__)


class AIImageService:
    """Generate or normalize images for menu/content management."""

    FREE_PROVIDER = "pollinations"
    OPENAI_PROVIDER = "openai"
    PROFILE_PROMPTS = [
        "minimalist black and white caricature portrait of a smiling waiter, ink illustration, clean background, high contrast",
        "black and white caricature of a cheerful chef with hat, bold lines, sketchbook style, expressive eyes",
        "grayscale cartoon hostess with ponytail and headset, modern flat illustration, friendly expression",
        "ink drawing of a classy maître d', monochrome, exaggerated features, elegant suit",
        "playful black and white caricature of a young barista, thick outlines, textured shading",
        "hand-drawn monochrome portrait of an experienced waitress, subtle smile, cross-hatching style",
        "comic-style black and white caricature of a laughing cook, apron and utensils, ink wash finish",
        "grayscale avatar of a trendy mixologist with suspenders, bold contour lines, cartoon vibe",
        "monochrome caricature of a pastry chef with piping bag, cute proportions, marker sketch",
        "black and white ink illustration of a friendly host holding a menu, mid-century cartoon style",
    ]

    def __init__(self, restaurant_slug: str | None = None):
        self.restaurant_slug = restaurant_slug or ImageService.RESTAURANT_SLUG

    @staticmethod
    def _normalize_image(content: bytes, grayscale: bool = False, max_size: int = 800) -> bytes:
        """Ensure images share the same format, size, and color model."""
        image = Image.open(BytesIO(content))
        image = image.convert("L").convert("RGB") if grayscale else image.convert("RGB")
        image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return buffer.read()

    def _generate_with_pollinations(self, prompt: str) -> bytes:
        url = f"https://image.pollinations.ai/prompt/{quote_plus(prompt)}"
        params = {
            "width": 768,
            "height": 768,
            "nologo": "true",
            "seed": secrets.randbelow(1_000_000),
        }
        headers = {"User-Agent": "ProntoApp/1.0 (+https://pronto.example.com)"}
        response = requests.get(url, params=params, headers=headers, timeout=90)
        response.raise_for_status()
        return response.content

    def _generate_with_openai(self, prompt: str, size: str = "1024x1024") -> bytes:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada para usar OpenAI")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Instala el paquete openai para usar este proveedor") from exc

        client = OpenAI(api_key=api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        download = requests.get(image_url, timeout=90)
        download.raise_for_status()
        return download.content

    def generate_image(
        self,
        prompt: str,
        provider: str = FREE_PROVIDER,
        category: str = "menu",
        grayscale: bool = False,
    ) -> dict[str, str]:
        """Generate an image and persist it on the static asset store."""
        if not prompt:
            raise ValueError("El prompt es obligatorio para generar la imagen")

        provider = (provider or self.FREE_PROVIDER).lower()
        if provider == self.OPENAI_PROVIDER:
            raw = self._generate_with_openai(prompt)
        else:
            raw = self._generate_with_pollinations(prompt)

        normalized = self._normalize_image(raw, grayscale=grayscale)
        filename_hint = f"{self._slugify(prompt)[:40] or 'ia-image'}.png"
        return ImageService.save_raw_image(
            normalized, filename_hint, category, self.restaurant_slug
        )

    def generate_profile_set(
        self,
        count: int = 10,
        provider: str = FREE_PROVIDER,
    ) -> list[dict[str, str]]:
        """Generate a batch of grayscale avatar images."""
        results: list[dict[str, str]] = []
        prompts = self._cycle_prompts(count)
        for prompt in prompts:
            try:
                results.append(
                    self.generate_image(
                        prompt, provider=provider, category="profiles", grayscale=True
                    )
                )
            except Exception as exc:
                logger.error("No se pudo generar avatar con prompt '%s': %s", prompt, exc)
        return results

    def import_from_url(
        self,
        url: str,
        category: str = "menu",
        grayscale: bool = False,
    ) -> dict[str, str]:
        """Fetch an external image and store it locally."""
        if not url:
            raise ValueError("La URL es requerida")

        headers = {"User-Agent": "ProntoApp/1.0 (+https://pronto.example.com)"}
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()

        normalized = self._normalize_image(response.content, grayscale=grayscale)
        filename = url.split("/")[-1] or "imported-image.png"
        if "." not in filename:
            filename = f"{self._slugify(filename)}.png"
        return ImageService.save_raw_image(normalized, filename, category, self.restaurant_slug)

    @classmethod
    def _slugify(cls, value: str) -> str:
        allowed = "-_."
        value = value.strip().lower()
        return "".join(ch for ch in value if ch.isalnum() or ch in allowed).replace(" ", "-")

    def _cycle_prompts(self, count: int) -> list[str]:
        prompts: list[str] = []
        idx = 0
        while len(prompts) < count:
            prompts.append(self.PROFILE_PROMPTS[idx % len(self.PROFILE_PROMPTS)])
            idx += 1
        return prompts
