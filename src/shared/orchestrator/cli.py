#!/usr/bin/env python3
"""
CLI del Orquestador de Modelos Locales

Uso:
    python orchestrator_cli.py "tu tarea aquí" [--stream] [--stats]
    python orchestrator_cli.py --models
    python orchestrator_cli.py --health
"""

import argparse
import asyncio
import sys

from build.shared.orchestrator import get_orchestrator, get_router


async def main():
    parser = argparse.ArgumentParser(description="Orquestador de Modelos Locales para Ollama")
    parser.add_argument("task", nargs="?", help="Tarea a ejecutar")
    parser.add_argument("--stream", action="store_true", help="Mostrar respuesta en streaming")
    parser.add_argument(
        "--stats", action="store_true", help="Mostrar estadísticas después de ejecutar"
    )
    parser.add_argument("--models", action="store_true", help="Listar modelos disponibles")
    parser.add_argument("--health", action="store_true", help="Verificar salud de servicios")
    parser.add_argument("--speed", action="store_true", help="Preferir modelo rápido")
    parser.add_argument("--quality", action="store_true", help="Preferir modelo de alta calidad")

    args = parser.parse_args()

    if not any([args.task, args.models, args.health]):
        parser.print_help()
        return

    orchestrator = get_orchestrator(prefer_speed=args.speed, prefer_quality=args.quality)

    if args.models:
        models = orchestrator.list_models()
        print("\n📦 Modelos Locales Disponibles:")
        print("=" * 60)
        for m in models:
            print(f"  • {m['name']} ({m['id']})")
            print(f"    Velocidad: {'⚡' * int(m['speed'])}")
            print(f"    Calidad:   {'⭐' * int(m['quality'])}")
            print(f"    Memoria:   {m['memory_gb']}GB")
            print(f"    Fortalezas: {', '.join(m['strengths'][:3])}")
            print()
        return

    if args.health:
        health = await orchestrator.health_check()
        print("\n🏥 Estado de Salud:")
        print("=" * 60)
        print(f"  Ollama: {'✅' if health['ollama']['healthy'] else '❌'}")
        print(f"  URL: {health['ollama']['url']}")
        if health.get("models"):
            print(f"  Modelos: {len(health['models'])}")
        print()
        return

    if args.task:
        print(f"\n🎯 Tarea: {args.task}")
        print("=" * 60)

        if args.stream:
            async for chunk in orchestrator.execute_streaming(args.task):
                if chunk["type"] == "metadata":
                    print(f"\n📌 Modelo: {chunk['model_name']}")
                    print(f"   Tipo: {chunk['task_type']}")
                    print(f"   Razón: {chunk['reasoning']}\n")
                elif chunk["type"] == "content":
                    print(chunk["chunk"], end="", flush=True)
                elif chunk["type"] == "done":
                    print("\n")
        else:
            result = await orchestrator.execute(args.task)

            print(f"\n📌 Modelo Seleccionado: {result.decision.model_name}")
            print(f"   Tipo de Tarea: {result.task_type.value}")
            print(f"   Confianza: {result.decision.confidence:.2f}")
            print(f"   Razón: {result.decision.reasoning}")
            print(f"   Tiempo: {(result.completed_at - result.started_at):.2f}s")

            print(f"\n📝 Respuesta:")
            print("-" * 60)
            if result.success:
                print(result.response.content)
            else:
                print(f"❌ Error: {result.error}")

            if args.stats:
                stats = orchestrator.get_stats()
                print(f"\n📊 Estadísticas:")
                print(f"   Total: {stats['total_tasks']}")
                print(f"   Éxito: {stats['successful']} ({stats['success_rate']:.1f}%)")
                print(f"   Modelos: {', '.join(stats['models_used'])}")


if __name__ == "__main__":
    asyncio.run(main())
