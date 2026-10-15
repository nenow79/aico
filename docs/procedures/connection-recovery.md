---
type: Troubleshooting Guide
title: Odzyskiwanie pracy po awarii połączenia
description: Diagnostyka LLM, proxy i MCP z uwzględnieniem nieznanego wyniku operacji.
tags: [aico, network, recovery]
status: draft
sources:
  - id: code
    resource: 'Repozytorium aico: services/network.py, services/native_runner.py, services/mcp_client.py i aico.py; working tree przeglądu 2026-10-15'
  - id: protocol
    resource: specs/agent-and-mcp.md
  - id: reader
    resource: 'Repozytorium aico: services/response_reader.py i /read w aico.py; zmiana robocza po bc95b3f'
---

# Awaria połączenia

## LLM i proxy

| Objaw | Działanie |
| --- | --- |
| HTTP 401/403 | Sprawdź klucz, uprawnienia modelu i reguły bramy; nie ujawniaj klucza w rozmowie |
| HTTP 407 / błąd proxy | Sprawdź uwierzytelnienie proxy i zmienne środowiska |
| Błąd TLS | Sprawdź firmowy CA i REQUESTS_CA_BUNDLE; nie wyłączaj weryfikacji certyfikatu |
| HTTP 400 | Sprawdź endpoint, model, obsługę tools i wielkość kontekstu |
| HTTP 429/502/503/504 | Poczekaj na ograniczone retry; po wyczerpaniu prób sprawdź usługę lub wróć później |
| Timeout / brak połączenia | Sprawdź VPN, sieć, adres i proxy; dostosuj limit tylko do uzasadnionej latencji |
| Niepoprawny JSON API | Sprawdź endpoint i odpowiedź bramy; próba nie jest automatycznie ponawiana |

LLM ponawia błędy połączenia i timeouty oraz powyższe przejściowe statusy HTTP.
Liczbowy Retry-After do 30 s jest respektowany, większy zatrzymuje próby.
Retry-After w formacie daty nie jest interpretowany — stosowany jest zwykły backoff.
Ctrl+C przerywa oczekiwanie między próbami. Powtórzona generacja może kosztować
dodatkowo, jeśli dostawca przyjął poprzednią prośbę. `LLM_RETRIES=0` wyłącza retry.
Nie ma przełączenia do innego dostawcy.[^code]

## MCP

1. Sprawdź, czy serwer działa pod skonfigurowanym adresem i czy localhost jest
   wyłączony z proxy. Dla HTTPS MCP sprawdź SSL_CERT_FILE.
2. Wykonaj `/mcp connect`; zachowaj nazwę i URL serwera z oczekującym zadaniem.
   To odświeża narzędzia, nie anuluje ani nie tworzy zadania.
3. Jeśli task_id jest znane, sprawdź panel i użyj `/continue`. Agent najpierw
   odczyta get_task. Gdy stan nadal oczekuje, wróci do pauzy.
4. Jeśli odpowiedź na zapis/skrypt zaginęła i task_id nie jest znane, sprawdź
   listę zadań, panel i rzeczywisty wynik operacji przed wznowieniem. Nie wysyłaj
   w ciemno tej samej operacji. Sam timeout klienta nie oznacza niewykonania.
5. Po odrzuceniu zadania nowe wykonanie wymaga nowego polecenia użytkownika.
   `/clear` tylko zapomina kontekst; `/exit` nie jest anulowaniem pracy serwera.[^protocol]

## Gdy program nadal długo czeka

Timeouty HTTP ograniczają nawiązywanie połączenia i przerwy w odczycie, nie całkowity
czas odpowiedzi. Discovery jest sekwencyjne, więc kilka niedostępnych serwerów
sumuje oczekiwanie. Tiktoken w trybie AICO_EXACT_TOKENS=1 może pobierać słownik.
Wyłącz nieużywane serwery, pozostaw domyślny licznik offline i użyj Ctrl+C,
pamiętając o możliwym wykonaniu operacji MCP.

Historia pozostaje w pamięci. Przed zamknięciem, jeśli terminal odpowiada, można
użyć `/export`; po ponownym uruchomieniu nie ma automatycznego odtworzenia sesji.

## Widok przeskakuje na dół podczas czytania

Po zakończeniu odpowiedzi wpisz `/read`. Otworzy ostatnią niepustą odpowiedź
asystenta od początku w osobnym widoku tekstu Markdown. Strzałki i Page Up/Down
przewijają, Home/End przenoszą na początek/koniec, Esc lub q wraca do rozmowy.
Ctrl+C również zamyka czytnik. Widok nie wznawia modelu ani oczekującego zadania.
Jest dostępny, gdy CLI przyjmuje komendy, również w pauzie MCP.[^reader]

Nie potwierdzono przyczyny pierwotnego zachowania konsoli Windows. Czytnik omija
przewijanie historii terminala; jego działanie w docelowym CMD wymaga odbioru.

[^code]: Zakres retry i ograniczenia aktualnej implementacji.
[^protocol]: Semantyka pauzy, wznowienia i niejednoznacznego wyniku narzędzia.
[^reader]: Lokalny czytnik odpowiedzi, niezależny od połączeń sieciowych.
