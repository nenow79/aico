"""Bosch Model Farm: Azure OpenAI and Vertex OpenAI-compatible chat only."""
import os
import re
from urllib.parse import quote, urlsplit

from services.agent_protocol import Completion, ProtocolError, parse_completion
from services.network import NetworkError, post_completion
from services.anthropic_protocol import build_payload as build_anthropic_payload, parse_response as parse_anthropic_response

BMF_PREFIX = "bmf:"
DEFAULT_BASE_URL = "https://aoai-farm.bosch-temp.com/api"


def has_bmf_api_key() -> bool:
    key = os.getenv("BMF_API_KEY", "").strip()
    return bool(key and not any(marker in key.lower() for marker in ("tu_wklej", "your_api", "tutaj_wklej")))


def get_bmf_headers() -> dict[str, str]:
    if not has_bmf_api_key():
        raise NetworkError("Brak poprawnego BMF_API_KEY w środowisku lub .env.")
    return {"Authorization": "Bearer " + os.environ["BMF_API_KEY"].strip(),
            "Content-Type": "application/json"}


def resolve_bmf_model(model: str) -> tuple[str, str, str]:
    """Return URL, payload model and output-limit field; reject unknown families."""
    base = os.getenv("BMF_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise NetworkError("BMF_BASE_URL: wymagany URL HTTPS bez danych logowania, query i fragmentu.")
    if model.startswith("bmf:azure:"):
        deployment = model.removeprefix("bmf:azure:")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", deployment):
            raise ProtocolError("Niepoprawny deployment BMF Azure.")
        version = os.getenv("BMF_API_VERSION", "2025-04-01-preview").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:-preview)?", version):
            raise ProtocolError("Niepoprawny BMF_API_VERSION.")
        url = f"{base}/openai/deployments/{quote(deployment, safe='')}/chat/completions?api-version={version}"
        return url, deployment, "max_completion_tokens"
    if model.startswith("bmf:vertex:google/"):
        model_id = model.removeprefix("bmf:vertex:google/")
        if not re.fullmatch(r"gemini-[A-Za-z0-9._-]+", model_id):
            raise ProtocolError("Niepoprawny model BMF Gemini.")
        url = f"{base}/google/v1/endpoints/{quote(model_id, safe='')}/openapi/chat/completions"
        return url, "google/" + model_id, "max_tokens"
    if model.startswith("bmf:anthropic:"):
        model_id = model.removeprefix("bmf:anthropic:")
        if model_id not in {"claude-sonnet-4-6", "claude-sonnet-5-5"}:
            raise ProtocolError("Nieobsługiwany model BMF Claude.")
        url = f"{base}/google/v1/publishers/anthropic/models/{model_id}:rawPredict"
        return url, model_id, "anthropic"
    if model.startswith("bmf:msp:"):
        model_id = model.removeprefix("bmf:msp:")
        payload_models = {"qwen3.8-27b": "Qwen-38-27B", "glm-5.2": "zai-glm-52"}
        if model_id not in payload_models:
            raise ProtocolError("Nieobsługiwany model BMF MSP.")
        url = f"{base}/providers/bosch/msp/{model_id}/v1/chat/completions"
        return url, payload_models[model_id], "max_tokens"
    raise ProtocolError("Nieobsługiwany model BMF; użyj prefiksu bmf:azure:, bmf:vertex:google/ lub bmf:msp:.")


def complete_bmf(model: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
    url, payload_model, limit_field = resolve_bmf_model(model)
    payload = {"model": payload_model, "messages": messages}
    if tools:
        payload.update(tools=tools, tool_choice="auto")
    raw = os.getenv("LLM_MAX_OUTPUT_TOKENS", "16000").strip()
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if limit > 0:
        payload[limit_field] = limit
    if limit_field == "anthropic":
        if limit <= 0:
            raise ProtocolError("Claude wymaga dodatniego LLM_MAX_OUTPUT_TOKENS.")
        payload = build_anthropic_payload(messages, tools, limit)
    # Automatic Requests proxy/NO_PROXY selection; corporate CA/TLS stay enabled.
    data = post_completion(url, headers=get_bmf_headers(), json=payload,
                           connect_timeout_default=120)
    if limit_field == "anthropic":
        return parse_anthropic_response(data)
    return parse_completion(data)


def ask_bmf(model: str, messages: list[dict]) -> str:
    result = complete_bmf(model, messages)
    if result.message.get("tool_calls") or result.finish_reason in {"length", "max_tokens", "content_filter"}:
        raise ProtocolError("Odpowiedź wymaga narzędzi albo została ucięta/zablokowana.")
    content = result.message.get("content") or ""
    if not content.strip():
        raise ProtocolError("API zwróciło pustą odpowiedź; reasoning nie jest odpowiedzią.")
    return content
