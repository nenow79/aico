import asyncio
import json
from typing import Any

from fastmcp import Client
from services.network import describe_error, seconds


def run_async(coro):
    # A RuntimeError may occur AFTER dispatch. Never replay the operation.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    coro.close()
    raise RuntimeError("Synchroniczny klient MCP nie może działać w aktywnej pętli asyncio.")


def normalize_tool(tool: Any) -> dict:
    if hasattr(tool, "model_dump"):
        data = tool.model_dump()
    elif hasattr(tool, "dict"):
        data = tool.dict()
    else:
        data = {
            "name": getattr(tool, "name", ""),
            "description": getattr(tool, "description", ""),
            "inputSchema": getattr(tool, "inputSchema", {}),
        }

    return {
        "name": data.get("name", ""),
        "description": data.get("description") or "",
        "input_schema": data.get("inputSchema") or data.get("input_schema") or {},
    }


def normalize_tool_result(result: Any) -> Any:
    if result is None:
        return None

    if isinstance(result, (str, int, float, bool)):
        return result

    if isinstance(result, list):
        return [normalize_tool_result(item) for item in result]

    if isinstance(result, tuple):
        return [normalize_tool_result(item) for item in result]

    if isinstance(result, dict):
        return {
            str(key): normalize_tool_result(value)
            for key, value in result.items()
        }

    if hasattr(result, "model_dump"):
        return normalize_tool_result(result.model_dump())

    if hasattr(result, "dict"):
        return normalize_tool_result(result.dict())

    if hasattr(result, "content"):
        data = {
            "content": normalize_tool_result(getattr(result, "content", None)),
        }

        if hasattr(result, "structured_content"):
            data["structured_content"] = normalize_tool_result(
                getattr(result, "structured_content", None)
            )

        if hasattr(result, "is_error"):
            data["is_error"] = normalize_tool_result(
                getattr(result, "is_error", None)
            )

        return data

    if hasattr(result, "__dict__"):
        return normalize_tool_result(vars(result))

    return str(result)


async def async_list_mcp_tools(url: str) -> list[dict]:
    limit = seconds("MCP_DISCOVERY_TIMEOUT", 15)
    async with asyncio.timeout(limit):
        async with Client(url, timeout=limit, init_timeout=seconds("MCP_INIT_TIMEOUT", 10)) as client:
            tools = await client.list_tools()
            return [normalize_tool(tool) for tool in tools]


async def async_test_mcp_connection(url: str) -> dict:
    tools = await async_list_mcp_tools(url)

    return {
        "success": True,
        "message": f"Połączono poprawnie. Liczba narzędzi: {len(tools)}",
        "tools_count": len(tools),
    }


async def async_call_mcp_tool(url: str, tool_name: str, arguments: dict) -> Any:
    limit = seconds("MCP_CALL_TIMEOUT", 60)
    async with asyncio.timeout(limit):
        async with Client(url, timeout=limit, init_timeout=seconds("MCP_INIT_TIMEOUT", 10)) as client:
            result = await client.call_tool(tool_name, arguments)
            return normalize_tool_result(result)


def list_mcp_tools(url: str) -> dict:
    try:
        tools = run_async(async_list_mcp_tools(url))

        return {
            "success": True,
            "tools": tools,
            "tools_count": len(tools),
            "error": "",
        }

    except Exception as error:
        return {
            "success": False,
            "tools": [],
            "tools_count": 0,
            "error": describe_error(error),
        }


def test_mcp_connection(url: str) -> dict:
    try:
        return run_async(async_test_mcp_connection(url))

    except Exception as error:
        return {
            "success": False,
            "message": "",
            "tools_count": 0,
            "error": describe_error(error),
        }


def call_mcp_tool(url: str, tool_name: str, arguments_json: str) -> dict:
    try:
        arguments_json = arguments_json.strip()

        if arguments_json:
            arguments = json.loads(arguments_json)
        else:
            arguments = {}

        if not isinstance(arguments, dict):
            return {
                "success": False,
                "result": None,
                "error": "Argumenty muszą być obiektem JSON, np. {} albo {\"subpath\": \"src\"}.",
            }

        result = run_async(
            async_call_mcp_tool(
                url=url,
                tool_name=tool_name,
                arguments=arguments,
            )
        )

        return {
            "success": True,
            "result": result,
            "error": "",
        }

    except json.JSONDecodeError as error:
        return {
            "success": False,
            "result": None,
            "error": f"Niepoprawny JSON: {error}",
        }

    except Exception as error:
        return {
            "success": False,
            "result": None,
            "error": describe_error(error),
        }


def format_tool_schema(tool: dict) -> str:
    input_schema = tool.get("input_schema") or {}

    if not input_schema:
        return "{}"

    return json.dumps(input_schema, ensure_ascii=False, indent=2)


def format_tool_result(result: Any) -> str:
    normalized = normalize_tool_result(result)

    if isinstance(normalized, dict):
        structured_content = normalized.get("structured_content")

        if structured_content is not None:
            return json.dumps(
                structured_content,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        content = normalized.get("content")

        if isinstance(content, list) and content:
            first_item = content[0]

            if isinstance(first_item, dict):
                text = first_item.get("text")

                if isinstance(text, str):
                    try:
                        parsed_text = json.loads(text)
                        return json.dumps(
                            parsed_text,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        )
                    except json.JSONDecodeError:
                        return text

    if isinstance(normalized, str):
        return normalized

    return json.dumps(
        normalized,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
