"""Bounded retries for completions only; never replay MCP operations."""
import math
import os
import random
import sys
import time

import requests


class NetworkError(RuntimeError):
    """Safe diagnostic without URLs, headers, response bodies or proxy credentials."""


def seconds(name, default):
    try:
        value = float(os.getenv(name, str(default)))
        if math.isfinite(value) and 0 < value <= 3600:
            return value
    except ValueError:
        pass
    raise NetworkError(f"{name}: wymagane sekundy w zakresie (0, 3600].")


def describe_error(error):
    if isinstance(error, NetworkError):
        return str(error)
    if isinstance(error, requests.exceptions.SSLError):
        return "Błąd TLS. Sprawdź firmowy certyfikat CA (REQUESTS_CA_BUNDLE)."
    if isinstance(error, requests.exceptions.ProxyError):
        return "Błąd proxy. Sprawdź HTTP_PROXY, HTTPS_PROXY i NO_PROXY."
    if isinstance(error, (TimeoutError, requests.exceptions.Timeout)):
        return "Przekroczono limit czasu połączenia lub odpowiedzi."
    if isinstance(error, requests.exceptions.ConnectionError):
        return "Brak połączenia. Sprawdź sieć, VPN, proxy i adres serwera."
    return f"Błąd komunikacji ({type(error).__name__})."


def post_completion(url, *, headers, json):
    timeout = (seconds("LLM_CONNECT_TIMEOUT", 10), seconds("LLM_READ_TIMEOUT", 120))
    try:
        retries = int(os.getenv("LLM_RETRIES", "2"))
        if not 0 <= retries <= 5:
            raise ValueError()
    except ValueError:
        raise NetworkError("LLM_RETRIES: wymagana liczba całkowita od 0 do 5.") from None
    for attempt in range(retries + 1):
        delay = min(2 ** attempt + random.random(), 30)
        try:
            # Environment handling preserves NO_PROXY and the corporate CA bundle.
            response = requests.post(url, headers=headers, json=json, timeout=timeout)
        except requests.exceptions.SSLError as error:
            raise NetworkError(describe_error(error)) from None
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as error:
            message = describe_error(error)
        else:
            try:
                if response.ok:
                    try:
                        return response.json()
                    except ValueError:
                        raise NetworkError("API zwróciło niepoprawny JSON; sprawdź endpoint i proxy.") from None
                code = response.status_code
                message = f"LLM HTTP {code}. " + {
                    401: "Sprawdź klucz API.", 403: "Sprawdź uprawnienia i proxy.",
                    407: "Proxy wymaga uwierzytelnienia.",
                    400: "Sprawdź model, obsługę tools i długość kontekstu.",
                    429: "Limit zapytań lub budżetu dostawcy.",
                }.get(code, "Błąd dostawcy lub bramy proxy.")
                if code not in {429, 502, 503, 504}:
                    raise NetworkError(message)
                retry_after = response.headers.get("Retry-After", "")
                try:
                    requested_delay = float(retry_after)
                    if math.isfinite(requested_delay) and requested_delay >= 0:
                        if requested_delay > 30:
                            raise NetworkError(message + " Spróbuj później (Retry-After > 30 s).")
                        delay = max(delay, requested_delay)
                except ValueError:
                    pass
            finally:
                response.close()
        if attempt == retries:
            raise NetworkError(message + " Wyczerpano próby LLM.") from None
        print(f"{message} Ponowienie LLM {attempt + 1}/{retries} za {delay:.1f} s; Ctrl+C przerywa.",
              file=sys.stderr)
        time.sleep(delay)
