"""
MCP automatic runner – terminal version (bez Streamlit).

Logika zaczerpnięta z harness services/mcp_automatic_runner.py,
oczyszczona ze wszystkich zależności st.*.

Callbacki:
  on_message(role, content)  – wywoływany dla każdej nowej wiadomości
  on_status(status, message) – informacje o postępie (opcjonalny)
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from services.llm_client import ask_llm
from services.mcp_client import (
    call_mcp_tool,
    format_tool_result,
    format_tool_schema,
    list_mcp_tools,
)


# ---------------------------------------------------------------------------
# Parsowanie propozycji tool call z odpowiedzi modelu
# ---------------------------------------------------------------------------

CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

PLACEHOLDER_VALUES = {
    "nazwa_toola", "tool_name", "name_of_tool",
    "nazwa_narzędzia", "nazwa_narzedzia",
    "nazwa_serwera", "server_name", "nazwa_servera",
    "nazwa_mcp", "mcp_server",
}

NATIVE_TOOL_CALL_MARKERS = [
    "<|tool_calls_section_begin|>",
    "<|tool_call_begin|>",
    "<|tool_call_argument_begin|>",
    "functions.",
]

TOOL_RESULT_CONTEXT_MAX_CHARS = 8_000


def _extract_json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    objects = []

    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            objects.append(parsed)

    return objects


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in PLACEHOLDER_VALUES


def _normalize_arguments(arguments: Any) -> dict:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("arguments musi być obiektem JSON.")


def _normalize_proposal(data: dict) -> dict | None:
    for wrapper_key in ["mcp_tool_call", "tool_call", "mcp_call"]:
        nested = data.get(wrapper_key)
        if isinstance(nested, dict):
            data = nested
            break

    tool_name = data.get("tool") or data.get("tool_name") or data.get("name")

    if not tool_name or not isinstance(tool_name, str):
        return None
    if _is_placeholder(tool_name):
        return None

    server_name = (
        data.get("mcp_server")
        or data.get("server")
        or data.get("server_name")
        or data.get("mcp_server_name")
    )
    if _is_placeholder(server_name):
        server_name = None

    arguments = _normalize_arguments(data.get("arguments", data.get("args", {})))

    return {
        "mcp_server": server_name,
        "tool": tool_name,
        "arguments": arguments,
    }


def parse_tool_call(text: str) -> dict | None:
    """Wyciąga propozycję tool call z tekstu modelu. Zwraca None jeśli brak."""
    if not isinstance(text, str) or not text.strip():
        return None

    candidates = []

    for match in CODE_BLOCK_PATTERN.findall(text):
        candidates.extend(_extract_json_objects(match))

    candidates.extend(_extract_json_objects(text))

    for candidate in candidates:
        try:
            proposal = _normalize_proposal(candidate)
            if proposal:
                return proposal
        except Exception:
            continue

    return None


def contains_native_tool_syntax(text: str) -> bool:
    if not isinstance(text, str):
        return False
    return any(marker in text for marker in NATIVE_TOOL_CALL_MARKERS)


def looks_like_incomplete_tool_call(text: str) -> bool:
    """Recognizes a truncated text-JSON MCP proposal without mistaking it for a final reply."""
    if not isinstance(text, str):
        return False

    lowered = text.lower()
    has_tool_fields = '"tool"' in lowered and (
        '"mcp_server"' in lowered or '"arguments"' in lowered
    )
    if not has_tool_fields:
        return False

    stripped = text.strip()
    has_unclosed_json_fence = "```json" in lowered and stripped.count("```") % 2 != 0
    ends_like_partial_json = not stripped.endswith("}")

    return has_unclosed_json_fence or ends_like_partial_json


def _tool_result_context_limit() -> int:
    raw_value = os.getenv("MCP_TOOL_RESULT_CONTEXT_MAX_CHARS", "").strip()

    if not raw_value:
        return TOOL_RESULT_CONTEXT_MAX_CHARS

    try:
        value = int(raw_value)
    except ValueError:
        return TOOL_RESULT_CONTEXT_MAX_CHARS

    return value if value > 0 else TOOL_RESULT_CONTEXT_MAX_CHARS


def _compact_messages_for_model(messages: list[dict]) -> list[dict]:
    """Keeps exported history intact while bounding verbose MCP results sent back to the LLM."""
    limit = _tool_result_context_limit()
    compacted = []

    for message in messages:
        content = message.get("content", "")

        if (
            message.get("role") == "assistant"
            and isinstance(content, str)
            and content.startswith("### MCP automatic")
            and len(content) > limit
        ):
            omitted = len(content) - limit
            content = (
                f"{content[:limit]}\n\n"
                f"[Wynik MCP skrócony dla kontekstu modelu; pominięto {omitted} znaków. "
                "Użyj precyzyjnego odczytu pliku, jeśli potrzebujesz brakującego fragmentu.]"
            )

        compacted.append({"role": message.get("role", "user"), "content": content})

    return compacted


# ---------------------------------------------------------------------------
# Ładowanie serwerów MCP z pliku konfiguracyjnego
# ---------------------------------------------------------------------------

def load_mcp_servers(path: str | Path = "config/mcp_servers.json") -> list[dict]:
    """
    Wczytuje listę serwerów MCP z pliku JSON.

    Format pliku:
        [
            { "name": "vibecoder", "url": "http://localhost:8100/mcp" },
            { "name": "redlake",   "url": "http://localhost:9000/mcp" }
        ]
    """
    config_path = Path(path)

    if not config_path.exists():
        return []

    with config_path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

    return [
        {"name": str(s.get("name", "")), "url": str(s.get("url", ""))}
        for s in data
        if isinstance(s, dict) and s.get("enabled", True) and s.get("name") and s.get("url")
    ]


def load_all_tools(servers: list[dict]) -> list[dict]:
    """
    Pobiera listę tools ze wszystkich serwerów.

    Zwraca listę słowników:
        { "name", "url", "tools": [...], "error": "" }
    """
    result = []

    for server in servers:
        info = list_mcp_tools(server["url"])
        result.append({
            "name": server["name"],
            "url": server["url"],
            "tools": info.get("tools", []),
            "error": info.get("error", ""),
            "success": info.get("success", False),
        })

    return result


# ---------------------------------------------------------------------------
# Budowanie system prompt z dostępnymi narzędziami
# ---------------------------------------------------------------------------

def build_tools_context(servers_with_tools: list[dict]) -> str:
    """Buduje blok systemu z opisem wszystkich dostępnych narzędzi MCP."""
    parts = [
        "## MCP automatic mode",
        "",
        "Jesteś w trybie automatic.",
        "Możesz zaproponować użycie maksymalnie jednego narzędzia MCP w jednej odpowiedzi.",
        "Jeśli chcesz użyć narzędzia, zwróć dokładnie jeden kompletny blok JSON i niczego nie wykonuj samodzielnie.",
        "Nie używaj natywnego formatu tool calls (functions.tool, <|tool_calls_section_begin|> itp.).",
        "Nie twórz fikcyjnych wyników MCP.",
        "Dla zmian kodu preferuj małe, precyzyjne wywołania edit_file. Nie używaj rewrite_full_file, jeśli zmianę można podzielić.",
        "Jeśli payload narzędzia byłby bardzo długi, podziel pracę na kolejne iteracje zamiast zwracać ucięty JSON.",
        "Wynik narzędzia zostanie dodany przez aplikację po wykonaniu.",
        "",
        "Format propozycji:",
        "",
        "```json",
        "{",
        '  "mcp_server": "nazwa_serwera",',
        '  "tool": "nazwa_toola",',
        '  "arguments": {}',
        "}",
        "```",
        "",
        "Jeśli nie potrzebujesz już narzędzi MCP, odpowiedz normalnie bez JSON tool call.",
        "",
        "## Dostępne narzędzia MCP",
        "",
    ]

    for server in servers_with_tools:
        if not server.get("success") or not server.get("tools"):
            continue

        parts += [
            f"### Serwer: `{server['name']}`",
            "",
        ]

        for tool in server["tools"]:
            parts += [f"#### Tool: `{tool['name']}`", ""]

            if tool.get("description"):
                parts += [tool["description"], ""]

            parts += [
                "Schema argumentów:",
                "",
                "```json",
                format_tool_schema(tool),
                "```",
                "",
            ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Znajdowanie serwera i narzędzia z propozycji modelu
# ---------------------------------------------------------------------------

def _find_server(proposal: dict, servers_with_tools: list[dict]) -> dict | None:
    requested = proposal.get("mcp_server")

    if requested:
        requested = str(requested).strip().lower()
        for server in servers_with_tools:
            if server["name"].strip().lower() == requested:
                return server

    if len(servers_with_tools) == 1:
        return servers_with_tools[0]

    return None


def _tool_exists(server: dict, tool_name: str) -> bool:
    return any(t["name"] == tool_name for t in server.get("tools", []))


# ---------------------------------------------------------------------------
# Główna pętla automatic
# ---------------------------------------------------------------------------

def run_automatic(
    messages: list[dict],
    model: str,
    servers_with_tools: list[dict],
    on_message: Callable[[str, str], None],
    on_status: Callable[[str, str], None] | None = None,
    max_iterations: int = 15,
) -> list[dict]:
    """
    Uruchamia pętlę MCP automatic.

    Args:
        messages:           Historia czatu (modyfikowana in-place, zwracana).
        model:              Identyfikator modelu (np. "openrouter:...")
        servers_with_tools: Lista serwerów z załadowanymi tools.
        on_message:         Callback (role, content) – wywoływany dla każdej wiadomości.
        on_status:          Opcjonalny callback (status, message) – info o postępie.
        max_iterations:     Maksymalna liczba iteracji tool call.

    Returns:
        Zaktualizowana lista messages.
    """

    def status(s: str, m: str = ""):
        if on_status:
            on_status(s, m)

    def append(role: str, content: str, emit: bool = True):
        messages.append({"role": role, "content": content})
        if emit and role != "system":
            on_message(role, content)

    # --- Buduj kontekst MCP i wstrzyknij jako system message ---
    tools_context = build_tools_context(servers_with_tools)

    # Wstaw system message z kontekstem MCP za pierwszą wiadomością system (lub na początku)
    mcp_system = {"role": "system", "content": tools_context}
    if messages and messages[0]["role"] == "system":
        messages.insert(1, mcp_system)
    else:
        messages.insert(0, mcp_system)

    status("starting", "Uruchamianie MCP automatic...")
    retry_instruction = ""

    for iteration in range(1, max_iterations + 1):
        status("waiting_for_model", f"Iteracja {iteration}/{max_iterations} – czekam na model...")

        # Prompt kontynuacji (od 2. iteracji model już ma kontekst w historii)
        continuation_prompt = (
            f"Kontynuuj zadanie w trybie MCP automatic (iteracja {iteration}/{max_iterations}).\n\n"
            "Jeśli potrzebujesz kolejnego narzędzia – zwróć JSON tool call.\n"
            "Jeśli zadanie jest zakończone – odpowiedz finalnie bez JSON tool call."
            f"{retry_instruction}"
        )

        messages_for_model = _compact_messages_for_model(messages) + [
            {"role": "user", "content": continuation_prompt}
        ]
        retry_instruction = ""

        # --- Wywołanie LLM ---
        try:
            ai_reply = ask_llm(model=model, messages=messages_for_model)
        except Exception as error:
            append("assistant", f"### Błąd LLM\n\n```text\n{error}\n```")
            status("error", str(error))
            break

        if not isinstance(ai_reply, str) or not ai_reply.strip():
            append("assistant", "### MCP automatic zatrzymany\n\nModel zwrócił pustą odpowiedź.")
            status("error", "Pusta odpowiedź modelu.")
            break

        if contains_native_tool_syntax(ai_reply):
            append(
                "assistant",
                "### MCP automatic zatrzymany\n\n"
                "Model użył natywnego formatu tool call zamiast wymaganego JSON MCP.\n\n"
                f"```text\n{ai_reply}\n```",
            )
            status("error", "Natywny format tool call.")
            break

        proposal = parse_tool_call(ai_reply)

        # Model began a text-JSON tool call but its response was cut off. Do not
        # mistake that for a completed task: retry with an explicit recovery prompt.
        if not proposal and looks_like_incomplete_tool_call(ai_reply):
            status(
                "retrying",
                "Niekompletny JSON tool call — proszę model o kompletną, mniejszą operację...",
            )
            retry_instruction = (
                "\n\nPoprzednia odpowiedź zawierała niekompletny JSON tool call i nie została "
                "wykonana. Ponów działanie jako jeden kompletny JSON. Jeśli operacja jest zbyt "
                "duża, podziel ją na mniejsze wywołania edit_file."
            )
            continue

        # Brak tool call → model skończył zadanie
        if not proposal:
            append("assistant", ai_reply)
            status("finished", "Zadanie zakończone.")
            break

        # --- Znajdź serwer ---
        server = _find_server(proposal, servers_with_tools)

        if not server:
            err_msg = (
                f"### MCP automatic · iteracja {iteration}/{max_iterations}\n\n"
                f"Nie znaleziono serwera MCP: `{proposal.get('mcp_server')}`"
            )
            append("assistant", err_msg)
            status("error", "Nie znaleziono serwera.")
            break

        tool_name = proposal["tool"]

        # --- Sprawdź czy tool istnieje ---
        if not _tool_exists(server, tool_name):
            err_msg = (
                f"### MCP automatic · iteracja {iteration}/{max_iterations}\n\n"
                f"Tool `{tool_name}` nie istnieje na serwerze `{server['name']}`."
            )
            append("assistant", err_msg)
            status("error", f"Tool {tool_name} nie istnieje.")
            break

        status("executing_tool", f"Wykonuję `{tool_name}` na `{server['name']}`...")

        # --- Wywołaj narzędzie ---
        result = call_mcp_tool(
            url=server["url"],
            tool_name=tool_name,
            arguments_json=json.dumps(proposal.get("arguments", {}), ensure_ascii=False),
        )

        if result["success"]:
            formatted = format_tool_result(result["result"])
            tool_msg = (
                f"### MCP automatic · iteracja {iteration}/{max_iterations}\n\n"
                f"**Serwer:** `{server['name']}`  \n"
                f"**Tool:** `{tool_name}`  \n"
                f"**Argumenty:**\n\n"
                f"```json\n{json.dumps(proposal.get('arguments', {}), ensure_ascii=False, indent=2)}\n```\n\n"
                f"**Wynik:**\n\n"
                f"```\n{formatted}\n```"
            )
        else:
            tool_msg = (
                f"### MCP automatic · błąd · iteracja {iteration}/{max_iterations}\n\n"
                f"**Serwer:** `{server['name']}`  \n"
                f"**Tool:** `{tool_name}`  \n"
                f"**Błąd:**\n\n"
                f"```text\n{result['error']}\n```"
            )
            append("assistant", tool_msg)
            status("error", f"Błąd tool {tool_name}: {result['error']}")
            break

        append("assistant", tool_msg)

    else:
        append(
            "assistant",
            f"### MCP automatic zakończony\n\nOsiągnięto limit `{max_iterations}` iteracji.",
        )
        status("limit_reached", f"Osiągnięto limit {max_iterations} iteracji.")

    # Usuń wstrzyknięty system message MCP z historii (żeby nie zaśmiecał eksportu)
    messages[:] = [m for m in messages if m.get("content") != tools_context]

    return messages
