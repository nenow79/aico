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
  - id: completeness
    resource: 'Repozytorium aico: services/mcp_completeness.py, integracja native_runner.py i tests/test_mcp_completeness.py; zmiana robocza po bc95b3f'
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

## Kompletność wyników

Aktywny runner nie obcina treści otrzymanej z MCP. Rozpoznaje jawne boolean
`truncated=true`, `partial=true`, `*_truncated=true` i `instructions_complete=false`
w obiektach i listach, także zagnieżdżonych. Nie parsuje tych flag z tekstu pliku.
Brak flagi nie stanowi dowodu kompletności; serwer może nie zgłaszać skrócenia.[^completeness]

Niepełny wynik trafia do wiadomości tool jako JSON z polami `mcp_result` (pełna
otrzymana wartość po dotychczasowym maskowaniu) oraz `aico_notice` (ostrzeżenie).
Wynik bez flag nie zmienia formatu. Ostrzeżenie jest też drukowane poza skróconym
podglądem terminala. Dotyczy to również odczytu get_task przy wznowieniu.
Obsługa zadania nadal odczytuje oryginalne pola status/task_id.[^completeness]

Instrukcja systemowa nakazuje doczytać potrzebny fragment w kolejnych tool_calls,
bez pytania o dodatkową zgodę na dozwolony odczyt. Nie wymaga zbędnego pobierania
całego pliku. To wskazówka dla modelu, nie automatyczny paginator ani gwarancja
przestrzegania instrukcji przez każdy model.

- `read_file`: zakresy od 1, oba końce włącznie; `line_numbers=true`. Przy ucięciu
  end_line nie oznacza ostatniej dostarczonej linii. Ponowny odczyt ostatniej widocznej
  linii zabezpiecza przed pominięciem jej uciętej części. Bez numerów linii trzeba
  odczytać mniejszy zakres z numeracją. Nie należy zgadywać startu z end_line+1.
- `read_files_batch`: doczytywać potrzebne pliki osobno; sprawdzać flagi każdego wyniku.
- `knowledge_get`: outline, następnie section_id i expected_revision; po konflikcie
  rewizji nowy outline. Nie ma parametru start_line.
- `read_skill_resource`: można zwiększyć max_chars do 80000, ale nie ma offsetu
  ani zakresów linii. Gdy to nie wystarcza, trzeba jawnie zgłosić ograniczenie.
- `partial`: sprawdzić diagnostykę; może oznaczać częściowy indeks lub wyszukiwanie.
- Ucięty wynik zapisu/skryptu nie uprawnia do powtórzenia operacji. Pozostają
  obowiązujące pauzy, zgody i sprawdzanie stanu.[^completeness]

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
[^completeness]: Detekcja metadanych, zachowanie wyniku i instrukcja doczytywania.
