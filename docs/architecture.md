---
type: Reference
title: Architektura aico
description: Aktywny przepływ terminala, dostawców LLM i narzędzi MCP oraz rola starszego runnera.
tags: [aico, architecture, mcp]
status: draft
sources:
  - id: code
    resource: 'Repozytorium aico: aico.py i services/*.py; 5f3d659 plus zmiany robocze z przeglądu 2026-10-15'
  - id: legacy
    resource: 'Repozytorium aico: .vibecoder_context.md oraz .vibecoder_checkpoints.md, niezmienione źródła historyczne'
  - id: reader
    resource: 'Repozytorium aico: services/response_reader.py oraz obsługa /read w aico.py; zmiana robocza po bc95b3f'
---

# Architektura

## Aktywny przepływ

Terminal → router dostawcy → LiteLLM/OpenRouter → natywne tool_calls → klient MCP
→ serwer MCP → wynik w historii → kolejna odpowiedź modelu.[^code]

| Element | Odpowiedzialność |
| --- | --- |
| aico.py | Wybór modelu, REPL, komendy, renderowanie, historia i AgentState |
| services/llm_client.py | Wybór dostawcy po identyfikatorze modelu |
| services/litellm_client.py, openrouter_client.py | Payload i autoryzacja właściwego API |
| services/network.py | Timeouty HTTP, ograniczone retry i komunikaty błędów |
| services/agent_protocol.py | Walidacja odpowiedzi, aliasy narzędzi, JSON argumentów i wyników |
| services/native_runner.py | Aktywna pętla agenta, budżet kroków, pauzy i stan zadania |
| services/mcp_client.py | Sesja FastMCP na operację, timeout i normalizacja odpowiedzi |
| services/mcp_runner.py | Wczytanie konfiguracji/list narzędzi oraz starsza pętla tekstowa |
| services/token_counter.py | Lokalny szacunek lub opcjonalny tiktoken |
| services/chat_exporter.py | Eksport historii; CLI korzysta z Markdown |
| services/response_reader.py | Osobny pełnoekranowy czytnik ostatniej odpowiedzi, tylko do odczytu |
| services/mcp_completeness.py | Rozpoznawanie flag niepełności i instrukcja doczytywania; szczegóły w kontrakcie agenta |

`/read` otwiera lokalny widok prompt_toolkit od początku tekstu. Widok korzysta
z własnej nawigacji i nie dopisuje wiadomości do rozmowy. Treść Markdown jest
wyświetlana jako tekst; wyniki narzędzi i puste wiadomości asystenta są pomijane
przy wyborze ostatniej odpowiedzi.[^reader]

Brak aktywnych serwerów oznacza zwykłą rozmowę bez narzędzi. Konfigurację MCP
wczytuje się jawnie przez `/mcp connect`. Listowanie serwerów jest sekwencyjne.
Klient tworzy sesję na każdą operację; CLI nie utrzymuje stałego połączenia.[^code]

## Stan i granice

Historia rozmowy, historia promptów i AgentState są w pamięci procesu. AgentState
przechowuje m.in. powód pauzy, model, oczekujące zadanie i ochronę przed identyczną
pętlą narzędzia. Eksport nie jest checkpointem do automatycznego odtworzenia.
Moduł eksportu ma także funkcję JSON, ale CLI `/export` zapisuje Markdown.[^code]

Zgody i wykonanie zadań należą do MCP. Aico przechowuje otrzymany identyfikator
i odczytuje stan; nie zatwierdza operacji w imieniu użytkownika. Szczegóły:
[kontrakt agenta](specs/agent-and-mcp.md).

## Starsza implementacja

`run_automatic` parsuje propozycje JSON z tekstu modelu i zawiera historyczne
mechanizmy naprawiania urwanych wywołań oraz ograniczania kontekstu wyników.
Aktualne `send_message_mcp` wywołuje `run_native`. Obecność starszej funkcji nie
czyni jej aktualnym kontraktem CLI; nie ustalono jej użycia poza CLI.[^code][^legacy]

Ten dokument opisuje implementację. Nie odtwarza nieudokumentowanych motywacji
ani dat decyzji architektonicznych.

[^code]: Wskazane moduły lokalnego working tree.
[^legacy]: Checkpointy opisują wcześniejszą fazę projektu.
[^reader]: Implementacja czytnika i integracja z komendami CLI.
