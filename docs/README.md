---
type: Link Collection
title: Dokumentacja aico
description: Mapa bieżącej wiedzy, procedur i źródeł historycznych projektu.
tags: [aico, documentation]
status: draft
sources:
  - id: migration
    resource: archive/migration-review.md
---

# Dokumentacja aico

Dokumentacja opisuje lokalny kod roboczy, nie potwierdzone wdrożenie na Windows.
Strukturę i typy zaakceptowano w rozmowie; treść dokumentów pozostaje do odbioru.
Nie włączono wymogu OKF ani nie zmieniono konfiguracji MCP.[^migration]

| Potrzeba | Dokument |
| --- | --- |
| Stan implementacji, wyniki sprawdzeń i niepewności | [CURRENT](plan/CURRENT.md) |
| Otwarte zadania i propozycje | [Backlog](plan/backlog.md) |
| Moduły i przepływ wykonania | [Architektura](architecture.md) |
| Narzędzia, zgody, historia i wznowienie | [Kontrakt agenta i MCP](specs/agent-and-mcp.md) |
| Ustawienia i wartości domyślne | [Konfiguracja](configuration.md) |
| Przygotowanie firmowego komputera | [Windows](procedures/windows-setup.md) |
| Awaria połączenia lub nieznany wynik operacji | [Odzyskiwanie połączenia](procedures/connection-recovery.md) |
| Pochodzenie informacji i sprzeczne checkpointy | [Raport migracji](archive/migration-review.md) |

## Jak czytać źródła

Kod opisuje zachowanie, instrukcje użytkownika określają wymagania, a testy mają
konkretny zakres. Rozbieżność między nimi wymaga wyjaśnienia. Nowsza data dokumentu
ani ostatni checkpoint nie są samodzielnym dowodem aktualności.

`sources.resource` wskazuje dokument wewnątrz tego zbioru albo jawny opis źródła
poza nim (np. plik kodu względem repozytorium). Opis nie jest ścieżką do otwarcia
przez knowledge_get. Oryginały `.vibecoder_context.md` i `.vibecoder_checkpoints.md`
pozostają w korzeniu repozytorium bez zmian i służą jako historia.

Archiwum nie jest listą bieżących zadań. W profilu projektowym sklr katalog
`archive/` jest wyłączony z indeksu; pozostaje dostępny jako pliki źródłowe.

[^migration]: Raport migracji, zakres źródeł i lokalne kontrakty OKF sklr.
