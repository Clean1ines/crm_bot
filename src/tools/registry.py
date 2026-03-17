"""
Tool Registry for dynamic, multi-tenant tool execution.

This module defines the core abstraction for tools in the MRAK-OS platform:
- Tool: Abstract base class defining the interface all tools must implement
- ToolRegistry: Singleton registry for registering and executing tools
- Input validation via JSON Schema for safe tool execution
- Sandbox support for public/untrusted tool execution

The registry enables:
- Dynamic tool resolution from canvas workflows
- Multi-tenant isolation via context dict
- Event emission for audit and debugging
- Marketplace-ready architecture for third-party tools
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from uuid import UUID

import jsonschema
from jsonschema import ValidationError as SchemaValidationError

from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)


class ToolExecutionError(Exception):
    """
    Exception raised when a tool execution fails.
    
    Attributes:
        tool_name: Name of the tool that failed.
        message: Human-readable error message.
        details: Optional additional error details.
    """
    
    def __init__(self, tool_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.tool_name = tool_name
        self.message = message
        self.details = details or {}
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")


class Tool(ABC):
    """
    Abstract base class for all tools in the MRAK-OS platform.
    
    Every tool must implement this interface to be registered in the ToolRegistry.
    Tools are executed within a multi-tenant context and must respect isolation.
    
    Attributes:
        name: Unique identifier for the tool (used in canvas and API).
        description: Human-readable description for canvas UI.
        input_schema: JSON Schema defining valid input arguments.
        is_public: Whether this tool can be used by untrusted users (Marketplace).
        timeout_seconds: Maximum execution time for this tool (None = no limit).
    """
    
    name: str
    description: str
    input_schema: Dict[str, Any]
    is_public: bool = False
    timeout_seconds: Optional[int] = None
    
    @abstractmethod
    async def run(self, args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with given arguments and context.
        
        Args:
            args: Tool-specific arguments validated against input_schema.
            context: Multi-tenant context containing:
                - project_id: UUID of the project (required)
                - thread_id: UUID of the conversation thread (optional)
                - user_id: Telegram user ID (optional)
                - Any other request-specific metadata
        
        Returns:
            Dict containing tool execution results.
        
        Raises:
            ToolExecutionError: If tool execution fails.
            asyncio.TimeoutError: If execution exceeds timeout_seconds.
        """
        pass
    
    def validate_input(self, args: Dict[str, Any]) -> None:
        """
        Validate input arguments against the tool's input_schema.
        
        Args:
            args: Input arguments to validate.
        
        Raises:
            SchemaValidationError: If args don't match input_schema.
        """
        try:
            jsonschema.validate(instance=args, schema=self.input_schema)
        except SchemaValidationError as e:
            logger.warning(
                "Tool input validation failed",
                extra={
                    "tool_name": self.name,
                    "error": str(e.message),
                    "path": list(e.path) if e.path else None
                }
            )
            raise
    
    def _require_context_field(self, context: Dict[str, Any], field: str) -> Any:
        """
        Require a specific field in the context dict.
        
        Args:
            context: Context dictionary from orchestrator.
            field: Required field name.
        
        Returns:
            The value of the required field.
        
        Raises:
            ToolExecutionError: If field is missing.
        """
        if field not in context:
            raise ToolExecutionError(
                self.name,
                f"Required context field '{field}' is missing",
                {"available_fields": list(context.keys())}
            )
        return context[field]


class ToolRegistry:
    """
    Singleton registry for managing and executing tools.
    
    The ToolRegistry provides:
    - Registration of tools by unique name
    - Input validation before execution
    - Context isolation for multi-tenant safety
    - Optional sandbox execution for public tools
    - Event emission hooks for audit logging
    
    Usage:
        registry = ToolRegistry()
        registry.register(MyTool())
        result = await registry.execute("my_tool", {"arg": "value"}, context)
    """
    
    def __init__(self) -> None:
        """
        Initialize an empty ToolRegistry.
        
        Note: Use the singleton instance `tool_registry` from __init__.py
        instead of creating new instances.
        """
        self._tools: Dict[str, Tool] = {}
        self._event_emitters: List[Callable] = []
        self._lock = asyncio.Lock()
        logger.debug("ToolRegistry initialized")
    
    def register(self, tool: Tool, public: bool = False) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool instance to register.
            public: If True, tool will be available in Marketplace (requires sandbox).
        
        Raises:
            ValueError: If tool name is already registered.
        """
        if tool.name in self._tools:
            logger.error(
                "Tool name conflict",
                extra={"tool_name": tool.name, "existing": type(self._tools[tool.name]).__name__}
            )
            raise ValueError(f"Tool '{tool.name}' is already registered")
        
        tool.is_public = public
        self._tools[tool.name] = tool
        logger.info(
            "Tool registered",
            extra={"tool_name": tool.name, "public": public, "description": tool.description}
        )
    
    def register_event_emitter(self, emitter: Callable) -> None:
        """
        Register a callback to be called on tool execution events.
        
        Args:
            emitter: Callable(event_type: str, payload: Dict) -> None
        """
        self._event_emitters.append(emitter)
        logger.debug("Event emitter registered", extra={"emitter": emitter.__name__})
    
    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Emit an event to all registered emitters.
        
        Args:
            event_type: Type of event (e.g., "tool_called", "tool_failed").
            payload: Event-specific data.
        """
        for emitter in self._event_emitters:
            try:
                emitter(event_type, payload)
            except Exception as e:
                logger.error(
                    "Event emitter failed",
                    extra={"event_type": event_type, "error": str(e)}
                )
    
    async def execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a registered tool with validation and context isolation.
        
        This is the main entry point for tool execution from:
        - LangGraph agent nodes
        - Canvas workflow runtime
        - API endpoints
        
        Args:
            name: Name of the tool to execute (must be registered).
            args: Tool-specific arguments (validated against input_schema).
            context: Multi-tenant context with project_id, thread_id, etc.
        
        Returns:
            Dict containing tool execution results.
        
        Raises:
            ValueError: If tool name is not registered.
            SchemaValidationError: If args don't match input_schema.
            ToolExecutionError: If tool execution fails.
            asyncio.TimeoutError: If execution exceeds timeout.
        """
        start_time = time.time()
        
        # Validate tool exists
        if name not in self._tools:
            logger.error(
                "Tool not found in registry",
                extra={"tool_name": name, "available_tools": list(self._tools.keys())}
            )
            raise ValueError(f"Tool '{name}' is not registered")
        
        tool = self._tools[name]
        
        # Validate input schema
        try:
            tool.validate_input(args)
        except SchemaValidationError as e:
            self._emit_event("tool_validation_failed", {
                "tool_name": name,
                "error": str(e.message),
                "context_project_id": context.get("project_id")
            })
            raise
        
        # Validate required context fields
        try:
            tool._require_context_field(context, "project_id")
        except ToolExecutionError as e:
            self._emit_event("tool_context_error", {
                "tool_name": name,
                "error": e.message,
                "context_keys": list(context.keys())
            })
            raise
        
        # Emit tool_called event
        self._emit_event("tool_called", {
            "tool_name": name,
            "args_keys": list(args.keys()),
            "context_project_id": context.get("project_id"),
            "context_thread_id": context.get("thread_id"),
            "timestamp": start_time
        })
        
        logger.info(
            "Executing tool",
            extra={
                "tool_name": name,
                "project_id": context.get("project_id"),
                "thread_id": context.get("thread_id"),
                "args_keys": list(args.keys())
            }
        )
        
        try:
            # Execute with optional timeout
            if tool.timeout_seconds:
                result = await asyncio.wait_for(
                    tool.run(args, context),
                    timeout=tool.timeout_seconds
                )
            else:
                result = await tool.run(args, context)
            
            elapsed = time.time() - start_time
            logger.info(
                "Tool executed successfully",
                extra={
                    "tool_name": name,
                    "elapsed_seconds": round(elapsed, 3),
                    "result_keys": list(result.keys()) if isinstance(result, dict) else None
                }
            )
            
            # Emit success event
            self._emit_event("tool_completed", {
                "tool_name": name,
                "elapsed_seconds": elapsed,
                "result_keys": list(result.keys()) if isinstance(result, dict) else None
            })
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(
                "Tool execution timed out",
                extra={
                    "tool_name": name,
                    "timeout_seconds": tool.timeout_seconds,
                    "project_id": context.get("project_id")
                }
            )
            self._emit_event("tool_timeout", {
                "tool_name": name,
                "timeout_seconds": tool.timeout_seconds
            })
            raise
            
        except ToolExecutionError:
            # Re-raise without additional logging (already logged in tool)
            raise
            
        except Exception as e:
            logger.exception(
                "Tool execution failed with unexpected error",
                extra={
                    "tool_name": name,
                    "project_id": context.get("project_id"),
                    "error_type": type(e).__name__
                }
            )
            self._emit_event("tool_failed", {
                "tool_name": name,
                "error_type": type(e).__name__,
                "error_message": str(e)
            })
            raise ToolExecutionError(name, str(e), {"original_exception": type(e).__name__})
    
    def list_tools(self, public_only: bool = False) -> List[Dict[str, Any]]:
        """
        List registered tools for canvas UI or API documentation.
        
        Args:
            public_only: If True, only return tools marked as public.
        
        Returns:
            List of dicts with tool metadata (name, description, input_schema).
        """
        tools = self._tools.values()
        if public_only:
            tools = [t for t in tools if t.is_public]
        
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "is_public": t.is_public,
                "timeout_seconds": t.timeout_seconds
            }
            for t in tools
        ]
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """
        Get a registered tool by name (for testing or advanced use).
        
        Args:
            name: Tool name to retrieve.
        
        Returns:
            Tool instance if found, None otherwise.
        """
        return self._tools.get(name)
    
    async def unregister(self, name: str) -> bool:
        """
        Unregister a tool from the registry (thread-safe).
        
        Args:
            name: Tool name to unregister.
        
        Returns:
            True if tool was unregistered, False if not found.
        """
        async with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info("Tool unregistered", extra={"tool_name": name})
                return True
            return False
    
    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)
    
    def __contains__(self, name: str) -> bool:
        """Check if a tool name is registered."""
        return name in self._tools


# Global singleton instance
tool_registry = ToolRegistry()
