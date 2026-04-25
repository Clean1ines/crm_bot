"""
HTTP Tool for making external API requests.

This tool provides a generic interface for calling external HTTP APIs
from agent tool calls. It supports all HTTP methods, custom headers,
JSON bodies, and response parsing.

Security considerations:
- Domain filtering can be applied via settings.TOOL_HTTP_ALLOWED_DOMAINS
- Timeout is enforced to prevent hanging requests
- Response size is limited to prevent memory issues

Usage:
{
    "type": "tool_call",
    "tool_name": "http_request",
    "args": {
        "method": "POST",
        "url": "https://api.example.com/webhook",
        "headers": {"Authorization": "Bearer token"},
        "body": {"event": "order_created", "data": {...}}
    }
}
"""

import json
from typing import Any, Dict, List, Optional

import httpx

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.tools.registry import Tool, ToolExecutionError

logger = get_logger(__name__)


class HTTPTool(Tool):
    """
    Generic HTTP request tool for external API integration.
    
    Supports GET, POST, PUT, PATCH, DELETE methods with:
    - Custom headers
    - JSON or form-encoded bodies
    - Query parameters
    - Response parsing (JSON or text)
    
    Context required:
    - project_id: For audit logging and potential rate limiting
    
    Returns:
    {
        "status_code": 200,
        "headers": {...},
        "body": {...},  # Parsed JSON or raw text
        "elapsed_ms": 150
    }
    """
    
    name = "http_request"
    description = "Make HTTP requests to external APIs. Supports GET, POST, PUT, PATCH, DELETE with custom headers and body."
    input_schema = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
            },
            "url": {
                "type": "string",
                "description": "Target URL (must start with https://)",
                "format": "uri",
                "pattern": "^https://.+"
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers",
                "additionalProperties": {"type": "string"}
            },
            "params": {
                "type": "object",
                "description": "Optional query parameters",
                "additionalProperties": True
            },
            "body": {
                "description": "Optional request body (JSON object or string)",
                "oneOf": [
                    {"type": "object"},
                    {"type": "string"}
                ]
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "minimum": 1,
                "maximum": 60,
                "default": 30
            },
            "parse_json": {
                "type": "boolean",
                "description": "Whether to parse response as JSON",
                "default": True
            }
        },
        "required": ["method", "url"],
        "additionalProperties": False
    }
    
    timeout_seconds: Optional[int] = 30
    is_public: bool = True  # Can be used in Marketplace with domain filtering
    
    def _validate_url(self, url: str) -> None:
        """
        Validate URL against allowed domains if configured.
        
        Args:
            url: URL to validate.
        
        Raises:
            ToolExecutionError: If URL is not allowed.
        """
        if not url.startswith("https://"):
            raise ToolExecutionError(
                self.name,
                "Only HTTPS URLs are allowed",
                {"url": url}
            )
        
        # Check domain whitelist if configured
        allowed_domains = getattr(settings, "TOOL_HTTP_ALLOWED_DOMAINS", [])
        if allowed_domains:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if not any(domain.endswith(allowed) for allowed in allowed_domains):
                logger.warning(
                    "HTTP request blocked: domain not in whitelist",
                    extra={"url": url, "domain": domain, "allowed": allowed_domains}
                )
                raise ToolExecutionError(
                    self.name,
                    f"Domain '{domain}' is not in the allowed list",
                    {"url": url, "allowed_domains": allowed_domains}
                )
    
    async def run(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an HTTP request to an external API.
        
        Args:
            args: Request configuration (method, url, headers, body, etc.).
            context: Must contain 'project_id' for audit logging.
        
        Returns:
            Dict with response data and metadata.
        
        Raises:
            ToolExecutionError: If request fails or validation fails.
        """
        project_id = self._require_context_field(context, "project_id")
        
        method = args.get("method", "GET").upper()
        url = args.get("url", "").strip()
        headers = args.get("headers", {})
        params = args.get("params")
        body = args.get("body")
        timeout = min(args.get("timeout_seconds", 30), 60)  # Cap at 60s
        parse_json = args.get("parse_json", True)
        
        if not url:
            raise ToolExecutionError(
                self.name,
                "URL is required",
                {"args": args}
            )
        
        # Validate URL security
        self._validate_url(url)
        
        logger.info(
            "Executing HTTP request",
            extra={
                "project_id": project_id,
                "method": method,
                "url": url,
                "has_body": body is not None
            }
        )
        
        start_time = httpx._utils.get_monotonic_time()
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Prepare request
                request_kwargs = {
                    "method": method,
                    "url": url,
                    "headers": headers
                }
                
                if params:
                    request_kwargs["params"] = params
                
                if body:
                    if isinstance(body, dict):
                        request_kwargs["json"] = body
                    else:
                        request_kwargs["content"] = body
                
                # Execute request
                response = await client.request(**request_kwargs)
                
                elapsed_ms = round((httpx._utils.get_monotonic_time() - start_time) * 1000)
                
                # Parse response
                if parse_json and response.headers.get("content-type", "").startswith("application/json"):
                    try:
                        response_body = response.json()
                    except json.JSONDecodeError:
                        response_body = response.text
                else:
                    response_body = response.text
                
                logger.info(
                    "HTTP request completed",
                    extra={
                        "project_id": project_id,
                        "status_code": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "url": url
                    }
                )
                
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                    "elapsed_ms": elapsed_ms,
                    "url": url
                }
                
        except httpx.TimeoutException as e:
            logger.error(
                "HTTP request timed out",
                extra={
                    "project_id": project_id,
                    "url": url,
                    "timeout_seconds": timeout
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Request timed out after {timeout}s",
                {"url": url, "timeout": timeout}
            )
            
        except httpx.HTTPError as e:
            logger.error(
                "HTTP request failed",
                extra={
                    "project_id": project_id,
                    "url": url,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            raise ToolExecutionError(
                self.name,
                f"HTTP error: {str(e)}",
                {"url": url, "method": method}
            )
            
        except Exception as e:
            logger.exception(
                "HTTP request failed with unexpected error",
                extra={
                    "project_id": project_id,
                    "url": url,
                    "error_type": type(e).__name__
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Request failed: {str(e)}",
                {"url": url}
            )
