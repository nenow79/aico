import os
import requests
from dotenv import load_dotenv
from services.agent_protocol import Completion, ProtocolError, parse_completion

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_api_key() -> str | None:
    return os.getenv("OPENROUTER_API_KEY")


def has_api_key() -> bool:
    api_key = get_api_key()
    return bool(api_key and "tutaj_wklej" not in api_key and "tu_wklej" not in api_key)


def normalize_openrouter_model(model: str) -> str:
    if model.startswith("openrouter:"):
        return model.removeprefix("openrouter:")

    return model


def get_headers() -> dict[str, str]:
    api_key = get_api_key()

    if not api_key:
        raise ValueError("Brak OPENROUTER_API_KEY")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://aico-terminal.local",
        "X-Title": "aico terminal chat",
    }


def get_max_output_tokens() -> int | None:
    """Returns an optional completion limit configured for the harness."""
    raw_value = os.getenv("LLM_MAX_OUTPUT_TOKENS", "16000").strip()

    if not raw_value:
        return None

    try:
        value = int(raw_value)
    except ValueError:
        return None

    return value if value > 0 else None


def complete_openrouter(model: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
    payload = {
        "model": normalize_openrouter_model(model),
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    max_output_tokens = get_max_output_tokens()
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    response = requests.post(
        OPENROUTER_URL,
        headers=get_headers(),
        json=payload,
        timeout=120,
    )

    if not response.ok:
        raise requests.HTTPError(f"OpenRouter HTTP {response.status_code}")
    return parse_completion(response.json())


def ask_openrouter(model: str, messages: list[dict]) -> str:
    result = complete_openrouter(model, messages)
    if result.message.get("tool_calls") or result.finish_reason in {"length", "max_tokens", "content_filter"}:
        raise ProtocolError("Odpowiedź wymaga narzędzi albo została ucięta/zablokowana.")
    content = result.message.get("content") or ""
    if not content.strip():
        raise ProtocolError("API zwróciło pustą odpowiedź.")
    return content
