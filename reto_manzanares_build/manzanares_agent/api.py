from __future__ import annotations

import hmac
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Settings
from .database import CRMDatabase, DatabaseError
from .orchestrator import ManzanaresOrchestrator, OrchestrationError


LOGGER = logging.getLogger(__name__)


class ApiApplication:
    def __init__(
        self,
        database: CRMDatabase,
        orchestrator: ManzanaresOrchestrator,
        settings: Settings,
    ):
        self.database = database
        self.orchestrator = orchestrator
        self.settings = settings

    def dispatch(
        self,
        method: str,
        target: str,
        body: dict[str, Any] | None,
        authorization: str | None,
    ) -> tuple[int, dict[str, Any]]:
        parsed = urlparse(target)
        path = parsed.path.rstrip("/") or "/"
        if path != "/health" and not self._authorized(authorization):
            return HTTPStatus.UNAUTHORIZED, {"error": "No autorizado."}

        if method == "GET" and path == "/health":
            health = self.database.health()
            status = (
                HTTPStatus.OK
                if health.get("status") == "ok"
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            return status, health
        if method == "GET" and path == "/api/v1/dashboard":
            return HTTPStatus.OK, self.database.dashboard()
        if method == "GET" and path == "/api/v1/tasks":
            status = parse_qs(parsed.query).get("status", ["pending"])[0]
            return HTTPStatus.OK, {"items": self.database.list_tasks(status)}
        if method == "POST" and path == "/api/v1/query":
            question = str((body or {}).get("question", ""))
            return HTTPStatus.OK, self.orchestrator.run(question).to_dict()
        if method == "POST" and path == "/api/v1/interactions":
            payload = body or {}
            interaction_id = self.database.record_interaction(
                int(payload.get("contact_id")),
                str(payload.get("channel", "")),
                str(payload.get("outcome", "")),
                str(payload.get("notes", "")),
                task_id=(
                    int(payload["task_id"])
                    if payload.get("task_id") is not None
                    else None
                ),
            )
            return HTTPStatus.CREATED, {"interaction_id": interaction_id}
        return HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."}

    def _authorized(self, authorization: str | None) -> bool:
        if not self.settings.api_token:
            return True
        expected = f"Bearer {self.settings.api_token}"
        return bool(
            authorization
            and hmac.compare_digest(authorization.strip(), expected)
        )


def build_handler(
    application: ApiApplication, settings: Settings
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ManzanaresGrowthAgent/2.0"

        def do_GET(self) -> None:
            self._handle()

        def do_POST(self) -> None:
            self._handle()

        def _handle(self) -> None:
            body: dict[str, Any] | None = None
            try:
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0:
                        body = {}
                    elif length > settings.request_max_bytes:
                        self._send(
                            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            {"error": "Solicitud demasiado grande."},
                        )
                        return
                    else:
                        decoded = self.rfile.read(length).decode("utf-8")
                        parsed_body = json.loads(decoded)
                        if not isinstance(parsed_body, dict):
                            raise ValueError("El cuerpo JSON debe ser un objeto.")
                        body = parsed_body
                status, payload = application.dispatch(
                    self.command,
                    self.path,
                    body,
                    self.headers.get("Authorization"),
                )
                self._send(status, payload)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except (DatabaseError, OrchestrationError) as exc:
                self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            except Exception:
                LOGGER.exception("Error no controlado en la API")
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "Error interno. Consulte los registros operativos."},
                )

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            LOGGER.info("%s - %s", self.address_string(), format % args)

    return Handler


def serve(
    database: CRMDatabase,
    orchestrator: ManzanaresOrchestrator,
    settings: Settings,
) -> None:
    application = ApiApplication(database, orchestrator, settings)
    server = ThreadingHTTPServer(
        (settings.api_host, settings.api_port),
        build_handler(application, settings),
    )
    LOGGER.info(
        "API iniciada en http://%s:%s", settings.api_host, settings.api_port
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
