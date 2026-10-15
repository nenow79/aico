"""Recognize explicit MCP completeness metadata, without interpreting file text."""

READING_POLICY = """Kompletność wyników MCP:
Flagi truncated=true, partial=true, *_truncated=true lub instructions_complete=false
oznaczają niepełny wynik w danym zakresie. Nie przedstawiaj go jako pełnego odczytu.
Gdy brakujący fragment jest potrzebny do zadania, doczytaj go dostępnym narzędziem
w kolejnych tool_calls, zamiast pytać użytkownika o zgodę na zwykły dozwolony odczyt.
Nie musisz pobierać całego pliku, jeśli potrzebny fragment jest już kompletny.
read_file: używaj start_line/end_line (od 1, włącznie) i line_numbers=true.
Przy truncated=true end_line oznacza żądany zakres, nie ostatnią zwróconą linię:
nie kontynuuj od end_line+1. Ostatnia widoczna linia mogła być ucięta, odczytaj ją
ponownie. Bez numerów linii odczytaj mniejszy zakres z line_numbers=true.
Zmniejsz zakres lub zwiększ max_chars do limitu narzędzia; nie powtarzaj bez zmian.
W sklr limit max_chars wynosi 80000. Pojedyncza linia może przekroczyć ten limit;
wtedy jawnie zgłoś brak możliwości pełnego odczytu, nie wymyślaj offsetu.
read_files_batch: sprawdzaj osobno results; doczytuj potrzebne pliki przez read_file.
knowledge_get: pobierz outline, następnie view=section, section_id oraz
expected_revision. Używaj section_mode=direct/subtree według potrzeby i schematu.
Po REVISION_CONFLICT pobierz nowy outline. Nie dopisuj start_line do knowledge_get.
read_skill_resource: zwiększ max_chars, maksymalnie do 80000; to narzędzie sklr
nie ma zakresów linii ani offsetu. Jeśli nadal brakuje treści, zgłoś ograniczenie.
partial nie musi oznaczać ucięcia tekstu: sprawdź diagnostykę, zakres i budżet.
Ucięty wynik zapisu, skryptu lub zadania NIE uprawnia do ponownego wykonania operacji.
Najpierw sprawdź stan i użyj dostępnego odczytu. Zachowaj zasady zgód i pauz MCP.
Jeśli dostępne narzędzia nie pozwalają doczytać, wskaż dokładnie brak i ograniczenie.
"""


def is_incomplete(value) -> bool:
    pending = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, item in node.items():
                if ((key in {"truncated", "partial"} or key.endswith("_truncated"))
                        and item is True):
                    return True
                if key == "instructions_complete" and item is False:
                    return True
                if isinstance(item, (dict, list)):
                    pending.append(item)
        elif isinstance(node, list):
            pending.extend(node)
    return False


def completeness_notice(tool_name: str, value) -> str | None:
    if not is_incomplete(value):
        return None
    return (f"Niepełny wynik MCP ({tool_name}). Sprawdź flagi i diagnostykę. "
            "Doczytaj potrzebny fragment zgodnie z zasadami kompletności i schematem narzędzia; "
            "nie traktuj wyniku jako pełnego i nie ponawiaj operacji zmieniającej stan.")
