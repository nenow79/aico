---
type: Implementation Plan
title: Otwarte prace aico
description: Rozdzielenie zatwierdzonej migracji dokumentacji od propozycji dalszego rozwoju.
tags: [aico, planning]
status: draft
sources:
  - id: state
    resource: plan/CURRENT.md
  - id: approval
    resource: 'Rozmowa projektowa: akceptacja tabeli struktury i typów OKF, zachowania oryginałów i oddzielnego przedstawienia AGENTS.md'
---

# Backlog

## Zatwierdzony zakres dokumentacyjny

- Odebrać treść nowych dokumentów i lokalny raport walidacji.
- Oddzielnie sprawdzić widoczność docs i odczyt/wyszukiwanie w docelowym MCP,
  gdy środowisko będzie dostępne; bez zmiany polityki zapisu.[^approval]

## Propozycje techniczne — nie są zleceniem implementacji

Kolejność poniżej jest propozycją, nie zatwierdzonym harmonogramem.[^state]

| Priorytet | Praca | Kryterium odbioru |
| --- | --- | --- |
| 1 | Odbiór Windows/proxy/LiteLLM/MCP | Odczyt, zgoda, wznowienie, awaria i Ctrl+C sprawdzone na docelowym komputerze |
| 1 | Ustalenie wersji zależności | Odtwarzalna instalacja z potwierdzonym zestawem wersji |
| 2 | Trwały zapis i odtworzenie sesji | Historia i task_id przeżywają restart; brak ponownego wykonania niepewnej operacji |
| 2 | Ścisły limit czasu odpowiedzi LLM | Powrót sterowania także przy ciągłym napływie bajtów; zdefiniowane zasady anulowania |
| 2 | Zarządzanie dużym kontekstem | Jawny budżet i zachowanie poprawnej historii tool_calls; brak cichej utraty instrukcji |
| 3 | Ustalenie losu starszego runnera | Rozpoznani użytkownicy i świadoma decyzja: utrzymanie, oznaczenie albo usunięcie |
| 3 | Uporządkowanie drobnych rozbieżności opisów | Docstring token_counter odpowiada obecnemu trybowi domyślnemu |
| 3 | Wybór potrzebnych modeli i serwerów | Konfiguracja zgodna z rzeczywistą dostępnością i potrzebami |

Przeniesienie oryginałów legacy oraz ewentualne włączenie wymogu OKF pozostają
osobnymi decyzjami użytkownika. Nie są automatycznym etapem tej migracji.

[^state]: Ograniczenia i niepewności z bieżącego przeglądu.
[^approval]: Zakres zgody użytkownika w rozmowie.
