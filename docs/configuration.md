---
type: Reference
title: Konfiguracja aico
description: Pliki ustawień, wartości domyślne i pierwszeństwo zmiennych środowiska.
tags: [aico, configuration, proxy]
status: draft
sources:
  - id: code
    resource: 'Repozytorium aico: aico.py, config/*.json, .env.example, services/network.py, litellm_client.py, openrouter_client.py, mcp_client.py, mcp_runner.py i token_counter.py; working tree 2026-10-15'
---

# Konfiguracja

## Pliki i dostawcy

`config/models.json` mapuje etykiety na identyfikatory. Prefiks `litellm:` wybiera
LiteLLM; pozostałe identyfikatory trafiają do OpenRouter (prefiks `openrouter:` jest
opcjonalny). Wpis w pliku nie potwierdza dostępności modelu.
`config/mcp_servers.json` zawiera listę obiektów `name`, `url` i opcjonalne
`enabled`. Używaj JSON boolean `false`, aby wyłączyć serwer.[^code]

Obecne wpisy to vibecoder:8100, websearch:8200, redlake:8111 i sklr:8101 na localhost.
Ich dostępność i potrzeba użycia nie zostały potwierdzone.
Konfigurację i eksporty CLI lokalizuje względem katalogu aico.py.

`load_dotenv()` nie nadpisuje już ustawionych zmiennych środowiska. Plik `.env`
przechowuj w katalogu projektu; standardowe uruchomienie z tego katalogu lub przez
launcher ułatwia przewidywalną konfigurację. Nie zapisuj wartości kluczy w docs.

## Zmienne

| Zmienna | Domyślnie / znaczenie |
| --- | --- |
| LITELLM_API_KEY | Klucz wymagany dla LiteLLM; nagłówek x-litellm-api-key |
| OPENROUTER_API_KEY | Klucz OpenRouter; autoryzacja Bearer |
| LITELLM_URL | Firmowy endpoint chat/completions wskazany w .env.example i kodzie |
| LLM_MAX_OUTPUT_TOKENS | 16000; dodatnia liczba dodaje max_tokens, pusta/błędna/niedodatnia pomija limit w payloadzie |
| LLM_CONNECT_TIMEOUT | 10 s |
| LLM_READ_TIMEOUT | 120 s; przerwa w odczycie, nie limit całej odpowiedzi |
| LLM_RETRIES | 2 dodatkowe próby; dopuszczalne 0–5 |
| MCP_INIT_TIMEOUT | 10 s |
| MCP_DISCOVERY_TIMEOUT | 15 s na operację listowania danego serwera |
| MCP_CALL_TIMEOUT | 60 s na operację narzędzia |
| MCP_MAX_ITERATIONS | 40; dodatnia liczba całkowita; /steps zmienia budżet bieżącej sesji |
| AICO_EXACT_TOKENS | 0; tylko wartość 1 włącza tiktoken |
| HTTP_PROXY, HTTPS_PROXY, ALL_PROXY | Proxy obsługiwane przez biblioteki transportowe |
| NO_PROXY | Wyjątki; przykład projektu zawiera localhost,127.0.0.1,::1 |
| REQUESTS_CA_BUNDLE | Plik PEM z zaufanymi CA dla Requests/LLM |
| SSL_CERT_FILE | Plik CA dla HTTPS MCP przez HTTPX |

Timeouty konfigurowane w `network.seconds` muszą być skończoną liczbą w zakresie
`(0, 3600]`; niepoprawna wartość powoduje błąd, a nie wyłączenie timeoutu.
Zmienne proxy zapisane małymi i wielkimi literami powinny być spójne.
Przed zmianami zachowaj istniejące firmowe wyjątki NO_PROXY.[^code]

## Limity interpretacji

Timeouty HTTP nie ograniczają całej tury; transport MCP może potrzebować dodatkowego
czasu na zamknięcie po anulowaniu. Szacunek tokenów nie obejmuje wszystkich narzutów
modelu i schematów MCP. Tiktoken może pobierać słownik przy pierwszym użyciu;
przy pracy offline wymaga przygotowanego cache.

Ustawienia są opisem obecnego working tree. Wersje bibliotek nie są przypięte,
więc zachowanie proxy/CA wymaga odbioru na środowisku docelowym.

[^code]: Wartości i odgałęzienia konfiguracji w podanych plikach; bez sprawdzania zewnętrznych usług.
