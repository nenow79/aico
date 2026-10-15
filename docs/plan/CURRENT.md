---
type: Project State
title: Bieżący stan aico
description: Stan lokalnej implementacji, zakres potwierdzenia i niewyjaśnione ograniczenia.
tags: [aico, state, verification]
status: draft
sources:
  - id: code
    resource: 'Repozytorium aico: aico.py, services/, tests/; baza bc95b3f wraz ze zmianami roboczymi /read i obsługi niepełnych wyników MCP'
  - id: session
    resource: 'Rozmowa projektowa z 2026-10-15: wymagania Windows/proxy/LiteLLM oraz wynik 34 testów offline przed migracją dokumentacji'
  - id: review
    resource: archive/migration-review.md
---

# Bieżący stan

## Punkt odniesienia

Przegląd: 2026-10-15. Poprawki odporności sieciowej i migrację dokumentacji zapisano
w commicie `bc95b3f`. Zmiany robocze dodają `/read` i obsługę niepełnych wyników MCP. Nie jest to dowód
wdrożenia na docelowym komputerze. Docelowo aico pracuje na Windows za firmowym proxy,
głównie z LiteLLM i MCP-sklr.[^code][^session]

## Implementacja

- CLI używa Rich i prompt_toolkit; MCP podłącza się poleceniem `/mcp connect`.
- Aktywny runner używa natywnych `tool_calls`, zachowuje historię protokołu,
  obsługuje pauzę, `/continue` i zadania wymagające zgody w panelu sklr.
- LiteLLM i OpenRouter są rozdzielone; brak automatycznego fallbacku dostawcy.
- Historia i stan oczekującego zadania pozostają w pamięci. Eksport Markdown
  nie zapewnia przywracania sesji.
- Implementacja obejmuje timeouty MCP, ograniczone retry LLM, obsługę proxy przez
  standardowe zmienne, odświeżanie MCP przy oczekującym zadaniu, przenośny launcher
  Windows i domyślny licznik tokenów bez pobierania słownika.
- Starszy tekstowy runner nadal istnieje, ale CLI go nie uruchamia.[^code]
- `/read` otwiera ostatnią niepustą odpowiedź asystenta w osobnym widoku tylko
  do odczytu, od początku. Obsługuje strzałki, Page Up/Down, Home/End i Esc/q.
  Pokazuje tekst Markdown, bez wywołań LLM/MCP i zmian historii. Dostępne również
  podczas pauzy na zgodę MCP. Przyczyna skakania scrolla w konsoli Windows nie
  została odtworzona; czytnik omija korzystanie ze scrollbacku terminala.[^code]
- Jawne flagi niepełności MCP wywołują ostrzeżenie w terminalu i historii modelu.
  Otrzymana treść pozostaje zachowana; instrukcja systemowa opisuje doczytywanie
  zakresami linii lub sekcjami. Nie ma automatycznego ponawiania operacji.
  Szczegóły: [kontrakt](../specs/agent-and-mcp.md).[^code]

Po migracji zapisano w korzeniu aico plik AGENTS.md z treścią osobno zaakceptowaną
przez użytkownika. Wskazuje docs jako bieżące źródło wiedzy i zachowuje pliki legacy
jako historię; nie zmienia polityki wymogu OKF.

## Zakres potwierdzenia

Przed migracją dokumentacji wykonano 34 testy unittest offline: wynik OK.
Użyto istniejącego interpretera `MCP-sklr/venv/bin/python` z dołączonym systemowym
`/usr/lib/python3/dist-packages` dla Requests; nie instalowano zależności.
Nie był to test czystej instalacji ani uruchomionego serwera MCP. Testy obejmowały
m.in. historię narzędzi, wznowienie znanego zadania, błędy transportu, ograniczone
retry, przerwanie backoffu i timeouty z atrapą klienta.[^session]

Migracja dokumentacji nie stanowi ponownego testu aplikacji. Zakres odbioru
dokumentów zapisuje [raport migracji](../archive/migration-review.md).

Po dodaniu `/read` ponownie uruchomiono cały zestaw: 37 testów offline, wynik OK.
Trzy nowe testy obejmują wybór ostatniej odpowiedzi bez mutacji historii, nawigację
Page Up/Down i Home/End, zachowanie tekstu tylko do odczytu, utrzymanie pozycji
podczas bezczynności oraz wyjście q/Esc. Interakcję symulowano przez wejście pipe
i DummyOutput na Linuksie. Do poprzedniego środowiska testowego dodano wyłącznie
w `/tmp` prompt_toolkit 3.0.52 i wcwidth 0.2.13. Nie jest to wizualny odbiór CMD
ani dowód usunięcia źródłowej przyczyny samoczynnego przewijania.[^code]

Po dodaniu obsługi niepełnych wyników ponownie wykonano cały zestaw w tym samym
środowisku: 41 testów offline, wynik OK. Nowe testy sprawdzają flagi zagnieżdżone,
brak rozpoznawania flag wewnątrz zwykłego tekstu, zachowanie pełnego payloadu,
przekazanie ostrzeżenia modelowi i terminalowi, poprawne przesłanie odczytu od
linii 200 oraz zachowanie pauzy na zgodę przy niepełnym wyniku zapisu.
Kolejny odczyt w teście wybiera atrapa modelu: nie jest to dowód, że rzeczywisty
LLM zawsze doczyta brakującą treść. MCP-sklr nie zmieniano.[^code]

## Ograniczenia i niepewności

- Brak potwierdzonego odbioru na docelowym Windows, firmowym TLS/proxy i LiteLLM.
- Dostępność modeli i czterech skonfigurowanych serwerów MCP nie została sprawdzona.
- Timeout HTTP nie ogranicza bezwzględnego czasu całej odpowiedzi; anulowanie
  klienta MCP nie dowodzi anulowania zadania na serwerze.
- Brak trwałego odtwarzania sesji, ścisłego budżetu czasu tury i automatycznego
  zarządzania rozmiarem historii. Pełne wyniki narzędzi mogą powiększać kontekst.
- Wersje zależności nie są przypięte; brak potwierdzonej macierzy zgodności.
- Nie ustalono, czy starszy runner ma użytkowników poza CLI.
- Nie potwierdzono rejestracji roota aico ani indeksowania docs w działającym sklr.
- Historyczne rozbieżności i zakres migracji opisuje raport.[^code][^review]

Otwarta praca i proponowana kolejność są wyłącznie w [backlogu](backlog.md).

[^code]: Przegląd lokalnych plików wskazanych w sources; bez utożsamiania working tree z wdrożeniem.
[^session]: Wynik wykonania testów i wymagania z wcześniejszego etapu tej rozmowy.
[^review]: Rozbieżności, zachowane oryginały i granice migracji.
