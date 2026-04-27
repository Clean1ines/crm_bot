"""
HTTP Tool for making external API requests.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from urllib.parse import urlparse

import httpx

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.tools.registry import JsonMap, Tool, ToolExecutionError

logger = get_logger(__name__)


class HTTPTool(Tool):
    name = "http_request"
    description = (
        "Make HTTP requests to external APIs. Supports GET, POST, PUT, PATCH, "
        "DELETE with custom headers and body."
    )
    input_schema: JsonMap = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
            },
            "url": {
                "type": "string",
                "description": "Target URL (must start with https://)",
                "format": "uri",
                "pattern": "^https://.+",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers",
                "additionalProperties": {"type": "string"},
            },
            "params": {
                "type": "object",
                "description": "Optional query parameters",
                "additionalProperties": True,
            },
            "body": {
                "description": "Optional request body (JSON object or string)",
                "oneOf": [
                    {"type": "object"},
                    {"type": "string"},
                ],
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "minimum": 1,
                "maximum": 60,
                "default": 30,
            },
            "parse_json": {
                "type": "boolean",
                "description": "Whether to parse response as JSON",
                "default": True,
            },
        },
        "required": ["method", "url"],
        "additionalProperties": False,
    }

    timeout_seconds: int | None = 30
    is_public: bool = True

    def _validate_url(self, url: str) -> None:
        if not url.startswith("https://"):
            raise ToolExecutionError(
                self.name,
                "Only HTTPS URLs are allowed",
                {"url": url},
            )

        allowed_domains = _allowed_domains()
        if not allowed_domains:
            return

        domain = urlparse(url).netloc
        if _domain_is_allowed(domain, allowed_domains):
            return

        logger.warning(
            "HTTP request blocked: domain not in whitelist",
            extra={"url": url, "domain": domain, "allowed": allowed_domains},
        )
        raise ToolExecutionError(
            self.name,
            f"Domain '{domain}' is not in the allowed list",
            {"url": url, "allowed_domains": allowed_domains},
        )

    async def run(self, args: JsonMap, context: JsonMap) -> JsonMap:
        project_id = str(self._require_context_field(context, "project_id"))
        request = _request_from_args(args)
        self._validate_url(request.url)

        logger.info(
            "Executing HTTP request",
            extra={
                "project_id": project_id,
                "method": request.method,
                "url": request.url,
                "has_body": request.body is not None,
            },
        )

        return await self._execute_request(project_id, request)

    async def _execute_request(self, project_id: str, request: HTTPRequest) -> JsonMap:
        start_time = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                response = await client.request(**request.to_httpx_kwargs())

            elapsed_ms = _elapsed_ms(start_time)
            response_body = _response_body(response, parse_json=request.parse_json)

            logger.info(
                "HTTP request completed",
                extra={
                    "project_id": project_id,
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                    "url": request.url,
                },
            )

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "elapsed_ms": elapsed_ms,
                "url": request.url,
            }

        except httpx.TimeoutException as exc:
            raise self._timeout_error(project_id, request) from exc
        except httpx.HTTPError as exc:
            raise self._http_error(project_id, request, exc) from exc
        except Exception as exc:
            raise self._unexpected_error(project_id, request, exc) from exc

    def _timeout_error(self, project_id: str, request: HTTPRequest) -> ToolExecutionError:
        logger.error(
            "HTTP request timed out",
            extra={
                "project_id": project_id,
                "url": request.url,
                "timeout_seconds": request.timeout_seconds,
            },
        )
        return ToolExecutionError(
            self.name,
            f"Request timed out after {request.timeout_seconds}s",
            {"url": request.url, "timeout": request.timeout_seconds},
        )

    def _http_error(
        self,
        project_id: str,
        request: HTTPRequest,
        exc: httpx.HTTPError,
    ) -> ToolExecutionError:
        logger.error(
            "HTTP request failed",
            extra={
                "project_id": project_id,
                "url": request.url,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        return ToolExecutionError(
            self.name,
            f"HTTP error: {str(exc)}",
            {"url": request.url, "method": request.method},
        )

    def _unexpected_error(
        self,
        project_id: str,
        request: HTTPRequest,
        exc: Exception,
    ) -> ToolExecutionError:
        logger.exception(
            "HTTP request failed with unexpected error",
            extra={
                "project_id": project_id,
                "url": request.url,
                "error_type": type(exc).__name__,
            },
        )
        return ToolExecutionError(
            self.name,
            f"Request failed: {str(exc)}",
            {"url": request.url},
        )


class HTTPRequest:
    def __init__(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, object] | None,
        body: object,
        timeout_seconds: int,
        parse_json: bool,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.params = params
        self.body = body
        self.timeout_seconds = timeout_seconds
        self.parse_json = parse_json

    def to_httpx_kwargs(self) -> JsonMap:
        kwargs: JsonMap = {
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
        }

        if self.params:
            kwargs["params"] = self.params

        if self.body is not None:
            if isinstance(self.body, Mapping):
                kwargs["json"] = dict(self.body)
            else:
                kwargs["content"] = str(self.body)

        return kwargs


def _request_from_args(args: JsonMap) -> HTTPRequest:
    url = str(args.get("url") or "").strip()
    if not url:
        raise ToolExecutionError(
            HTTPTool.name,
            "URL is required",
            {"args": args},
        )

    return HTTPRequest(
        method=str(args.get("method") or "GET").upper(),
        url=url,
        headers=_string_mapping(args.get("headers")),
        params=_object_mapping_or_none(args.get("params")),
        body=args.get("body"),
        timeout_seconds=_timeout_seconds(args.get("timeout_seconds")),
        parse_json=bool(args.get("parse_json", True)),
    )


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}

    return {
        str(key): str(item)
        for key, item in value.items()
        if item is not None
    }


def _object_mapping_or_none(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None

    result = {str(key): item for key, item in value.items()}
    return result or None


def _timeout_seconds(value: object) -> int:
    try:
        timeout = int(value) if value is not None else 30
    except (TypeError, ValueError):
        timeout = 30

    return max(1, min(timeout, 60))


def _allowed_domains() -> list[str]:
    raw_domains = getattr(settings, "TOOL_HTTP_ALLOWED_DOMAINS", None)
    if not raw_domains:
        return []

    if isinstance(raw_domains, str):
        return [
            domain.strip()
            for domain in raw_domains.split(",")
            if domain.strip()
        ]

    if isinstance(raw_domains, list | tuple | set):
        return [
            str(domain).strip()
            for domain in raw_domains
            if str(domain).strip()
        ]

    return []


def _domain_is_allowed(domain: str, allowed_domains: list[str]) -> bool:
    return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in allowed_domains)


def _elapsed_ms(start_time: float) -> int:
    return round((time.monotonic() - start_time) * 1000)


def _response_body(response: httpx.Response, *, parse_json: bool) -> object:
    content_type = response.headers.get("content-type", "")
    if not parse_json or not content_type.startswith("application/json"):
        return response.text

    try:
        return response.json()
    except json.JSONDecodeError:
        return response.text
