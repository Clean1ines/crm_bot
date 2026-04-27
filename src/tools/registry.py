"""
Tool Registry for dynamic, multi-tenant tool execution.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Protocol

import jsonschema
from jsonschema import ValidationError as SchemaValidationError

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

JsonMap = dict[str, object]


class ToolEventEmitter(Protocol):
    def __call__(self, event_type: str, payload: JsonMap) -> object: ...


class ToolExecutionError(Exception):
    """
    Exception raised when a tool execution fails.
    """

    def __init__(
        self,
        tool_name: str,
        message: str,
        details: JsonMap | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.message = message
        self.details = details or {}
        super().__init__(f"Tool '{tool_name}' execution failed: {message}")


class Tool(ABC):
    """
    Abstract base class for all tools.
    """

    name: str
    description: str
    input_schema: JsonMap
    is_public: bool = False
    timeout_seconds: int | None = None

    @abstractmethod
    async def run(self, args: JsonMap, context: JsonMap) -> JsonMap:
        """
        Execute the tool with given arguments and context.
        """
        raise NotImplementedError

    def validate_input(self, args: JsonMap) -> None:
        """
        Validate input arguments against the tool's input_schema.
        """
        try:
            jsonschema.validate(instance=args, schema=self.input_schema)
        except SchemaValidationError as exc:
            logger.warning(
                "Tool input validation failed",
                extra={
                    "tool_name": self.name,
                    "error": str(exc.message),
                    "path": list(exc.path) if exc.path else None,
                },
            )
            raise

    def _require_context_field(self, context: JsonMap, field: str) -> object:
        """
        Require a specific field in the context dict.
        """
        if field not in context:
            raise ToolExecutionError(
                self.name,
                f"Required context field '{field}' is missing",
                {"available_fields": list(context.keys())},
            )
        return context[field]


class ToolRegistry:
    """
    Registry for managing and executing tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._event_emitters: list[ToolEventEmitter] = []
        self._lock = asyncio.Lock()
        logger.debug("ToolRegistry initialized")

    def register(self, tool: Tool, public: bool = False) -> None:
        if tool.name in self._tools:
            logger.error(
                "Tool name conflict",
                extra={
                    "tool_name": tool.name,
                    "existing": type(self._tools[tool.name]).__name__,
                },
            )
            raise ValueError(f"Tool '{tool.name}' is already registered")

        tool.is_public = public
        self._tools[tool.name] = tool
        logger.info(
            "Tool registered",
            extra={
                "tool_name": tool.name,
                "public": public,
                "description": tool.description,
            },
        )

    def register_event_emitter(self, emitter: ToolEventEmitter) -> None:
        self._event_emitters.append(emitter)
        logger.debug(
            "Event emitter registered",
            extra={"emitter": getattr(emitter, "__name__", type(emitter).__name__)},
        )

    def _emit_event(self, event_type: str, payload: JsonMap) -> None:
        for emitter in self._event_emitters:
            try:
                emitter(event_type, payload)
            except Exception as exc:
                logger.error(
                    "Event emitter failed",
                    extra={"event_type": event_type, "error": str(exc)},
                )

    async def execute(
        self,
        name: str,
        args: JsonMap,
        context: JsonMap,
    ) -> JsonMap:
        start_time = time.time()
        tool = self._registered_tool(name)

        self._validate_tool_input(tool, name, args, context)
        self._validate_tool_context(tool, name, context)
        self._emit_tool_called(name, args, context, start_time)

        logger.info(
            "Executing tool",
            extra={
                "tool_name": name,
                "project_id": context.get("project_id"),
                "thread_id": context.get("thread_id"),
                "args_keys": list(args.keys()),
            },
        )

        try:
            result = await self._run_tool(tool, args, context)
            self._handle_success(name, result, start_time)
            return result
        except asyncio.TimeoutError:
            self._handle_timeout(name, tool, context)
            raise
        except ToolExecutionError:
            raise
        except Exception as exc:
            self._handle_unexpected_error(name, context, exc)
            raise ToolExecutionError(
                name,
                str(exc),
                {"original_exception": type(exc).__name__},
            ) from exc

    def _registered_tool(self, name: str) -> Tool:
        if name not in self._tools:
            logger.error(
                "Tool not found in registry",
                extra={"tool_name": name, "available_tools": list(self._tools.keys())},
            )
            raise ValueError(f"Tool '{name}' is not registered")
        return self._tools[name]

    def _validate_tool_input(
        self,
        tool: Tool,
        name: str,
        args: JsonMap,
        context: JsonMap,
    ) -> None:
        try:
            tool.validate_input(args)
        except SchemaValidationError as exc:
            self._emit_event(
                "tool_validation_failed",
                {
                    "tool_name": name,
                    "error": str(exc.message),
                    "context_project_id": context.get("project_id"),
                },
            )
            raise

    def _validate_tool_context(self, tool: Tool, name: str, context: JsonMap) -> None:
        try:
            tool._require_context_field(context, "project_id")
        except ToolExecutionError as exc:
            self._emit_event(
                "tool_context_error",
                {
                    "tool_name": name,
                    "error": exc.message,
                    "context_keys": list(context.keys()),
                },
            )
            raise

    def _emit_tool_called(
        self,
        name: str,
        args: JsonMap,
        context: JsonMap,
        start_time: float,
    ) -> None:
        self._emit_event(
            "tool_called",
            {
                "tool_name": name,
                "args_keys": list(args.keys()),
                "context_project_id": context.get("project_id"),
                "context_thread_id": context.get("thread_id"),
                "timestamp": start_time,
            },
        )

    async def _run_tool(self, tool: Tool, args: JsonMap, context: JsonMap) -> JsonMap:
        if tool.timeout_seconds:
            return await asyncio.wait_for(
                tool.run(args, context),
                timeout=tool.timeout_seconds,
            )
        return await tool.run(args, context)

    def _handle_success(self, name: str, result: JsonMap, start_time: float) -> None:
        elapsed = time.time() - start_time
        result_keys = list(result.keys())

        logger.info(
            "Tool executed successfully",
            extra={
                "tool_name": name,
                "elapsed_seconds": round(elapsed, 3),
                "result_keys": result_keys,
            },
        )

        self._emit_event(
            "tool_completed",
            {
                "tool_name": name,
                "elapsed_seconds": elapsed,
                "result_keys": result_keys,
            },
        )

    def _handle_timeout(self, name: str, tool: Tool, context: JsonMap) -> None:
        logger.error(
            "Tool execution timed out",
            extra={
                "tool_name": name,
                "timeout_seconds": tool.timeout_seconds,
                "project_id": context.get("project_id"),
            },
        )
        self._emit_event(
            "tool_timeout",
            {
                "tool_name": name,
                "timeout_seconds": tool.timeout_seconds,
            },
        )

    def _handle_unexpected_error(
        self, name: str, context: JsonMap, exc: Exception
    ) -> None:
        logger.exception(
            "Tool execution failed with unexpected error",
            extra={
                "tool_name": name,
                "project_id": context.get("project_id"),
                "error_type": type(exc).__name__,
            },
        )
        self._emit_event(
            "tool_failed",
            {
                "tool_name": name,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )

    def list_tools(self, public_only: bool = False) -> list[JsonMap]:
        tools = list(self._tools.values())
        if public_only:
            tools = [tool for tool in tools if tool.is_public]

        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "is_public": tool.is_public,
                "timeout_seconds": tool.timeout_seconds,
            }
            for tool in tools
        ]

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    async def unregister(self, name: str) -> bool:
        async with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info("Tool unregistered", extra={"tool_name": name})
                return True
            return False

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


tool_registry = ToolRegistry()
