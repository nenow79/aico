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
- OpenRouter, Bosch LiteLLM i Bosch Model Farm są rozdzielone; brak fallbacku.
  Provider wybierany jest przed modelem i pozostaje stały przez cały proces.
  `/model` ogranicza wybór do tego providera; `/clear` nie znosi ograniczenia.
- Adapter BMF obsługuje OpenAI przez Azure OpenAI oraz Gemini przez Vertex
  OpenAI-compatible. Dodano GPT-5.4 mini i Gemini 3.1 Flash-Lite jako wpisy
  konfiguracji, nie jako potwierdzone dostępne modele subskrypcji.
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

## Poprawka po porównaniu z aidev

Na bazie `200925c` przygotowano poprawkę roboczą transportu LiteLLM: przywrócenie
jawnego `get_proxies()` oraz domyślnego timeoutu połączenia 120 s. Jawna zmienna
`LLM_CONNECT_TIMEOUT` nadal ma pierwszeństwo. Retry i weryfikację TLS zachowano;
transport OpenRouter/MCP i launcher pozostają bez zmian.
Pierwszeństwo jawnego proxy względem `NO_PROXY` opisuje [konfiguracja](../configuration.md).

Dodano testy wyboru proxy przez rzeczywiste scalanie ustawień Requests z atrapą
końcowego `Session.send` (bez połączeń sieciowych), zachowania CA, domyślnych
timeoutów i kopiowania proxy między retry. Testy wykonano później w Windows
w ramach zestawu 56 testów opisanego poniżej; po korekcie oczekiwania dotyczącego
wielkości liter nazw zmiennych wszystkie przeszły. Działanie aidev jest informacją użytkownika; przyczyna awarii aico
i naprawa połączenia na docelowym Windows/LiteLLM wymagają potwierdzenia.

## Dodanie BMF i audyt dokumentacji

Zapisano adapter BMF, ProviderSession, routing i integrację CLI oraz testy
`tests/test_providers.py`. Wykonano cały zestaw offline w Windows, interpreterem
`venv/Scripts/python.exe`, Python 3.14.7: 56 testów, 54 zaliczone, 1 błąd i 1 failure.
Wszystkie 11 nowych testów BMF/providerów przeszło. Wykryto brak podłączenia
modułu kompletności do runnera, referencję do zmiennej historii w teście oraz
nieprzenośne oczekiwanie proxy (Windows nie rozróżnia wielkości liter nazw zmiennych).
Po zapisaniu poprawek ponownie wykonano cały zestaw tym samym interpreterem:
56/56 testów zaliczonych, bez błędów i pominięć (zadanie sklr 2146, unittest).
To testy offline z atrapami transportu, nie potwierdzenie działania BMF ani MCP w sieci.
Nie wykonywano wywołań BMF ani nie odczytywano kluczy użytkownika.
Endpointy i identyfikatory pochodzą z Docupedii, Model Endpoint Reference V61,
sekcje #1 i #3. Weryfikacja rzeczywistego tool calling, limitów, proxy i dostępu
subskrypcji pozostaje do wykonania. Native runner ponownie podłączono do istniejącego
modułu kompletności; zachowano odczyt stanu zadania z oryginalnego wyniku i pauzy.
Transportu LiteLLM i MCP-sklr nie zmieniano.

Audyt sklr obejmujący archiwum rozpoznał 9 dokumentów OKF bez błędów i ostrzeżeń.
Dwa źródła `.vibecoder_*` pozostają historycznym Markdown bez konwersji.
Root aico i projektowy indeks docs są dostępne w obecnej sesji sklr (8 dokumentów
poza archiwum). Potwierdzono odczyt plików i dostęp do zbioru; nie jest to test
połączenia z poziomu uruchomionej aplikacji AICO ani odbiór docelowej instalacji.

## Rozszerzenie listy modeli BMF

Dodano GPT-6 Sol/Luna, Gemini 3.7 Flash, Gemini 4 Argon, Claude Sonnet 4.6/5.5,
Qwen 3.8 27B i GLM-5.2. Łącznie konfiguracja zawiera 10 modeli BMF.
Claude korzysta z natywnego Vertex rawPredict i konwersji historii/tools przez
`services/anthropic_protocol.py`; Qwen/GLM z Bosch MSP OpenAI-compatible.
Identyfikatory pochodzą z Model Endpoint Reference V61; wzorzec rawPredict
z Code Examples V62. Extended thinking i streaming nie są włączone.

Wykonano pełny zestaw unittest przez `venv/Scripts/python.exe`, Python 3.14.7
na Windows: 63/63 testy zaliczone, bez błędów i pominięć (zadanie sklr 2175).
Siedem nowych testów obejmuje routing MSP, konfigurację modeli, konwersję historii,
schemat tools Claude, odrzucanie nieobsługiwanych odpowiedzi, ucięcie oraz
cykl tool_use/tool_result w runnerze. To testy offline, nie odbiór sieciowy.
Użytkownik potwierdził działanie wcześniejszej integracji BMF bez wskazania modelu
i scenariusza; nie rozszerzamy tego potwierdzenia na wszystkie nowe modele.
Nie wykonywano płatnych wywołań nowych modeli ani nie odczytywano kluczy.

## Ręczna kompakcja kontekstu i wyróżnienie promptów

Dodano roboczą komendę `/compact` i `services/context_compactor.py`.
Aktualny model otrzymuje transkrypcję do streszczenia bez udostępnionych tools.
Nie ma automatycznego eksportu; pełną rozmowę użytkownik może zachować przez
`/export` przed kompakcją. Podmiana jest warunkowa: kompletna odpowiedź bez tools
i mniejszy szacunek kontekstu. Oryginalne wiadomości systemowe oraz ostatnia
pełna tura pozostają; przy pojedynczej turze zostaje samo podsumowanie.
Podsumowanie nie rozszerza zgód. Pauza agenta, oczekujące zadanie lub pending
blokują komendę. Błąd i przerwanie zachowują oryginalną historię.
Opis użytkowy: [README](../../README.md#ręczne-skracanie-kontekstu).

Prompty CLI mają jasnoturkusowy tekst i pogrubione `TY ›`, przy szarych
metadanych. Wygląd MCP i odpowiedzi pozostaje bez zmian. Po zmianie promptów
wykonano 63/63 testy unittest offline na Windows, Python 3.14.7 (zadanie 2382).
Nie jest to wizualny odbiór terminala. Dodano testy kompakcji z atrapą LLM;
wynik ich uruchomienia i rzeczywista jakość streszczeń wymagają potwierdzenia.

## Ograniczenia i niepewności

- Brak potwierdzonego odbioru na docelowym Windows, firmowym TLS/proxy i LiteLLM.
- Dostępność modeli i czterech skonfigurowanych serwerów MCP nie została sprawdzona.
- Timeout HTTP nie ogranicza bezwzględnego czasu całej odpowiedzi; anulowanie
  klienta MCP nie dowodzi anulowania zadania na serwerze.
- Brak trwałego odtwarzania sesji, ścisłego budżetu czasu tury i automatycznego
  zarządzania rozmiarem historii. Ręczne `/compact` jest stratne i wymaga miejsca
  na transkrypcję oraz odpowiedź. Pełne wyniki narzędzi mogą powiększać kontekst.
- Wersje zależności nie są przypięte; brak potwierdzonej macierzy zgodności.
- Nie ustalono, czy starszy runner ma użytkowników poza CLI.
- Odczyt docs i indeks sklr są dostępne w obecnej sesji; połączenie i wyszukiwanie
  wykonywane przez aplikację AICO nadal wymagają odbioru.
- Historyczne rozbieżności i zakres migracji opisuje raport.[^code][^review]

Otwarta praca i proponowana kolejność są wyłącznie w [backlogu](backlog.md).

[^code]: Przegląd lokalnych plików wskazanych w sources; bez utożsamiania working tree z wdrożeniem.
[^session]: Wynik wykonania testów i wymagania z wcześniejszego etapu tej rozmowy.
[^review]: Rozbieżności, zachowane oryginały i granice migracji.
