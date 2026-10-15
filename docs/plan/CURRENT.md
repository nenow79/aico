---
type: Project State
title: Bieżący stan aico
description: Stan lokalnej implementacji, zakres potwierdzenia i niewyjaśnione ograniczenia.
tags: [aico, state, verification]
status: draft
sources:
  - id: code
    resource: 'Repozytorium aico: aico.py, services/, tests/; baza 5f3d659 wraz ze zmianami roboczymi zastanymi przy migracji'
  - id: session
    resource: 'Rozmowa projektowa z 2026-10-15: wymagania Windows/proxy/LiteLLM oraz wynik 34 testów offline przed migracją dokumentacji'
  - id: review
    resource: archive/migration-review.md
---

# Bieżący stan

## Punkt odniesienia

Przegląd: 2026-10-15. Baza Git: `5f3d659`. Kod zawiera niecommitowane poprawki
odporności sieciowej, opisane w raporcie migracji. To stan working tree, nie numer
wydania ani dowód wdrożenia. Docelowo aico pracuje na Windows za firmowym proxy,
głównie z LiteLLM i MCP-sklr.[^code][^session]

## Implementacja

- CLI używa Rich i prompt_toolkit; MCP podłącza się poleceniem `/mcp connect`.
- Aktywny runner używa natywnych `tool_calls`, zachowuje historię protokołu,
  obsługuje pauzę, `/continue` i zadania wymagające zgody w panelu sklr.
- LiteLLM i OpenRouter są rozdzielone; brak automatycznego fallbacku dostawcy.
- Historia i stan oczekującego zadania pozostają w pamięci. Eksport Markdown
  nie zapewnia przywracania sesji.
- Zmiany robocze dodają timeouty MCP, ograniczone retry LLM, obsługę proxy przez
  standardowe zmienne, odświeżanie MCP przy oczekującym zadaniu, przenośny launcher
  Windows i domyślny licznik tokenów bez pobierania słownika.
- Starszy tekstowy runner nadal istnieje, ale CLI go nie uruchamia.[^code]

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
