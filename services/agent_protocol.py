"""OpenAI-compatible tool protocol. No network access or provider fallback."""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


class ProtocolError(ValueError):
    pass


@dataclass
class Completion:
    message: dict
    finish_reason: str | None
    usage: dict = field(default_factory=dict)


def normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            item["text"] for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    raise ProtocolError("Nieobsługiwany format message.content.")


def parse_completion(data: dict) -> Completion:
    """Never substitute reasoning for visible content, or dump raw API data."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProtocolError("API nie zwróciło choices.")
    choice = choices[0]
    raw = choice.get("message")
    if not isinstance(raw, dict):
        raise ProtocolError("API nie zwróciło message.")
    message = {"role": "assistant", "content": normalize_content(raw.get("content"))}
    calls = raw.get("tool_calls") or []
    if not isinstance(calls, list):
        raise ProtocolError("Niepoprawne tool_calls.")
    normalized = []
    seen = set()
    for call in calls:
        if not isinstance(call, dict) or call.get("type") != "function":
            raise ProtocolError("Nieobsługiwany typ tool call.")
        call_id = call.get("id")
        function = call.get("function")
        if not isinstance(call_id, str) or not call_id or call_id in seen:
            raise ProtocolError("Brak lub powtórzony tool_call_id.")
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise ProtocolError("Niepoprawna nazwa funkcji.")
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            raise ProtocolError("Argumenty funkcji muszą być tekstem JSON.")
        seen.add(call_id)
        normalized.append({"id": call_id, "type": "function", "function": {
            "name": function["name"], "arguments": arguments,
        }})
    if normalized:
        message["tool_calls"] = normalized
    return Completion(message, choice.get("finish_reason"), data.get("usage") or {})


def build_native_tools(servers: list[dict]) -> tuple[list[dict], dict]:
    tools, bindings = [], {}
    for server in servers:
        if not server.get("success"):
            continue
        for tool in server.get("tools", []):
            name = tool.get("name")
            if not isinstance(name, str) or not name or name == "secret_reveal":
                continue
            identity = json.dumps([server["name"], server["url"], name], ensure_ascii=False)
            alias = "mcp_" + hashlib.sha256(identity.encode()).hexdigest()[:40]
            if alias in bindings:
                raise ProtocolError("Powtórzona definicja narzędzia MCP.")
            bindings[alias] = (server, name)
            tools.append({"type": "function", "function": {
                "name": alias,
                "description": f"MCP {server['name']} / {name}\n{tool.get('description') or ''}",
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            }})
    return tools, bindings


def public_result(value: Any) -> Any:
    """Do not retain revealed secret values in model history or exports."""
    if isinstance(value, dict):
        return {key: ("[WYNIK SEKRETU ZABLOKOWANY W AICO]" if key == "secret_result"
                      else public_result(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [public_result(item) for item in value]
    return value


def unwrap_mcp_result(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("structured_content", "structuredContent"):
        if value.get(key) is not None:
            return value[key]
    content = value.get("content")
    if isinstance(content, list):
        texts = [item.get("text") for item in content if isinstance(item, dict)
                 and isinstance(item.get("text"), str)]
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except json.JSONDecodeError:
                pass
        return {"content": content}
    return value


def decode_arguments(call: dict) -> dict:
    try:
        value = json.loads(call["function"]["arguments"])
    except (ValueError, KeyError, TypeError) as error:
        raise ProtocolError("Niepoprawny JSON argumentów; narzędzie nie zostało wykonane.") from error
    if not isinstance(value, dict):
        raise ProtocolError("Argumenty muszą być obiektem JSON; narzędzie nie zostało wykonane.")
    return value


def serialize_result(value: Any) -> str:
    return json.dumps(public_result(value), ensure_ascii=False, default=str)
