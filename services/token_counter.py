import json
import math
import os


def count_chat_tokens(messages: list[dict], model: str = "gpt-4") -> int:
    """
    Zlicza tokeny w historii czatu używając tiktoken.

    Args:
        messages: Lista wiadomości w formacie OpenAI
        model: Nazwa modelu (domyślnie gpt-4 dla szerokiej kompatybilności)

    Returns:
        Przybliżona liczba tokenów
    """
    # tiktoken may download its dictionary on first use, without an HTTP timeout.
    # The terminal prompt must remain usable on a disconnected corporate network.
    if os.getenv("AICO_EXACT_TOKENS", "0") != "1":
        return 2 + sum(4 + math.ceil(len(json.dumps(message, ensure_ascii=False)) / 3)
                       for message in messages)
    import tiktoken
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    num_tokens = 0

    for message in messages:
        num_tokens += 4  # overhead per message

        for key, value in message.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str):
                num_tokens += len(encoding.encode(value, disallowed_special=()))

    num_tokens += 2  # overhead konwersacji

    return num_tokens


def format_token_count(token_count: int) -> str:
    """
    Formatuje liczbę tokenów w czytelny sposób.

    Returns:
        Sformatowany string (np. "1.2K", "15.3K", "128K")
    """
    if token_count < 1000:
        return str(token_count)
    elif token_count < 1_000_000:
        return f"{token_count / 1000:.1f}K"
    else:
        return f"{token_count / 1_000_000:.1f}M"


def get_token_warning(token_count: int) -> str | None:
    """
    Zwraca ostrzeżenie jeśli czat jest bardzo duży.
    """
    if token_count > 100_000:
        return "⚠️  >100K tokenów"
    elif token_count > 50_000:
        return "⚡ >50K tokenów"
    elif token_count > 20_000:
        return "📊 >20K tokenów"

    return None
