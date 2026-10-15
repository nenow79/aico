---
type: Reference
title: Raport migracji wiedzy aico do docs
description: Źródła, sprzeczności i granice przeniesienia wiedzy z plików vibecoder.
tags: [aico, migration, history]
status: draft
sources:
  - id: context
    resource: 'Repozytorium aico: .vibecoder_context.md, zachowany oryginał w korzeniu'
  - id: checkpoints
    resource: 'Repozytorium aico: .vibecoder_checkpoints.md, zachowany oryginał w korzeniu'
  - id: code
    resource: 'Repozytorium aico: baza Git 5f3d659 oraz zastany working tree z przeglądu 2026-10-15'
  - id: readme
    resource: 'Repozytorium aico: README.md, instrukcja przygotowana przed migracją; zachowana bez zmian'
  - id: okf
    resource: 'Repozytorium MCP-sklr: docs/specs/OKF/, docs/specs/okf-integration/curation.md, project-and-conversion.md oraz docs/migracja-projektu-legacy-do-okf.md'
  - id: user
    resource: 'Rozmowa projektowa: wymagania Windows/proxy/LiteLLM, przegląd migracyjny i akceptacja struktury dokumentacji'
---

# Raport migracji

## Zakres i zasady

Przegląd wykonano 2026-10-15. Zatwierdzona tabela zawiera dziewięć dokumentów i siedem
różnych typów; podana w rozmowie liczba ośmiu typów była pomyłką w zliczaniu.
Zachowano ścieżki i nazwy typów z tabeli. Nie zatwierdzano tym samym wdrożenia kodu, usuwania starszego runnera,
przenoszenia oryginałów ani wymogu OKF. Nowe treści mają status draft; zgoda na
strukturę nie jest zdarzeniem verified dla każdego twierdzenia.[^user][^okf]

Nie przypisano fikcyjnego autorstwa, dat generated/verified ani stref czasowych
historycznym checkpointom. Nie konwertowano oryginałów przez dopisanie YAML.
Nie znaleziono AGENTS.md w aico ani w sprawdzonych katalogach nadrzędnych.
AGENTS.md sąsiedniego MCP-sklr pozostaje zasadami tamtego projektu.

## Mapa źródeł

| Źródło | Wykorzystanie |
| --- | --- |
| .vibecoder_context.md | Dawny cel i założenia; potwierdzone elementy do architektury, rozbieżności poniżej |
| Checkpointy lipcowe | Historia budowy modułów i przejścia na ręczne łączenie MCP |
| Checkpoint sierpniowy | Historia tekstowego runnera; nie jest aktualnym opisem CLI |
| aico.py, native_runner.py, agent_protocol.py | Aktywny przepływ, protokół, pauzy i zgody |
| network.py i klienci dostawców/MCP | Konfiguracja i diagnostyka połączeń |
| token_counter.py, chat_exporter.py, aico.bat | Licznik, eksport i start na Windows |
| tests/ i wynik wcześniejszego uruchomienia | Zakres potwierdzenia w CURRENT, bez deklaracji odbioru produkcyjnego |
| README.md i .env.example | Materiał do konfiguracji i procedur; zachowany w oryginale |
| Lokalne kontrakty sklr OKF | Format, kuracja, oddzielenie archiwum i ograniczenia indeksowania |

## Rozstrzygnięte rozbieżności

| Dawne twierdzenie | Ustalenie z kodu podczas migracji |
| --- | --- |
| prompt_toolkit lub rich, TBD | Używane są obie biblioteki |
| JSON/YAML | Konfiguracja korzysta z JSON i .env |
| Pełna automatyzacja bez zgód | Native runner zatrzymuje się na oczekującym zadaniu; zgody wydaje użytkownik w panelu |
| MCP ładowane przy starcie | Obecnie jawne /mcp connect; odnotowane już w późniejszym lipcowym checkpointcie |
| Tekstowe JSON tool calls i retry urwanego JSON | Historyczny run_automatic istnieje; CLI uruchamia run_native |
| Skracanie wyników w kontekście modelu | Native runner zachowuje pełne wyniki, skraca tylko podgląd terminala |
| Domyślnie 15 iteracji | Obecnie 40 kroków, /steps i wznawialna pauza |
| Licznik oparty na tiktoken | W zmianach roboczych domyślny szacunek offline; docstring pozostaje nieaktualny |
| Venv i paczki zainstalowane | Świadectwo dawnego środowiska, nie potwierdzenie obecnej instalacji |

Powyższe nie zmienia treści historycznych źródeł.[^context][^checkpoints][^code]

## Chronologia zachowana w źródłach

- 2026-07-24 09:48: zapis setupu i planu etapów.
- 2026-07-24 09:52: przeniesienie services z harnessu referencyjnego.
- 2026-07-24 09:53: tekstowy runner MCP i callbacki.
- 2026-07-24 09:55: CLI, konfiguracja i deklarowany smoke test importów.
- 2026-07-24 10:56: obsługa /mcp connect i disconnect.
- 2026-08-26 09:23: naprawianie urwanych JSON, skracanie kontekstu i max_tokens;
  źródło deklaruje sprawdzenie składni, bez testów.

To daty zapisane w źródle, bez znanej strefy czasowej. Nie potwierdzają dat wdrożenia.
Historyczna ścieżka OpenRouterChat i alias harness nie były sprawdzane.[^checkpoints]

## Baza robocza i zachowanie oryginałów

HEAD podczas migracji: `5f3d659` (wcześniejszy commit: `dc7e66d`). Zastane zmiany:
`.env.example`, `aico.bat`, `aico.py`, `services/agent_protocol.py`,
`services/litellm_client.py`, `services/mcp_client.py`, `services/mcp_runner.py`,
`services/native_runner.py`, `services/openrouter_client.py`,
`services/token_counter.py`; nowe, jeszcze nieśledzone: `README.md`,
`services/network.py`, `tests/test_network.py`.

Migracja dodaje wyłącznie docs. Oba pliki legacy i dotychczasowy README pozostają
w korzeniu bez zmian. Ten raport zastępuje kopiowanie źródeł do archiwum; nie jest
ich pełnym zamiennikiem. Przed zapisem wykonano lokalny snapshot SHA-256 wszystkich
24 zastanych plików poza .git i cache; porównanie po zapisie służy wykryciu zmian.

## Odbiór dokumentacji

Lokalna walidacja po zapisie: dziewięć dokumentów przeszło parser
`okf_engine.parser.parse_document` z MCP-sklr bez błędów i ostrzeżeń. Sprawdzono
uzgodnione typy, status draft, brak dopisanego generated/verified, UTF-8 bez BOM
i końce linii LF. Piętnaście odnośników w treści prowadzi do istniejących plików
wewnątrz docs; przypisy mają definicje i odpowiadające wpisy sources.
Porównanie SHA-256 potwierdziło identyczność wszystkich 24 zastanych plików,
w tym obu oryginałów legacy i dotychczasowego README. Nie uruchamiano ponownie
testów aplikacji; zmieniony zakres obejmuje wyłącznie dokumentację.

Odbiór działającego indeksu MCP pozostaje oddzielny: nie uruchamiano serwera,
nie rejestrowano zbiorów i nie zmieniano polityki zapisu. Profil projektowy sklr
wyłącza archive z indeksu, ale nie usuwa plików i może uwzględniać je w audycie.[^okf]

Niepewności istotne dla bieżącej pracy są w [CURRENT](../plan/CURRENT.md).
Otwarte zadania są wyłącznie w [backlogu](../plan/backlog.md).

[^context]: Oryginalny opis aico, odczytany bez zmian.
[^checkpoints]: Wszystkie wpisy obu faz historycznych, nie tylko ostatni checkpoint.
[^code]: Bezpośredni przegląd aktywnej ścieżki i stanu Git.
[^readme]: Zachowana instrukcja z etapu poprawiania odporności połączeń.
[^okf]: Lokalny standard OKF 0.2 i kontrakty integracji sklr.
[^user]: Zakres zaakceptowany w rozmowie; bez przypisywania nieudzielonych zgód.
