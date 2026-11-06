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

`config/models.json` mapuje etykiety na identyfikatory. Provider wybierany jest
przed modelem i pozostaje stały do końca procesu, także po `/clear`.
`/model` pokazuje wyłącznie modele wybranego providera.

| Prefiks | Provider / protokół |
| --- | --- |
| `litellm:` | Bosch LiteLLM |
| `openrouter:` lub identyfikator bez dwukropka | OpenRouter, zgodność ze starszą konfiguracją |
| `bmf:azure:DEPLOYMENT` | Bosch Model Farm, Azure OpenAI chat/completions |
| `bmf:vertex:google/GEMINI_ID` | Bosch Model Farm, Vertex OpenAI-compatible |
| `bmf:msp:MODEL_ID` | Bosch Model Farm, Bosch MSP OpenAI-compatible (Qwen/GLM) |
| `bmf:anthropic:MODEL_ID` | Bosch Model Farm, natywny Claude Vertex rawPredict |

Nieznany prefiks jest odrzucany, a nie kierowany do OpenRouter.
Wpis w pliku nie potwierdza dostępności modelu ani uprawnień subskrypcji.
`config/mcp_servers.json` zawiera listę obiektów `name`, `url` i opcjonalne
`enabled`. Używaj JSON boolean `false`, aby wyłączyć serwer.[^code]

Obecne wpisy to vibecoder:8100, websearch:8200, redlake:8111 i sklr:8101 na localhost.
Ich dostępność i potrzeba użycia nie zostały potwierdzone.
Konfigurację i eksporty CLI lokalizuje względem katalogu aico.py.

CLI wskazuje jawnie `.env` obok `aico.py`; ustawione zmienne środowiska mają
pierwszeństwo. Moduły dotychczasowych klientów zachowują także własne `load_dotenv()`.
Plik `.env` przechowuj lokalnie i nie wersjonuj go. Nie zapisuj kluczy w docs,
promptach, eksporcie ani argumentach narzędzi.

## Zmienne

| Zmienna | Domyślnie / znaczenie |
| --- | --- |
| LITELLM_API_KEY | Klucz wymagany dla LiteLLM; nagłówek x-litellm-api-key |
| OPENROUTER_API_KEY | Klucz OpenRouter; autoryzacja Bearer |
| BMF_API_KEY | Indywidualny klucz BMF; autoryzacja Bearer |
| BMF_BASE_URL | https://aoai-farm.bosch-temp.com/api; wymagane HTTPS bez danych logowania, query i fragmentu |
| BMF_API_VERSION | 2025-04-01-preview; tylko endpoint Azure OpenAI |
| LITELLM_URL | Firmowy endpoint chat/completions wskazany w .env.example i kodzie |
| LLM_MAX_OUTPUT_TOKENS | 16000; dodatnia liczba dodaje max_tokens, a w BMF Azure max_completion_tokens; pusta/błędna/niedodatnia pomija limit |
| LLM_CONNECT_TIMEOUT | LiteLLM/BMF: 120 s; OpenRouter: 10 s; jawna wartość nadpisuje domyślne limity |
| LLM_READ_TIMEOUT | 120 s; przerwa w odczycie, nie limit całej odpowiedzi |
| LLM_RETRIES | 2 dodatkowe próby; dopuszczalne 0–5 |
| MCP_INIT_TIMEOUT | 10 s |
| MCP_DISCOVERY_TIMEOUT | 15 s na operację listowania danego serwera |
| MCP_CALL_TIMEOUT | 60 s na operację narzędzia |
| MCP_MAX_ITERATIONS | 40; dodatnia liczba całkowita; /steps zmienia budżet bieżącej sesji |
| MCP_AUTO_CONNECT | 1 (domyślnie); łączy serwery MCP automatycznie przy starcie; 0 wyłącza auto-connect, /mcp connect łączy ręcznie |
| AICO_EXACT_TOKENS | 0; tylko wartość 1 włącza tiktoken |
| HTTP_PROXY, HTTPS_PROXY, ALL_PROXY | Proxy obsługiwane przez biblioteki transportowe |
| NO_PROXY | Wyjątki; przykład projektu zawiera localhost,127.0.0.1,::1 |
| REQUESTS_CA_BUNDLE | Plik PEM z zaufanymi CA dla Requests/LLM |
| SSL_CERT_FILE | Plik CA dla HTTPS MCP przez HTTPX |

Timeouty konfigurowane w `network.seconds` muszą być skończoną liczbą w zakresie
`(0, 3600]`; niepoprawna wartość powoduje błąd, a nie wyłączenie timeoutu.
Zmienne proxy zapisane małymi i wielkimi literami powinny być spójne.
Przed zmianami zachowaj istniejące firmowe wyjątki NO_PROXY.[^code]

### Pierwszeństwo proxy LiteLLM

LiteLLM używa `proxies=get_proxies()` jak w aidev: jeśli `HTTP_PROXY` lub
`HTTPS_PROXY` ma wartość, przekazuje mapę obu schematów do Requests. Jawny wpis
dla schematu ma pierwszeństwo przed automatycznym wyborem, także gdy `NO_PROXY`
pasuje do adresu LiteLLM. Wpis z `None` zostaje usunięty z mapy podczas scalania;
nie jest to gwarancja trybu direct, bo może pozostać np. `ALL_PROXY`.
Gdy obie zmienne są puste/nieustawione, Requests wybiera proxy automatycznie,
z uwzględnieniem `NO_PROXY`, innych zmiennych proxy i ustawień systemowych.
Puste wpisy `.env` nie nadpisują odziedziczonych zmiennych i nie wyłączają proxy.

Jest to przywrócenie zachowania sprzed `bc95b3f`, nie potwierdzenie przyczyny
zgłoszonej awarii. OpenRouter i MCP zachowują automatyczny wybór proxy.
`REQUESTS_CA_BUNDLE` i weryfikacja TLS pozostają aktywne.
Jeżeli wcześniej ustawiono `LLM_CONNECT_TIMEOUT=10` w środowisku lub `.env`,
nowy domyślny limit LiteLLM go nie nadpisze; usuń override albo ustaw 120 s.
Nowy `.env.example` pozostawia tę zmienną zakomentowaną.

## Bosch Model Farm

Początkowe wpisy: `bmf:azure:gpt-5.4-mini-2026-03-17` oraz
`bmf:vertex:google/gemini-3.1-flash-lite`. Pochodzą z Model Endpoint Reference V61,
odczytanego w Docupedii; nie wykonano wywołań modeli ani testu subskrypcji.

Azure: `/openai/deployments/DEPLOYMENT/chat/completions?api-version=VERSION`.
Payload `model` zawiera deployment. Adapter używa `max_completion_tokens`;
zgodność tego parametru wymaga próby z rzeczywistym modelem.
Gemini: `/google/v1/endpoints/GEMINI_ID/openapi/chat/completions`.
Payload `model` zawiera prefiks `google/`, którego nie ma w ścieżce endpointu.
Oba warianty wysyłają Bearer, messages oraz opcjonalne natywne tools/tool_choice.

BMF korzysta z automatycznego wyboru proxy Requests z NO_PROXY i firmowym CA;
nie przejmuje jawnego `get_proxies()` z LiteLLM. Nie wyłączaj weryfikacji TLS.
Dodano Claude Sonnet 4.6/5.5 przez
`/google/v1/publishers/anthropic/models/MODEL_ID:rawPredict`, z
`anthropic_version=vertex-2023-10-16`. Adapter konwertuje tekst, system,
tool_calls i role=tool na bloki tool_use/tool_result oraz odpowiedź z powrotem
na protokół runnera AICO. Claude wymaga dodatniego LLM_MAX_OUTPUT_TOKENS.
Extended thinking i streaming nie są włączane; nieobsługiwane bloki odpowiedzi
lub stop_reason zatrzymują przetwarzanie przed wykonaniem narzędzi.

Dodano Qwen 3.8 27B i GLM-5.2 przez Bosch MSP:
`/providers/bosch/msp/MODEL_ID/v1/chat/completions`.
ID ścieżki `qwen3.8-27b` używa payload model `Qwen-38-27B`,
a `glm-5.2` używa `zai-glm-52`. Nie są to identyczne identyfikatory.
Lista zawiera też GPT-6 Sol/Luna, Gemini 3.7 Flash i Gemini 4 Argon.
Nazwy New i przykładowe koszty zadania nie są częścią identyfikatorów modeli.

Rozszerzenie przeszło testy offline (63/63 w całym zestawie; zakres w CURRENT).
Nadal wymaga próby każdego modelu/subskrypcji;
nie wykonywano płatnych wywołań. Źródła: Model Endpoint Reference V61 (#1, #2,
#3, #6) oraz Code Examples V62, Claude Opus/Vertex — wzorzec rawPredict.

Źródło: [Model Endpoint Reference V61, sekcje Endpoint #1 i #3](https://inside-docupedia.bosch.com/confluence2/pages/viewpage.action?pageId=961642929).
Odczyt tekstowy nie wykonuje makr i nie zachowuje wszystkich scaleń tabel.
Wiedza ogólna o usłudze pozostaje w centralnym OKF, koncepcja
`bosch-model-farm-harness-kodowanie`; tutaj opisujemy wyłącznie integrację AICO.

## Limity interpretacji

Timeouty HTTP nie ograniczają całej tury; transport MCP może potrzebować dodatkowego
czasu na zamknięcie po anulowaniu. Szacunek tokenów nie obejmuje wszystkich narzutów
modelu i schematów MCP. Tiktoken może pobierać słownik przy pierwszym użyciu;
przy pracy offline wymaga przygotowanego cache.

Ustawienia są opisem obecnego working tree. Wersje bibliotek nie są przypięte,
więc zachowanie proxy/CA wymaga odbioru na środowisku docelowym.

[^code]: Wartości i odgałęzienia konfiguracji w podanych plikach; bez sprawdzania zewnętrznych usług.
