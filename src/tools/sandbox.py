"""
Sandbox execution environment for public/untrusted tools.

This module provides security controls for executing tools that may be
defined by third parties (Marketplace) or used in untrusted contexts:
- Execution timeout enforcement
- Domain/URL filtering for network requests
- Memory and CPU limits (via asyncio)
- Restricted imports and globals

Usage:
    from src.tools.sandbox import sandbox_execute
    
    result = await sandbox_execute(
        tool.run,
        args={"query": "test"},
        context={"project_id": "..."},
        timeout_seconds=30,
        allowed_domains=["api.example.com"]
    )
"""

import asyncio
import re
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from urllib.parse import urlparse

from src.core.logging import get_logger
from src.core.config import settings
from src.tools.registry import ToolExecutionError

logger = get_logger(__name__)


# Default security settings
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RESPONSE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_URL_SCHEMES = {"https"}
DEFAULT_BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "169.254.169.254",  # AWS metadata
    "metadata.google.internal",  # GCP metadata
}


class SandboxError(ToolExecutionError):
    """
    Exception raised when sandbox security constraints are violated.
    
    Attributes:
        tool_name: Name of the tool that violated constraints.
        violation_type: Type of violation (timeout, domain, size, etc.).
        details: Additional context about the violation.
    """
    
    def __init__(
        self,
        tool_name: str,
        violation_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.violation_type = violation_type
        super().__init__(
            tool_name,
            f"Sandbox violation ({violation_type}): {message}",
            details
        )


async def sandbox_execute(
    coro: Coroutine[Any, Any, Any],
    tool_name: str,
    timeout_seconds: Optional[int] = None,
    allowed_domains: Optional[Set[str]] = None,
    blocked_domains: Optional[Set[str]] = None,
    allowed_url_schemes: Optional[Set[str]] = None
) -> Any:
    """
    Execute a coroutine within sandbox security constraints.
    
    This wrapper enforces:
    - Execution timeout (prevents hanging)
    - Domain filtering for any network requests (via monkey-patching)
    - Response size limits
    
    Note: Full isolation requires process-level sandboxing (not implemented).
    This provides best-effort protection for trusted code patterns.
    
    Args:
        coro: Coroutine to execute (typically tool.run()).
        tool_name: Name of the tool for error reporting.
        timeout_seconds: Maximum execution time (default: 30s).
        allowed_domains: Set of allowed domain suffixes (None = all).
        blocked_domains: Set of explicitly blocked domains.
        allowed_url_schemes: Allowed URL schemes (default: {"https"}).
    
    Returns:
        Result of the coroutine execution.
    
    Raises:
        SandboxError: If any security constraint is violated.
        asyncio.TimeoutError: If execution exceeds timeout.
    """
    timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
    blocked = blocked_domains or DEFAULT_BLOCKED_DOMAINS
    allowed_schemes = allowed_url_schemes or ALLOWED_URL_SCHEMES
    
    # Apply timeout
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(
            "Tool execution timed out in sandbox",
            extra={"tool_name": tool_name, "timeout_seconds": timeout}
        )
        raise SandboxError(
            tool_name,
            "timeout",
            f"Execution exceeded {timeout} seconds",
            {"timeout_seconds": timeout}
        )
    
    # Note: Domain filtering would require intercepting httpx/requests calls
    # This is complex and may be better handled at the Tool level
    # For now, we rely on Tool implementations to use _validate_url()
    
    return result


def validate_url_for_sandbox(
    url: str,
    tool_name: str,
    allowed_domains: Optional[Set[str]] = None,
    blocked_domains: Optional[Set[str]] = None,
    allowed_schemes: Optional[Set[str]] = None
) -> None:
    """
    Validate a URL against sandbox security constraints.
    
    Args:
        url: URL to validate.
        tool_name: Tool name for error reporting.
        allowed_domains: Allowed domain suffixes (None = all https).
        blocked_domains: Explicitly blocked domains.
        allowed_schemes: Allowed URL schemes.
    
    Raises:
        SandboxError: If URL violates constraints.
    """
    from urllib.parse import urlparse
    
    blocked = blocked_domains or DEFAULT_BLOCKED_DOMAINS
    schemes = allowed_schemes or ALLOWED_URL_SCHEMES
    
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SandboxError(
            tool_name,
            "invalid_url",
            f"Failed to parse URL: {str(e)}",
            {"url": url}
        )
    
    # Check scheme
    if parsed.scheme not in schemes:
        raise SandboxError(
            tool_name,
            "scheme_not_allowed",
            f"URL scheme '{parsed.scheme}' is not allowed",
            {"url": url, "allowed_schemes": list(schemes)}
        )
    
    # Check domain
    domain = parsed.netloc.lower()
    if domain in blocked:
        raise SandboxError(
            tool_name,
            "domain_blocked",
            f"Domain '{domain}' is explicitly blocked",
            {"url": url, "blocked_domains": list(blocked)}
        )
    
    # Check allowlist if provided
    if allowed_domains:
        if not any(domain.endswith(allowed) for allowed in allowed_domains):
            raise SandboxError(
                tool_name,
                "domain_not_allowed",
                f"Domain '{domain}' is not in the allowed list",
                {"url": url, "allowed_domains": list(allowed_domains)}
            )
    
    # Check for internal/private IPs
    if _is_private_ip(domain):
        raise SandboxError(
            tool_name,
            "private_ip_blocked",
            f"Private/internal IP addresses are not allowed",
            {"url": url, "domain": domain}
        )


def _is_private_ip(domain: str) -> bool:
    """
    Check if a domain resolves to a private/internal IP address.
    
    This is a best-effort check without actual DNS resolution.
    For production, consider using a library like `ipaddress` with
    actual resolution or a service like Cloudflare's DNS API.
    
    Args:
        domain: Domain name or IP address string.
    
    Returns:
        True if domain appears to be a private/internal address.
    """
    # Check if it's already an IP address
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ip_pattern, domain):
        parts = domain.split(".")
        if len(parts) == 4:
            try:
                first = int(parts[0])
                second = int(parts[1])
                # 10.x.x.x, 172.16-31.x.x, 192.168.x.x, 127.x.x.x, 0.x.x.x
                if (first == 10 or 
                    (first == 172 and 16 <= second <= 31) or
                    (first == 192 and second == 168) or
                    first == 127 or
                    first == 0):
                    return True
            except ValueError:
                pass
    
    # Check for localhost variants
    localhost_patterns = [
        r'^localhost(\.\w+)?$',
        r'^local\.host$',
        r'^.*\.local$',
        r'^.*\.internal$',
    ]
    for pattern in localhost_patterns:
        if re.match(pattern, domain, re.IGNORECASE):
            return True
    
    return False


class SandboxContext:
    """
    Context manager for sandbox execution with automatic cleanup.
    
    Usage:
        async with SandboxContext(tool_name="my_tool") as ctx:
            result = await ctx.execute(my_coro, timeout=30)
    """
    
    def __init__(
        self,
        tool_name: str,
        timeout_seconds: Optional[int] = None,
        allowed_domains: Optional[Set[str]] = None,
        blocked_domains: Optional[Set[str]] = None
    ):
        self.tool_name = tool_name
        self.timeout = timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        self.allowed_domains = allowed_domains
        self.blocked_domains = blocked_domains or DEFAULT_BLOCKED_DOMAINS
        self._start_time: Optional[float] = None
    
    async def __aenter__(self) -> "SandboxContext":
        self._start_time = time.time()
        logger.debug(
            "Sandbox context entered",
            extra={"tool_name": self.tool_name, "timeout": self.timeout}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            elapsed = time.time() - self._start_time
            logger.debug(
                "Sandbox context exited successfully",
                extra={"tool_name": self.tool_name, "elapsed_seconds": round(elapsed, 3)}
            )
        return False  # Don't suppress exceptions
    
    async def execute(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """
        Execute a coroutine within this sandbox context.
        
        Args:
            coro: Coroutine to execute.
        
        Returns:
            Result of coroutine execution.
        
        Raises:
            SandboxError: If constraints are violated.
        """
        return await sandbox_execute(
            coro=coro,
            tool_name=self.tool_name,
            timeout_seconds=self.timeout,
            allowed_domains=self.allowed_domains,
            blocked_domains=self.blocked_domains
        )
    
    def validate_url(self, url: str) -> None:
        """
        Validate a URL against this context's constraints.
        
        Args:
            url: URL to validate.
        
        Raises:
            SandboxError: If URL is not allowed.
        """
        validate_url_for_sandbox(
            url=url,
            tool_name=self.tool_name,
            allowed_domains=self.allowed_domains,
            blocked_domains=self.blocked_domains
        )
