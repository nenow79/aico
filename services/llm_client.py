"""Explicit provider routing; no cross-provider fallback."""
from services.agent_protocol import Completion, ProtocolError
from services.bmf_client import ask_bmf, complete_bmf, has_bmf_api_key
from services.litellm_client import ask_litellm, complete_litellm, has_litellm_api_key
from services.openrouter_client import ask_openrouter, complete_openrouter, has_api_key as has_openrouter_api_key

OPENROUTER_PREFIX = "openrouter:"
LITELLM_PREFIX = "litellm:"
BMF_PREFIX = "bmf:"
PROVIDER_LABELS = {"openrouter": "OpenRouter", "litellm": "Bosch LiteLLM", "bmf": "Bosch Model Farm"}


def get_model_provider(model: str) -> str:
    if not isinstance(model, str) or not model.strip():
        raise ProtocolError("Niepoprawny identyfikator modelu.")
    if model.startswith(LITELLM_PREFIX):
        return "litellm"
    if model.startswith(BMF_PREFIX):
        return "bmf"
    if model.startswith(OPENROUTER_PREFIX) or ":" not in model:
        return "openrouter"
    raise ProtocolError("Nieznany prefiks providera; model nie został wysłany.")


def get_provider_label(model: str) -> str:
    return PROVIDER_LABELS[get_model_provider(model)]


def ask_llm(model: str, messages: list[dict]) -> str:
    provider = get_model_provider(model)
    if provider == "bmf":
        return ask_bmf(model=model, messages=messages)
    if provider == "litellm":
        return ask_litellm(model=model, messages=messages)
    return ask_openrouter(model=model, messages=messages)


def ask_completion(model: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
    provider = get_model_provider(model)
    if provider == "bmf":
        return complete_bmf(model=model, messages=messages, tools=tools)
    if provider == "litellm":
        return complete_litellm(model=model, messages=messages, tools=tools)
    return complete_openrouter(model=model, messages=messages, tools=tools)


def has_llm_api_key(model: str) -> bool:
    provider = get_model_provider(model)
    if provider == "bmf":
        return has_bmf_api_key()
    if provider == "litellm":
        return has_litellm_api_key()
    return has_openrouter_api_key()


def get_missing_api_key_message(model: str) -> str:
    variable = {"bmf": "BMF_API_KEY", "litellm": "LITELLM_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[get_model_provider(model)]
    return f"Brak {variable} w środowisku lub pliku .env."
