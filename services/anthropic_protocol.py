"""Translate AICO's tool history to Anthropic Messages; no network or secrets."""
import json
from services.agent_protocol import ProtocolError, parse_completion


def build_payload(messages, tools, max_tokens):
    if not isinstance(max_tokens, int) or max_tokens <= 0:
        raise ProtocolError("Claude wymaga dodatniego max_tokens.")
    system, history, pending = [], [], set()
    def append(role, blocks):
        if not blocks:
            return
        if history and history[-1]["role"] == role:
            history[-1]["content"].extend(blocks)
        else:
            history.append({"role": role, "content": blocks})
    for message in messages:
        role = message.get("role")
        text = message.get("content") or ""
        if not isinstance(text, str):
            raise ProtocolError("Claude: obsługiwany jest tekst i natywne tools.")
        if role == "system":
            if text:
                system.append(text)
            continue
        if role == "tool":
            call_id = message.get("tool_call_id")
            if call_id not in pending:
                raise ProtocolError("Claude: wynik narzędzia bez oczekującego wywołania.")
            pending.remove(call_id)
            append("user", [{"type": "tool_result", "tool_use_id": call_id, "content": text}])
            continue
        if role not in {"user", "assistant"} or pending:
            raise ProtocolError("Claude: niepoprawna kolejność historii narzędzi.")
        blocks = [{"type": "text", "text": text}] if text else []
        for call in message.get("tool_calls") or []:
            if role != "assistant" or call.get("type") != "function":
                raise ProtocolError("Claude: niepoprawne wywołanie narzędzia.")
            call_id, function = call.get("id"), call.get("function", {})
            try:
                arguments = json.loads(function.get("arguments", ""))
            except (ValueError, TypeError):
                raise ProtocolError("Claude: argumenty narzędzia muszą być JSON.") from None
            if not isinstance(arguments, dict) or not isinstance(call_id, str) or not call_id or call_id in pending:
                raise ProtocolError("Claude: niepoprawne argumenty lub ID narzędzia.")
            name = function.get("name")
            if not isinstance(name, str) or not name:
                raise ProtocolError("Claude: brak nazwy narzędzia.")
            pending.add(call_id)
            blocks.append({"type": "tool_use", "id": call_id, "name": name, "input": arguments})
        append(role, blocks)
    if pending or not history or history[0]["role"] != "user":
        raise ProtocolError("Claude: historia niekompletna lub bez pierwszej wiadomości użytkownika.")
    payload = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_tokens, "messages": history}
    if system:
        payload["system"] = "\n\n".join(system)
    if tools:
        native = []
        for tool in tools:
            if tool.get("type") != "function":
                raise ProtocolError("Claude: nieobsługiwany typ narzędzia.")
            function = tool["function"]
            native.append({"name": function["name"], "description": function.get("description", ""),
                           "input_schema": function.get("parameters") or {"type": "object", "properties": {}}})
        payload.update(tools=native, tool_choice={"type": "auto"})
    return payload


def parse_response(data):
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise ProtocolError("Claude: brak content w odpowiedzi API.")
    texts, calls = [], []
    for block in data["content"]:
        if not isinstance(block, dict):
            raise ProtocolError("Claude: niepoprawny blok odpowiedzi.")
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif kind == "tool_use":
            if not isinstance(block.get("input"), dict):
                raise ProtocolError("Claude: input narzędzia nie jest obiektem.")
            calls.append({"id": block.get("id"), "type": "function", "function": {
                "name": block.get("name"), "arguments": json.dumps(block["input"], ensure_ascii=False)}})
        else:
            # Thinking signatures must survive history round trips; not implemented here.
            raise ProtocolError("Claude: nieobsługiwany blok odpowiedzi; nie wykonano narzędzi.")
    reasons = {"end_turn": "stop", "stop_sequence": "stop", "tool_use": "tool_calls",
               "max_tokens": "length", "refusal": "content_filter"}
    reason = data.get("stop_reason")
    if reason not in reasons or (calls and reason != "tool_use"):
        raise ProtocolError("Claude: nieobsługiwany stop_reason; nie wykonano narzędzi.")
    usage = dict(data.get("usage") or {})
    if isinstance(usage.get("input_tokens"), int) and isinstance(usage.get("output_tokens"), int):
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    message = {"content": "\n".join(texts)}
    if calls:
        message["tool_calls"] = calls
    return parse_completion({"choices": [{"message": message, "finish_reason": reasons[reason]}], "usage": usage})
