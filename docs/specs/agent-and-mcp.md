---
type: Specification
title: Kontrakt agenta i MCP
description: Zachowanie aktywnego runnera wobec narzędzi, zgód, pauz i niejednoznacznych błędów.
tags: [aico, mcp, protocol]
status: draft
sources:
  - id: runner
    resource: 'Repozytorium aico: services/native_runner.py, services/agent_protocol.py, services/mcp_client.py oraz aico.py; working tree przeglądu 2026-10-15'
  - id: tests
    resource: 'Repozytorium aico: tests/test_native_agent.py oraz tests/test_network.py'
---

# Agent i MCP

Dokument opisuje obecny native runner. Nie nadaje dodatkowych uprawnień ani
nie zastępuje zasad projektu i zgód w serwerze MCP.[^runner]

## Protokół i wykonanie

- Model otrzymuje natywne definicje funkcji. Alias zależy od nazwy serwera, URL
  i nazwy narzędzia; zmiana tych danych może zerwać powiązanie oczekującego zadania.
- Walidacja całej partii obejmuje aliasy, identyfikatory wywołań oraz JSON
  argumentów. Nie zastępuje pełnej walidacji schematu po stronie serwera.
- Narzędzia wykonują się kolejno. Ich wyniki trafiają do wiadomości `role=tool`.
- Ucięta lub zablokowana odpowiedź API nie uruchamia zawartych w niej narzędzi.
  Sam reasoning nie jest odpowiedzią dla użytkownika.
- Czwarta identyczna operacja z rzędu jest zatrzymywana przed wykonaniem.
- Pełny wynik jest zachowany w historii; podgląd terminala ma limit 2000 znaków.
- Lista narzędzi pomija `secret_reveal`; pola `secret_result` są usuwane z wartości
  przekazywanych do historii przez ten mechanizm. Nie jest to ogólny filtr wszystkich
  sekretów występujących w dowolnym tekście.[^runner][^tests]

## Zgody i wznowienie

Odpowiedź zadania ze statusem `awaiting_approval`, `queued` lub `running` powoduje
pauzę, jeżeli zawiera poprawny całkowity task_id i dostępne jest get_task tego
samego serwera. Pozostałe wywołania partii otrzymują wynik „nie wykonano”.
Bez identyfikatora albo get_task agent zgłasza błąd i odsyła do panelu.[^runner]

`/continue` dla znanego zadania wykonuje pojedyncze get_task. Stan oczekujący
pozostawia pauzę; `done` pozwala kontynuować model; odrzucenie lub inny końcowy
stan błędu kończy obsługę bez ponownego utworzenia zadania. Nie ma automatycznej
pętli odpytywania panelu.[^runner][^tests]

Przy znanym oczekującym zadaniu nowe polecenia, zmiana modelu i rozłączenie MCP
są blokowane. `/mcp connect` może odświeżyć narzędzia bez wyczyszczenia task_id.
`/clear` wymaga wtedy potwierdzenia CLEAR; zapomina kontekst, ale nie anuluje zadania.

## Błąd i przerwanie

Klient MCP nie ponawia automatycznie narzędzia. Utrata odpowiedzi lub Ctrl+C
może oznaczać nieznany wynik już rozpoczętej operacji. Historia jest uzupełniana
wynikiem błędu dla wywołania i wynikami „nie wykonano” dla pozostałych pozycji.
Stan na serwerze trzeba ustalić przed kolejnym zapisem/skryptem.[^runner][^tests]

Po błędzie bez znanego task_id `/continue` wznawia model z informacją o nieznanym
wyniku. Nie jest to automatyczne odnalezienie zadania ani techniczna gwarancja,
że model nie zaproponuje operacji ponownie; zakaz ponawiania jest także instrukcją
systemową. Procedura: [odzyskiwanie połączenia](../procedures/connection-recovery.md).

Budżet kroków kończy uruchomienie pauzą, zachowując historię. Zwykła odpowiedź
bez tool_calls oddaje sterowanie użytkownikowi; nie dowodzi wykonania zadania.

[^runner]: Aktywna implementacja, nie starszy run_automatic.
[^tests]: Scenariusze offline; zakres wykonanego sprawdzenia w CURRENT.
