# aico: Windows, LiteLLM i MCP-sklr

Wymagany Python 3.11+ (limity MCP używają `asyncio.timeout`). Uruchamiaj w środowisku
z zależnościami z `requirements.txt`. `aico.bat` działa względem własnego katalogu;
wybiera `venv\Scripts\python.exe`, a gdy go brak — `python` z PATH, np. z aktywnej condy.

Skopiuj `.env.example` do `.env`, ustaw klucz LiteLLM i firmowe proxy. Wybierz model
z prefiksem `litellm:`. Awaria LiteLLM nie przełącza rozmowy do OpenRouter.

## Proxy i certyfikaty

Ustaw `NO_PROXY=localhost,127.0.0.1,::1`, żeby lokalny MCP nie szedł przez firmowe
proxy. Jeśli masz już wyjątki, dopisz te adresy do istniejącej listy. Uwzględnij
również `no_proxy` odziedziczone ze środowiska: ustawienia małymi i wielkimi literami
powinny być spójne. Zmienne środowiska mają pierwszeństwo przed `.env`.

Dla firmowego CA użyj pliku PEM: `REQUESTS_CA_BUNDLE` dla LLM (Requests),
`SSL_CERT_FILE` dla HTTPS MCP (HTTPX). Nie wyłączaj weryfikacji TLS.
LiteLLM respektuje standardowe zmienne proxy, w tym `NO_PROXY`.

## Limity i odzyskiwanie pracy

| Zmienna | Domyślnie | Znaczenie |
| --- | ---: | --- |
| `LLM_CONNECT_TIMEOUT` | 10 s | Nawiązanie połączenia HTTP |
| `LLM_READ_TIMEOUT` | 120 s | Maksymalna przerwa podczas odczytu HTTP |
| `LLM_RETRIES` | 2 | Dodatkowe próby tej samej prośby do LLM |
| `MCP_INIT_TIMEOUT` | 10 s | Inicjalizacja sesji MCP |
| `MCP_DISCOVERY_TIMEOUT` | 15 s | Limit operacji pobierania listy narzędzi |
| `MCP_CALL_TIMEOUT` | 60 s | Limit operacji narzędzia MCP |

LLM ponawia błędy połączenia, timeouty oraz HTTP 429/502/503/504 z krótkim backoffem
i losowym przesunięciem. Błędy TLS, uwierzytelnienia, parametrów i niepoprawny JSON
kończą próbę. Komunikaty nie zawierają treści odpowiedzi API, kluczy ani adresów
proxy z hasłami. Liczbowy `Retry-After` do 30 s jest respektowany; dłuższy zatrzymuje
próby i prosi o powrót później. Powtórzona generacja może zwiększyć koszt dostawcy,
jeśli poprzednia już trwała. Ustaw `LLM_RETRIES=0`, żeby wyłączyć powtórki.

**To nie jest gwarantowany czas całej tury.** Limity Requests dotyczą połączenia
i przerw w odczycie, a nie całej odpowiedzi (np. serwer może stale przesyłać bajty).
DNS/system operacyjny także mogą opóźnić powrót. Limit MCP anuluje operację
asynchroniczną; zamykanie transportu może wydłużyć powrót. Ctrl+C przerywa agenta,
ale nie gwarantuje anulowania pracy już przyjętej przez serwer.

Narzędzia MCP nie są automatycznie ponawiane. Po utracie odpowiedzi zapis/skrypt
mógł zostać wykonany: najpierw sprawdź panel, listę zadań i wynik operacji.
`/continue` po błędzie transportu wznawia model z informacją o nieznanym wyniku;
używaj go dopiero po ocenie stanu. Dla znanego oczekującego zadania `/continue`
najpierw wykonuje `get_task`, nie tworzy nowego zadania.
`/mcp connect` odświeża narzędzia również podczas oczekiwania na zadanie;
zachowaj nazwę i URL serwera, aby można było odnaleźć wcześniejsze powiązanie.

W `config/mcp_servers.json` ustaw `"enabled": false` przy nieużywanych serwerach.
Discovery jest sekwencyjne: niedostępny serwer może dodać około 15 s oczekiwania.
Dla samego MCP-sklr potrzebny jest wpis z portem 8101, np.
`{"name":"sklr","url":"http://localhost:8101/mcp"}`.

Licznik tokenów domyślnie szacuje rozmiar lokalnie, bez pobierania słownika przez
sieć. `AICO_EXACT_TOKENS=1` włącza tiktoken; przygotuj jego cache przed pracą za
proxy. Nawet tiktoken jest tu szacunkiem: nie obejmuje schematów MCP ani wszystkich
różnic między modelami. Historia pozostaje w pamięci; `/export` zapisuje Markdown,
ale nie jest mechanizmem odtwarzania sesji po zamknięciu procesu.

## Sprawdzenie przed wdrożeniem

Testy offline aico: `python -m unittest discover -s tests -v`.
Na docelowym Windows sprawdź `/mcp connect`, odczyt pliku, pojedyncze zadanie
wymagające zgody, `/continue` po zgodzie oraz odłączenie VPN/proxy i Ctrl+C.
Sprawdź ponowne `/mcp connect` podczas oczekiwania na zgodę.
Testy lokalne nie zastępują testu firmowego TLS/proxy i zachowania Ctrl+C w terminalu Windows.

Dalsze usprawnienia: trwały zapis i odtwarzanie historii wraz z identyfikatorem
zadania, ścisły limit całej odpowiedzi LLM (transport asynchroniczny lub izolacja
procesu) oraz świadome zarządzanie kontekstem przy dużych wynikach narzędzi.
Obecne poprawki nie wymagają zmian w MCP-sklr.

Podstawa zachowania HTTP: [Requests: proxy i timeouty](https://requests.readthedocs.io/en/stable/user/advanced/).
