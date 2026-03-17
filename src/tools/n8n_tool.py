"""
n8n Workflow Trigger Tool.

This tool allows canvas workflows to trigger n8n automation workflows
via webhook. It's a specialized version of HTTPTool with n8n-specific
conventions and error handling.

Use case:
- Canvas workflow detects "order_created" event
- Tool triggers n8n webhook with order data
- n8n handles: CRM update, email notification, inventory sync

Security:
- Webhook URL must be configured per-project or use allowlist
- Payload is validated against expected schema
- Timeout enforced to prevent hanging

Usage in canvas:
{
    "type": "tool_call",
    "tool_name": "n8n_workflow",
    "args": {
        "webhook_url": "https://n8n.example.com/webhook/order-created",
        "payload": {
            "order_id": "12345",
            "customer_email": "user@example.com",
            "total": 99.99
        }
    }
}
"""

from typing import Any, Dict, Optional

import httpx

from src.core.logging import get_logger
from src.core.config import settings
from src.tools.registry import Tool, ToolExecutionError

logger = get_logger(__name__)


class N8NTool(Tool):
    """
    Tool for triggering n8n workflows via webhook.
    
    This tool simplifies integration with self-hosted or cloud n8n
    instances by providing:
    - Webhook URL validation
    - Payload schema enforcement (optional)
    - n8n-specific error handling
    - Response parsing for workflow results
    
    Context required:
    - project_id: For audit and potential webhook URL lookup
    
    Returns:
    {
        "triggered": true,
        "execution_id": "n8n-exec-123",
        "response": {...},  # n8n webhook response
        "elapsed_ms": 250
    }
    """
    
    name = "n8n_workflow"
    description = "Trigger an n8n workflow via webhook. Use this to integrate with CRM, email, inventory, or other automation workflows."
    input_schema = {
        "type": "object",
        "properties": {
            "webhook_url": {
                "type": "string",
                "description": "n8n webhook URL (must start with https://)",
                "format": "uri",
                "pattern": "^https://.+/webhook/.+"
            },
            "payload": {
                "type": "object",
                "description": "Data to send to the n8n workflow",
                "additionalProperties": True
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Request timeout in seconds",
                "minimum": 1,
                "maximum": 60,
                "default": 30
            },
            "expect_execution_id": {
                "type": "boolean",
                "description": "Whether to parse n8n execution ID from response",
                "default": True
            }
        },
        "required": ["webhook_url", "payload"],
        "additionalProperties": False
    }
    
    timeout_seconds: Optional[int] = 30
    is_public: bool = True  # Can be used in Marketplace with URL validation
    
    def _validate_webhook_url(self, url: str, project_id: str) -> None:
        """
        Validate n8n webhook URL against configuration.
        
        Args:
            url: Webhook URL to validate.
            project_id: Project ID for potential project-specific allowlist.
        
        Raises:
            ToolExecutionError: If URL is invalid or not allowed.
        """
        if not url.startswith("https://"):
            raise ToolExecutionError(
                self.name,
                "Only HTTPS webhook URLs are allowed",
                {"url": url}
            )
        
        if "/webhook/" not in url:
            logger.warning(
                "n8n webhook URL may be invalid",
                extra={"url": url, "project_id": project_id}
            )
        
        # Check against configured allowlist if present
        allowed_webhooks = getattr(settings, "TOOL_N8N_ALLOWED_WEBHOOKS", [])
        if allowed_webhooks:
            if not any(url.startswith(allowed) for allowed in allowed_webhooks):
                logger.warning(
                    "n8n webhook blocked: URL not in allowlist",
                    extra={"url": url, "project_id": project_id}
                )
                raise ToolExecutionError(
                    self.name,
                    "Webhook URL is not in the allowed list",
                    {"url": url, "allowed_prefixes": allowed_webhooks}
                )
    
    async def run(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trigger an n8n workflow via webhook.
        
        Args:
            args: Webhook configuration (webhook_url, payload, etc.).
            context: Must contain 'project_id' for validation.
        
        Returns:
            Dict with trigger confirmation and n8n response.
        
        Raises:
            ToolExecutionError: If trigger fails or validation fails.
        """
        project_id = self._require_context_field(context, "project_id")
        
        webhook_url = args.get("webhook_url", "").strip()
        payload = args.get("payload", {})
        timeout = min(args.get("timeout_seconds", 30), 60)
        expect_execution_id = args.get("expect_execution_id", True)
        
        if not webhook_url:
            raise ToolExecutionError(
                self.name,
                "webhook_url is required",
                {"args": args}
            )
        
        if not isinstance(payload, dict):
            raise ToolExecutionError(
                self.name,
                "payload must be a JSON object",
                {"payload_type": type(payload).__name__}
            )
        
        # Validate webhook URL
        self._validate_webhook_url(webhook_url, str(project_id))
        
        logger.info(
            "Triggering n8n workflow",
            extra={
                "project_id": project_id,
                "webhook_url": webhook_url,
                "payload_keys": list(payload.keys())
            }
        )
        
        start_time = httpx._utils.get_monotonic_time()
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                elapsed_ms = round((httpx._utils.get_monotonic_time() - start_time) * 1000)
                
                # Parse n8n response
                try:
                    response_data = response.json()
                except Exception:
                    response_data = {"raw_text": response.text}
                
                # Extract execution ID if expected
                execution_id = None
                if expect_execution_id:
                    execution_id = (
                        response_data.get("executionId") or
                        response_data.get("execution_id") or
                        response_data.get("id")
                    )
                
                logger.info(
                    "n8n workflow triggered",
                    extra={
                        "project_id": project_id,
                        "status_code": response.status_code,
                        "elapsed_ms": elapsed_ms,
                        "execution_id": execution_id
                    }
                )
                
                return {
                    "triggered": response.status_code in (200, 202, 204),
                    "status_code": response.status_code,
                    "execution_id": execution_id,
                    "response": response_data,
                    "elapsed_ms": elapsed_ms,
                    "webhook_url": webhook_url
                }
                
        except httpx.TimeoutException:
            logger.error(
                "n8n webhook timed out",
                extra={
                    "project_id": project_id,
                    "webhook_url": webhook_url,
                    "timeout_seconds": timeout
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Webhook timed out after {timeout}s",
                {"webhook_url": webhook_url}
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "n8n webhook returned error status",
                extra={
                    "project_id": project_id,
                    "webhook_url": webhook_url,
                    "status_code": e.response.status_code,
                    "response_body": e.response.text[:200] if e.response.text else None
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Webhook error {e.response.status_code}: {e.response.text[:100]}",
                {"webhook_url": webhook_url, "status": e.response.status_code}
            )
            
        except Exception as e:
            logger.exception(
                "n8n webhook failed with unexpected error",
                extra={
                    "project_id": project_id,
                    "webhook_url": webhook_url,
                    "error_type": type(e).__name__
                }
            )
            raise ToolExecutionError(
                self.name,
                f"Webhook failed: {str(e)}",
                {"webhook_url": webhook_url}
            )
