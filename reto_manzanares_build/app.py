#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from manzanares_agent.api import serve
from manzanares_agent.config import ConfigurationError, Settings
from manzanares_agent.database import CRMDatabase, DatabaseError
from manzanares_agent.logging_config import configure_logging
from manzanares_agent.orchestrator import (
    ManzanaresOrchestrator,
    OrchestrationError,
)


LOGGER = logging.getLogger(__name__)


def build_system(
    settings: Settings | None = None,
) -> tuple[CRMDatabase, ManzanaresOrchestrator]:
    runtime_settings = settings or Settings.load()
    database = CRMDatabase(runtime_settings.database_path)
    database.initialize()
    return database, ManzanaresOrchestrator(database, runtime_settings)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nucleo comercial auditable para Grupo Manzanares."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inicializar", help="Aplica el esquema y las migraciones.")

    demo = sub.add_parser("demo", help="Carga datos sinteticos y genera un briefing.")
    demo.add_argument(
        "--reset",
        action="store_true",
        help="Elimina los datos actuales. Usar solo en demostraciones.",
    )

    query = sub.add_parser("consultar", help="Realiza una consulta al sistema.")
    query.add_argument("question", help="Pregunta del lider comercial.")
    query.add_argument("--json", action="store_true", help="Entrega JSON estructurado.")

    sub.add_parser(
        "conversar",
        help="Abre una conversacion continua con los agentes y Ollama.",
    )
    sub.add_parser("tablero", help="Muestra indicadores operativos y comerciales.")
    sub.add_parser("salud", help="Verifica integridad, migraciones y disponibilidad.")
    sub.add_parser("servir", help="Inicia la API HTTP interna.")

    tasks = sub.add_parser("tareas", help="Lista la cola de trabajo.")
    tasks.add_argument(
        "--estado",
        default="pending",
        choices=[
            "pending",
            "in_progress",
            "completed",
            "cancelled",
            "superseded",
            "all",
        ],
    )

    interaction = sub.add_parser(
        "registrar-interaccion", help="Registra el resultado de una gestion."
    )
    interaction.add_argument("contact_id", type=int)
    interaction.add_argument("--canal", required=True)
    interaction.add_argument("--resultado", required=True)
    interaction.add_argument("--notas", default="")
    interaction.add_argument("--tarea", type=int)

    importer = sub.add_parser(
        "importar-contactos", help="Valida e importa contactos desde CSV."
    )
    importer.add_argument("archivo", type=Path)
    importer.add_argument("--dry-run", action="store_true")

    backup = sub.add_parser("backup", help="Crea una copia consistente de SQLite.")
    backup.add_argument("--destino", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings.load()
        configure_logging(settings.log_level, settings.json_logs)
        database, orchestrator = build_system(settings)

        if args.command == "inicializar":
            print(
                json.dumps(
                    {
                        "database": str(database.path),
                        "schema_version": database.schema_version(),
                        "status": "initialized",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "demo":
            database.seed_demo(reset=args.reset)
            result = orchestrator.run(
                "Dame el briefing comercial, clientes prioritarios y acciones de hoy"
            )
            print(result.to_text())
        elif args.command == "consultar":
            result = orchestrator.run(args.question)
            print(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
                if args.json
                else result.to_text()
            )
        elif args.command == "conversar":
            print("\nMANZANARES GROWTH AGENT")
            print("=" * 72)
            print(
                f"Modelo local: {settings.ollama_model}"
                if settings.llm_provider == "ollama"
                else "Modo deterministico: Ollama esta desactivado"
            )
            print("Pregunta libremente sobre clientes, ventas, prioridades y campañas.")
            print("Comandos: /ayuda, /tablero, /salud, /salir\n")
            while True:
                try:
                    question = input("Tú: ").strip()
                except EOFError:
                    print()
                    break
                if not question:
                    continue
                command = question.casefold()
                if command in {"/salir", "salir", "exit", "quit"}:
                    print("Agente: Conversación finalizada.")
                    break
                if command == "/ayuda":
                    print(
                        "\nAgente: Puedes preguntar, por ejemplo:\n"
                        "- ¿A quién debo llamar hoy y por qué?\n"
                        "- ¿Cuál es la brecha frente a la meta?\n"
                        "- ¿Qué clientes inactivos conviene recuperar?\n"
                        "- Diseña una campaña de recompra.\n"
                    )
                    continue
                if command == "/tablero":
                    print(
                        "\nAgente:\n"
                        + json.dumps(
                            database.dashboard(), ensure_ascii=False, indent=2
                        )
                        + "\n"
                    )
                    continue
                if command == "/salud":
                    print(
                        "\nAgente:\n"
                        + json.dumps(database.health(), ensure_ascii=False, indent=2)
                        + "\n"
                    )
                    continue
                try:
                    result = orchestrator.run(question)
                    print(f"\nAgente: {result.executive_summary}")
                    if result.generation_metrics:
                        print(
                            "\nUso: "
                            + result.generation_metrics.display()
                        )
                    else:
                        print("\nUso: respuesta determinística; Ollama no generó tokens.")
                    if result.warnings:
                        print("Aviso: " + " ".join(result.warnings))
                    print()
                except (DatabaseError, OrchestrationError, ValueError) as exc:
                    print(f"\nAgente: No pude procesar la pregunta: {exc}\n")
        elif args.command == "tablero":
            print(
                json.dumps(database.dashboard(), ensure_ascii=False, indent=2)
            )
        elif args.command == "salud":
            health = database.health()
            print(json.dumps(health, ensure_ascii=False, indent=2))
            return 0 if health.get("status") == "ok" else 1
        elif args.command == "tareas":
            print(
                json.dumps(
                    database.list_tasks(args.estado),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "registrar-interaccion":
            interaction_id = database.record_interaction(
                args.contact_id,
                args.canal,
                args.resultado,
                args.notas,
                task_id=args.tarea,
            )
            print(json.dumps({"interaction_id": interaction_id}, indent=2))
        elif args.command == "importar-contactos":
            report = database.import_contacts_csv(
                args.archivo, dry_run=args.dry_run
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["rejected"] == 0 else 2
        elif args.command == "backup":
            destination = args.destino or Path("backups") / (
                f"manzanares-{datetime.now():%Y%m%d-%H%M%S}.db"
            )
            print(database.backup(destination).resolve())
        elif args.command == "servir":
            serve(database, orchestrator, settings)
        return 0
    except (ConfigurationError, DatabaseError, OrchestrationError, ValueError) as exc:
        LOGGER.error("%s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nOperacion detenida.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
