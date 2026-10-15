import json
import os
from typing import Any

import requests
from dotenv import load_dotenv
from services.agent_protocol import Completion, ProtocolError, parse_completion
from services.network import post_completion

load_dotenv()

LITELLM_URL = os.getenv(
    "LITELLM_URL",
    "https://litellm.orchestration.bbm.ai.bosch.com/v1/chat/completions",
)


def get_litellm_api_key() -> str | None:
    return os.getenv("LITELLM_API_KEY")


def has_litellm_api_key() -> bool:
    api_key = get_litellm_api_key()
    return bool(
        api_key
        and "tu_wklej" not in api_key
        and "your" not in api_key.lower()
    )


def normalize_litellm_model(model: str) -> str:
    if model.startswith("litellm:"):
        return model.removeprefix("litellm:")

    return model


def get_proxies() -> dict | None:
    http_proxy = os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("HTTPS_PROXY")

    if http_proxy or https_proxy:
        return {
            "http": http_proxy,
            "https": https_proxy,
        }

    return None


def get_litellm_headers() -> dict[str, str]:
    api_key = get_litellm_api_key()

    if not api_key:
        raise ValueError("Brak LITELLM_API_KEY")

    return {
        "Content-Type": "application/json",
        "x-litellm-api-key": api_key,
    }


def normalize_message_content(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")

                if text:
                    parts.append(str(text))
            else:
                parts.append(str(item))

        return "\n".join(parts)

    if isinstance(content, dict):
        text = content.get("text") or content.get("content")

        if text:
            return str(text)

        return json.dumps(content, ensure_ascii=False, indent=2)

    return str(content)


def extract_litellm_content(data: dict) -> str:
    choices = data.get("choices")

    if not choices:
        raise ProtocolError("API nie zwróciło choices.")

    first_choice = choices[0]
    message = first_choice.get("message", {})

    content = normalize_message_content(message.get("content"))

    if content.strip():
        return content

    return ""


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


def complete_litellm(model: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
    payload = {
        "model": normalize_litellm_model(model),
        "messages": messages,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    max_output_tokens = get_max_output_tokens()
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens

    data = post_completion(
        LITELLM_URL,
        headers=get_litellm_headers(),
        json=payload,
    )

    return parse_completion(data)


def ask_litellm(model: str, messages: list[dict]) -> str:
    result = complete_litellm(model, messages)
    if result.message.get("tool_calls") or result.finish_reason in {"length", "max_tokens", "content_filter"}:
        raise ProtocolError("Odpowiedź wymaga narzędzi albo została ucięta/zablokowana.")
    content = result.message.get("content") or ""
    if not content.strip():
        raise ProtocolError("API zwróciło pustą odpowiedź; reasoning nie jest odpowiedzią.")
    return content
