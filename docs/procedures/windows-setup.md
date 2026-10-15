---
type: Procedure
title: Przygotowanie aico na Windows
description: Procedura uruchomienia i odbioru z firmowym LiteLLM, proxy oraz MCP-sklr.
tags: [aico, windows, deployment]
status: draft
sources:
  - id: configuration
    resource: configuration.md
  - id: launcher
    resource: 'Repozytorium aico: aico.bat, requirements.txt i README.md; working tree przeglądu 2026-10-15'
---

# Windows — przygotowanie i odbiór

Procedura do wykonania na docelowym komputerze. Nie stanowi zapisu zakończonego
wdrożenia.[^launcher]

1. Przygotuj środowisko Python 3.11+ z zależnościami z requirements.txt zgodnie
   z firmowymi zasadami instalacji. Nie przenoś linuksowego venv na Windows.
2. Sprawdź `python --version` oraz interpreter aktywnego środowiska. Launcher
   preferuje `venv\Scripts\python.exe`; jeżeli go brak, używa `python` z PATH,
   np. aktywnej condy. Ustawia UTF-8 i przechodzi do własnego katalogu.
3. Przygotuj `.env` z `.env.example`, kluczem LiteLLM i właściwym endpointem.
   Dopasuj proxy i CA, zachowując lokalne wyjątki NO_PROXY. Sprawdź zmienne
   odziedziczone z systemu — mają pierwszeństwo przed `.env`.[^configuration]
4. W models.json wybierz identyfikator dostępny w firmowym LiteLLM z prefiksem
   `litellm:`. Potwierdź obsługę natywnych tools przez wybrany model.
5. W mcp_servers.json wskaż właściwy adres sklr (obecny przykład: port 8101).
   Wyłącz nieużywane serwery przez `enabled: false`.
6. Uruchom `aico.bat` lub `python aico.py` w przygotowanym środowisku.
   Wybierz model, sprawdź zwykłą rozmowę, następnie `/mcp connect` i `/mcp`.
7. Sprawdź odczyt testowego pliku w zatwierdzonym roocie, a potem pojedynczą
   uzgodnioną edycję wymagającą zgody. Po decyzji w panelu użyj `/continue`;
   sprawdź rzeczywisty wynik i brak duplikatu zadania.
8. Sprawdź `/mcp connect` przy oczekującym zadaniu, odrzucenie zadania, przerwę
   sieciową oraz Ctrl+C. Do prób użyj danych testowych i procedury odzyskiwania.
9. Sprawdź `/export` oraz polskie znaki. Eksport nie służy do wznowienia procesu.

Testy offline aico, uruchamiane z katalogu projektu:

```text
python -m unittest discover -s tests -v
```

Zapisz interpreter i wersje bibliotek, model, scenariusze oraz wyniki bez kluczy
i danych proxy z hasłem. Rezultat odbioru powinien aktualizować zakres potwierdzenia
w [CURRENT](../plan/CURRENT.md); historyczny raport może trafić do archiwum.

[^configuration]: Ustawienia i wartości domyślne projektu.
[^launcher]: Wymaganie asyncio.timeout, sposób startu i istniejąca instrukcja wdrożenia.
