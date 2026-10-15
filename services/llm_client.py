from services.agent_protocol import Completion
from services.litellm_client import ask_litellm, complete_litellm, has_litellm_api_key
from services.openrouter_client import ask_openrouter, complete_openrouter, has_api_key as has_openrouter_api_key


OPENROUTER_PREFIX = "openrouter:"
LITELLM_PREFIX = "litellm:"


def get_model_provider(model: str) -> str:
    if model.startswith(LITELLM_PREFIX):
        return "litellm"

    return "openrouter"


def get_provider_label(model: str) -> str:
    provider = get_model_provider(model)

    if provider == "litellm":
        return "Bosch LiteLLM"

    return "OpenRouter"


def ask_llm(model: str, messages: list[dict[str, str]]) -> str:
    provider = get_model_provider(model)

    if provider == "litellm":
        return ask_litellm(
            model=model,
            messages=messages,
        )

    return ask_openrouter(
        model=model,
        messages=messages,
    )


def ask_completion(model: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
    if get_model_provider(model) == "litellm":
        return complete_litellm(model=model, messages=messages, tools=tools)
    return complete_openrouter(model=model, messages=messages, tools=tools)


def has_llm_api_key(model: str) -> bool:
    provider = get_model_provider(model)

    if provider == "litellm":
        return has_litellm_api_key()

    return has_openrouter_api_key()


def get_missing_api_key_message(model: str) -> str:
    provider = get_model_provider(model)

    if provider == "litellm":
        return "Brak LITELLM_API_KEY w pliku .env."

    return "Brak OPENROUTER_API_KEY w pliku .env."
