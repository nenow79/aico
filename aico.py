"""
aico – terminal LLM chat harness
rich + prompt_toolkit, MCP automatic, OpenRouter + LiteLLM
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from services.chat_exporter import (
    build_export_filename,
    export_chat_to_markdown,
)
from services.llm_client import (
    ask_llm,
    get_missing_api_key_message,
    get_provider_label,
    get_model_provider,
    has_llm_api_key,
)
from services.mcp_runner import load_all_tools, load_mcp_servers
from services.native_runner import AgentState, run_native
from services.network import NetworkError
from services.provider_session import ProviderSession
from services.llm_client import PROVIDER_LABELS
from services.agent_protocol import ProtocolError
from services.response_reader import last_assistant_response, read_response
from services.context_compactor import compact_history
from services.task_poller import poll_task, PENDING_STATES
from services.token_counter import (
    count_chat_tokens,
    format_token_count,
    get_token_warning,
)

load_dotenv(Path(__file__).resolve().parent / ".env")

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
MODELS_PATH = BASE_DIR / "config/models.json"
MCP_SERVERS_PATH = BASE_DIR / "config/mcp_servers.json"
EXPORTS_DIR = BASE_DIR / "exports"
MAX_ITERATIONS_DEFAULT = 40

console = Console()


# ---------------------------------------------------------------------------
# Ładowanie konfiguracji
# ---------------------------------------------------------------------------

def load_models() -> dict[str, str]:
    if not MODELS_PATH.exists():
        console.print(f"[red]Brak pliku {MODELS_PATH}[/red]")
        sys.exit(1)

    with MODELS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or not data:
        console.print("[red]Plik models.json jest pusty lub niepoprawny.[/red]")
        sys.exit(1)

    try:
        for label, model in data.items():
            if not isinstance(label, str) or not label.strip():
                raise ProtocolError("Niepoprawna etykieta modelu.")
            get_model_provider(model)
    except ProtocolError as error:
        console.print(str(error), markup=False)
        sys.exit(1)
    return data


def pick_provider(models: dict[str, str]) -> ProviderSession:
    console.print(Panel.fit("[bold cyan]aico[/bold cyan] – wybierz providera sesji", border_style="cyan"))
    providers = list(PROVIDER_LABELS)
    for i, provider in enumerate(providers, 1):
        count = len(ProviderSession(provider).models(models))
        console.print(f"{i}. {PROVIDER_LABELS[provider]} ({count} modeli)", markup=False)
    console.print("Provider pozostaje stały także po /clear; zmiana wymaga restartu.", markup=False)
    while True:
        try:
            raw = console.input("Wybierz numer providera: ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
        if not raw.isdigit() or not 1 <= int(raw) <= len(providers):
            console.print("Podaj numer z listy.", markup=False)
            continue
        selected = ProviderSession(providers[int(raw) - 1])
        if not selected.models(models):
            console.print("Brak modeli tego providera w config/models.json.", markup=False)
            continue
        return selected


# ---------------------------------------------------------------------------
# Ekran wyboru modelu
# ---------------------------------------------------------------------------

def pick_model(models: dict[str, str]) -> tuple[str, str]:
    """Wyświetla panel wyboru modelu. Zwraca (label, model_id)."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]aico[/bold cyan] – terminal LLM chat",
        border_style="cyan",
    ))
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="dim", width=4)
    table.add_column("Model", style="bold white")
    table.add_column("Provider", style="dim")

    items = list(models.items())

    for i, (label, model_id) in enumerate(items, start=1):
        provider = get_provider_label(model_id)
        color = "green" if provider == "OpenRouter" else "yellow"
        table.add_row(
            str(i),
            label,
            f"[{color}]{provider}[/{color}]",
        )

    console.print(table)
    console.print()

    while True:
        try:
            raw = console.input("[dim]Wybierz numer modelu:[/dim] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Do widzenia.[/dim]")
            sys.exit(0)

        if not raw.isdigit():
            console.print("[red]Podaj numer z listy.[/red]")
            continue

        idx = int(raw) - 1

        if idx < 0 or idx >= len(items):
            console.print(f"[red]Podaj liczbę od 1 do {len(items)}.[/red]")
            continue

        label, model_id = items[idx]
        return label, model_id


# ---------------------------------------------------------------------------
# Ładowanie MCP
# ---------------------------------------------------------------------------

def init_mcp(servers_path: Path) -> list[dict]:
    """Wczytuje serwery MCP i pobiera tools. Wyświetla status."""
    servers = load_mcp_servers(servers_path)

    if not servers:
        console.print("[dim]Brak serwerów MCP (config/mcp_servers.json pusty lub brak pliku).[/dim]")
        return []

    console.print(f"[dim]Łączę z {len(servers)} serwerem/serwerami MCP...[/dim]")

    servers_with_tools = load_all_tools(servers)

    for s in servers_with_tools:
        if s["success"]:
            console.print(
                f"  [green]✓[/green] [bold]{s['name']}[/bold] "
                f"– [cyan]{len(s['tools'])} tools[/cyan]"
            )
        else:
            console.print(
                f"  [red]✗[/red] [bold]{s['name']}[/bold] "
                f"– [red]{s['error']}[/red]"
            )

    active = [s for s in servers_with_tools if s["success"]]

    if not active:
        console.print("[yellow]Żaden serwer MCP nie odpowiada – tryb MCP wyłączony.[/yellow]")

    console.print()
    return servers_with_tools


# ---------------------------------------------------------------------------
# Prompt string (prompt_toolkit)
# ---------------------------------------------------------------------------

def build_prompt_text(model_label: str, messages: list[dict], mcp_count: int) -> FormattedText:
    tokens = count_chat_tokens(messages)
    tok_str = format_token_count(tokens)
    mcp_str = f"MCP:{mcp_count}" if mcp_count > 0 else "MCP:off"
    # Fragmenty zamiast HTML: etykieta modelu pozostaje dosłownym tekstem.
    return FormattedText([
        ("class:prompt-meta", f"[{model_label} | ~{tok_str} | {mcp_str}] "),
        ("class:prompt-user", "TY › "),
    ])


# ---------------------------------------------------------------------------
# Renderowanie odpowiedzi
# ---------------------------------------------------------------------------

def render_assistant(content: str):
    console.print()
    console.print(Rule(style="dim"))
    console.print(Markdown(content))
    console.print(Rule(style="dim"))
    console.print()


def render_status(status: str, message: str):
    icons = {
        "starting": "🚀",
        "waiting_for_model": "⏳",
        "executing_tool": "🔧",
        "finished": "✅",
        "error": "❌",
        "limit_reached": "⚠️ ",
        "stopped": "🛑",
        "retrying": "↻",
        "incomplete_result": "⚠️",
    }
    if status == "tool_result":
        preview = message[:2000]
        if len(message) > 2000:
            preview += "\n[Podgląd skrócony; pełny wynik w historii i eksporcie.]"
        console.print(preview, markup=False, highlight=False, style="dim")
        return
    icons.update({"budget": "⏸", "approval": "🔒", "task_running": "⏳", "loop": "⚠️"})
    icon = icons.get(status, "•")
    console.print(f"  {icon} {message}", markup=False, highlight=False, style="dim")


# ---------------------------------------------------------------------------
# Komendy specjalne
# ---------------------------------------------------------------------------

def cmd_help():
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", width=12)
    table.add_column(style="dim")

    table.add_row("/help",           "Pokaż tę pomoc")
    table.add_row("/continue, /c",   "Wznów pauzę; oczekujące zadanie najpierw sprawdza get_task")
    table.add_row("/auto [on|off]",   "Tryb automatycznego wznowienia po zakończeniu zadania MCP")
    table.add_row("/steps N",        "Budżet kroków na uruchomienie (domyślnie 40)")
    table.add_row("Ctrl+C",          "Przerwij agenta; nie anuluje zadania uruchomionego w MCP")
    table.add_row("/model",          "Zmień model tylko w ramach wybranego providera")
    table.add_row("/mcp",            "Pokaż status serwerów MCP i tools")
    table.add_row("/mcp connect",    "Połącz z serwerami MCP (auto-connect przy starcie)")
    table.add_row("/mcp disconnect", "Rozłącz serwery MCP")
    table.add_row("/tokens",         "Szczegółowy licznik tokenów")
    table.add_row("/read",           "Czytaj ostatnią odpowiedź od początku; Esc/q wraca do rozmowy")
    table.add_row("/clear",          "Wyczyść historię; provider sesji pozostaje bez zmian")
    table.add_row("/cls",            "Wyczyść ekran terminala")
    table.add_row("/export",         "Zapisz czat do pliku Markdown")
    table.add_row("/compact",        "Streść i zmniejsz kontekst przez aktualny model; bez eksportu")
    table.add_row("/exit",           "Wyjście")

    console.print()
    console.print(Panel(table, title="[bold]Komendy[/bold]", border_style="dim"))
    console.print()


def cmd_mcp(servers_with_tools: list[dict]):
    if not servers_with_tools:
        console.print("[dim]Brak aktywnych serwerów MCP.[/dim]  "
                      "Użyj [cyan]/mcp connect[/cyan] aby się połączyć.")
        return

    console.print()
    for s in servers_with_tools:
        status = "[green]✓[/green]" if s["success"] else "[red]✗[/red]"
        console.print(f"  {status} [bold]{s['name']}[/bold] – {s['url']}")

        if s["success"] and s["tools"]:
            for tool in s["tools"]:
                desc = tool.get("description", "")
                short_desc = (desc[:60] + "…") if len(desc) > 60 else desc
                console.print(f"       [cyan]{tool['name']}[/cyan]  [dim]{short_desc}[/dim]")

        if s.get("error"):
            console.print(f"    [red]{s['error']}[/red]")

    console.print()


def cmd_tokens(messages: list[dict]):
    tokens = count_chat_tokens(messages)
    formatted = format_token_count(tokens)
    warning = get_token_warning(tokens)

    visible = [m for m in messages if m["role"] != "system"]

    console.print()
    console.print(f"  Wiadomości: [bold]{len(visible)}[/bold]")
    console.print(f"  Tokeny (szacunek): [bold cyan]{formatted}[/bold cyan] (~{tokens})")

    if warning:
        console.print(f"  {warning}")

    console.print()


def cmd_export(model_label: str, model_id: str, messages: list[dict]):
    EXPORTS_DIR.mkdir(exist_ok=True)
    filename = build_export_filename("md")
    filepath = EXPORTS_DIR / filename

    content = export_chat_to_markdown(
        model=f"{model_label} ({model_id})",
        messages=messages,
    )

    filepath.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Eksport zapisany: [bold]{filepath}[/bold]")
    console.print()


def cmd_compact(messages: list[dict], model_id: str, state: AgentState) -> list[dict]:
    if state.resumable or state.waiting or state.pending:
        console.print("/compact niedostępne podczas pauzy agenta lub oczekiwania na MCP. "
                      "Najpierw zakończ pracę przez /continue i sprawdź stan zadania.", markup=False)
        return messages
    if not any(m.get("role") != "system" for m in messages):
        console.print("Brak rozmowy do streszczenia.", markup=False)
        return messages
    console.print("Streszczam rozmowę przez aktualny model, bez MCP. "
                  "Nie zapisuję eksportu; podsumowanie może pomijać szczegóły...", markup=False)
    try:
        before = count_chat_tokens(messages)
        compacted = compact_history(messages, model_id)
        after = count_chat_tokens(compacted)
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, (ValueError, NetworkError)) else type(error).__name__
        console.print(f"/compact: {detail}. Historia bez zmian.", markup=False)
        return messages
    console.print(f"Kontekst zmniejszony: ~{format_token_count(before)} → "
                  f"~{format_token_count(after)} tokenów (szacunek). "
                  "Możesz kontynuować rozmowę.", markup=False)
    return compacted


def cmd_clear(messages: list[dict]) -> list[dict]:
    # Zachowaj system message jeśli jest
    system = [m for m in messages if m["role"] == "system"]
    console.print("  [dim]Historia czatu wyczyszczona.[/dim]")
    console.print()
    return system


def cmd_cls():
    import os
    os.system("cls" if os.name == "nt" else "clear")


# ---------------------------------------------------------------------------
# Wysłanie wiadomości (tryb bez MCP)
# ---------------------------------------------------------------------------

def send_message(user_input: str, messages: list[dict], model_id: str) -> list[dict]:
    messages.append({"role": "user", "content": user_input})

    console.print("[dim]Czekam na odpowiedź...[/dim]")

    try:
        reply = ask_llm(model=model_id, messages=messages)
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, NetworkError) else type(error).__name__
        console.print(f"Błąd/przerwanie: {detail}", markup=False)
        messages.pop()
        return messages

    messages.append({"role": "assistant", "content": reply})
    render_assistant(reply)
    return messages


# ---------------------------------------------------------------------------
# Wysłanie wiadomości (tryb MCP automatic)
# ---------------------------------------------------------------------------

def send_message_mcp(
    user_input: str,
    messages: list[dict],
    model_id: str,
    servers_with_tools: list[dict],
    max_iterations: int,
    state: AgentState,
) -> list[dict]:
    if user_input:
        messages.append({"role": "user", "content": user_input})

    console.print()

    def on_message(role: str, content: str):
        if role == "assistant":
            render_assistant(content)

    def on_status(status: str, message: str):
        render_status(status, message)

    messages = run_native(
        state=state,
        messages=messages,
        model=model_id,
        servers_with_tools=servers_with_tools,
        on_message=on_message,
        on_status=on_status,
        max_iterations=max_iterations,
    )

    return messages


# ---------------------------------------------------------------------------
# Tryb /auto: automatyczne oczekiwanie na zadanie MCP
# ---------------------------------------------------------------------------

def auto_wait_for_task(
    messages: list[dict],
    model_id: str,
    active_servers: list[dict],
    max_iterations: int,
    agent_state: AgentState,
    console: Console,
) -> list[dict]:
    """Poll known MCP tasks and resume the agent without recording polling calls."""
    while agent_state.waiting and agent_state.reason in {"approval", "task_running"}:
        wait = agent_state.waiting
        task_id = wait["task_id"]
        console.print()
        console.print(
            f"  ⏳ [dim]Tryb /auto: czekam na zadanie [bold]{task_id}[/bold] "
            "(Ctrl+C → wróć do oczekiwania ręcznego)[/dim]"
        )

        def on_tick(task_status: str, elapsed: int):
            status_labels = {
                "awaiting_approval": "🔒 czeka na zgodę w panelu",
                "queued":            "⏳ w kolejce",
                "running":           "⚙️  wykonywanie",
            }
            label = status_labels.get(task_status, task_status)
            console.print(
                f"  [dim]  zadanie {task_id}: {label} (+{elapsed}s)[/dim]",
                highlight=False,
            )

        try:
            poll_result = poll_task(
                url=wait["url"],
                task_id=task_id,
                get_task_alias=wait["get_task_alias"],
                on_tick=on_tick,
            )
        except KeyboardInterrupt:
            agent_state.reason = "stopped"
            console.print(
                "\n  [dim]Ctrl+C — przerywam oczekiwanie. Zadanie nadal działa na serwerze. "
                "Użyj /continue albo /auto on, aby wznowić.[/dim]"
            )
            return messages

        final_status = poll_result["status"]
        if final_status in {"error", "timeout"}:
            # Do not immediately restart polling on the next CLI iteration.
            agent_state.reason = "stopped"
            console.print(
                f"  [yellow]⚠️ {poll_result['error']}[/yellow]\n"
                "  Użyj /continue do ręcznego sprawdzenia albo /auto on, aby wznowić polling."
            )
            return messages

        if final_status == "done":
            console.print(f"  [green]✅ Zadanie {task_id} zakończone — wznawiamy.[/green]")
        else:
            console.print(
                f"  [yellow]⚠️ Zadanie {task_id} zakończyło się stanem "
                f"[bold]{final_status}[/bold]; nie ponawiam operacji.[/yellow]"
            )

        # The runner performs one final get_task, records its result, and either
        # continues the model or exposes the next approval-gated task.
        messages = send_message_mcp("", messages, model_id, active_servers,
                                    max_iterations, agent_state)
    return messages


# ---------------------------------------------------------------------------
# Główna pętla
# ---------------------------------------------------------------------------

def main():
    models = load_models()
    provider_session = pick_provider(models)
    session_models = provider_session.models(models)
    model_label, model_id = pick_model(session_models)
    provider_session.validate_model(model_id)

    # Sprawdź klucz API
    if not has_llm_api_key(model_id):
        console.print(f"[red]{get_missing_api_key_message(model_id)}[/red]")
        console.print("[dim]Uzupełnij plik .env i uruchom ponownie.[/dim]")
        sys.exit(1)

    # MCP auto-connect – domyślnie łączy przy starcie; MCP_AUTO_CONNECT=0 wyłącza
    auto_connect = os.getenv("MCP_AUTO_CONNECT", "1") != "0"
    servers_with_tools: list[dict] = []
    active_servers: list[dict] = []
    mcp_count = 0

    if auto_connect:
        try:
            servers_with_tools = init_mcp(MCP_SERVERS_PATH)
            active_servers = [s for s in servers_with_tools if s["success"]]
            mcp_count = len(active_servers)
        except (Exception, KeyboardInterrupt) as error:
            console.print(
                f"Automatyczne łączenie MCP przerwane ({type(error).__name__}). "
                "Użyj /mcp connect po starcie.",
                markup=False,
            )

    provider = get_provider_label(model_id)
    color = "green" if provider == "OpenRouter" else "yellow"

    console.print(Panel.fit(
        f"Model: [bold]{model_label}[/bold]  [{color}]({provider})[/{color}]\n"
        f"MCP:   [cyan]{mcp_count} server(s) aktywnych[/cyan]\n"
        f"Wpisz [bold cyan]/help[/bold cyan] po listę komend.\n"
        "[dim]Kontakt: Pawel Rajko-Nenow · WwP/MFD (developer)[/dim]",
        border_style="dim",
    ))
    console.print()

    # Historia sesji
    messages: list[dict] = []

    # prompt_toolkit session (historia strzałkami ↑↓)
    pt_style = Style.from_dict({
        "": "#5fd7d7",
        "prompt-meta": "#888888",
        "prompt-user": "#5fd7d7 bold",
    })
    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        style=pt_style,
    )

    agent_state = AgentState()
    auto_mode: bool = False
    try:
        max_iterations = int(os.getenv("MCP_MAX_ITERATIONS", str(MAX_ITERATIONS_DEFAULT)))
        if max_iterations < 1:
            raise ValueError()
    except ValueError:
        max_iterations = MAX_ITERATIONS_DEFAULT
        console.print("Niepoprawne MCP_MAX_ITERATIONS; używam 40 kroków.", markup=False)

    while True:
        if auto_mode and agent_state.waiting and agent_state.reason in {"approval", "task_running"}:
            messages = auto_wait_for_task(
                messages=messages,
                model_id=model_id,
                active_servers=active_servers,
                max_iterations=max_iterations,
                agent_state=agent_state,
                console=console,
            )

        prompt_text = build_prompt_text(model_label, messages, mcp_count)

        try:
            user_input = session.prompt(prompt_text)
        except KeyboardInterrupt:
            console.print("\n[dim]Ctrl+C – wpisz /exit aby wyjść.[/dim]")
            continue
        except EOFError:
            console.print("\n[dim]Do widzenia.[/dim]")
            break

        user_input = user_input.strip()

        if not user_input:
            continue

        # --- Komendy ---
        if user_input.lower() in ("/exit", "/quit", "/q"):
            console.print("[dim]Do widzenia.[/dim]")
            break

        if user_input.lower() == "/help":
            cmd_help()
            continue

        if user_input.lower() in ("/continue", "/c"):
            if not active_servers:
                console.print("Najpierw /mcp connect.", markup=False)
            elif not agent_state.resumable:
                console.print("Brak pauzy do wznowienia. Napisz nowe polecenie, jeśli model skończył odpowiedź.", markup=False)
            else:
                messages = send_message_mcp("", messages, model_id, active_servers, max_iterations, agent_state)
            continue

        if user_input.lower().startswith("/auto"):
            arg = user_input[5:].strip().lower()
            if arg == "on":
                auto_mode = True
                if agent_state.waiting and agent_state.reason == "stopped":
                    agent_state.reason = "task_running"
                console.print("  [green]✓[/green] Tryb /auto [bold]włączony[/bold]. "
                              "Po zatwierdzeniu zadania w panelu aico wznowi się automatycznie. "
                              "Ctrl+C przerywa oczekiwanie.", markup=True)
            elif arg == "off":
                auto_mode = False
                console.print("  [dim]Tryb /auto wyłączony. Użyj /continue po każdym zadaniu.[/dim]")
            elif arg == "":
                stan = "[green]włączony[/green]" if auto_mode else "[dim]wyłączony[/dim]"
                console.print(f"  Tryb /auto: {stan}. Użyj [cyan]/auto on[/cyan] lub [cyan]/auto off[/cyan].")
            else:
                console.print("Użycie: /auto, /auto on, /auto off", markup=False)
            continue

        if user_input.lower() == "/steps" or user_input.lower().startswith("/steps "):
            parts = user_input.split()
            if len(parts) == 1:
                console.print(f"Budżet: {max_iterations} kroków.", markup=False)
            elif len(parts) == 2 and parts[1].isdigit() and int(parts[1]) > 0:
                max_iterations = int(parts[1])
                console.print(f"Budżet: {max_iterations} kroków; po nim pauza, nie utrata zadania.", markup=False)
            else:
                console.print("Użycie: /steps N (dodatnia liczba całkowita).", markup=False)
            continue

        if user_input.lower().startswith("/mcp"):
            subcmd = user_input[4:].strip().lower()
            if agent_state.waiting and subcmd == "disconnect":
                console.print("Najpierw sprawdź oczekujące zadanie przez /continue albo /clear.", markup=False)
                continue

            if subcmd == "connect":
                try:
                    refreshed_servers = init_mcp(MCP_SERVERS_PATH)
                except (Exception, KeyboardInterrupt) as error:
                    console.print(f"Łączenie MCP przerwane ({type(error).__name__}). "
                                  "Sprawdź config/mcp_servers.json; poprzedni stan zachowany.", markup=False)
                    continue
                servers_with_tools = refreshed_servers
                active_servers = [s for s in servers_with_tools if s["success"]]
                mcp_count = len(active_servers)
                console.print(
                    f"  [green]✓[/green] MCP: [cyan]{mcp_count} server(s) aktywnych[/cyan]"
                )
                console.print()

            elif subcmd == "disconnect":
                servers_with_tools = []
                active_servers = []
                mcp_count = 0
                console.print("  [dim]MCP rozłączony.[/dim]")
                console.print()

            else:
                cmd_mcp(servers_with_tools)

            continue

        if user_input.lower() == "/tokens":
            cmd_tokens(messages)
            continue

        if user_input.lower() == "/read":
            content = last_assistant_response(messages)
            if content is None:
                console.print("Brak odpowiedzi modelu do przeczytania.", markup=False)
            else:
                read_response(content)
            continue

        if user_input.lower() == "/clear":
            if agent_state.waiting:
                console.print("/clear zapomina zadanie, ale go nie anuluje. Sprawdź panel MCP.", markup=False)
                if console.input("Wpisz CLEAR, aby potwierdzić: ").strip() != "CLEAR":
                    continue
            messages = cmd_clear(messages)
            agent_state = AgentState()
            continue

        if user_input.lower() == "/cls":
            cmd_cls()
            continue

        if user_input.lower() == "/export":
            cmd_export(model_label, model_id, messages)
            continue

        if user_input.lower() == "/compact":
            provider_session.validate_model(model_id)
            compacted = cmd_compact(messages, model_id, agent_state)
            if compacted is not messages:
                messages = compacted
                agent_state = AgentState()
            continue

        if user_input.lower() == "/model":
            if agent_state.waiting:
                console.print("Najpierw zakończ oczekujące zadanie przez /continue albo /clear.", markup=False)
                continue
            candidate_label, candidate_id = pick_model(session_models)
            try:
                provider_session.validate_model(candidate_id)
            except ValueError as error:
                console.print(str(error), markup=False)
                continue
            if not has_llm_api_key(candidate_id):
                console.print(get_missing_api_key_message(candidate_id), markup=False)
                continue
            model_label, model_id = candidate_label, candidate_id
            agent_state = AgentState()

            provider = get_provider_label(model_id)
            color = "green" if provider == "OpenRouter" else "yellow"
            console.print(
                f"  [green]✓[/green] Model zmieniony na: "
                f"[bold]{model_label}[/bold] [{color}]({provider})[/{color}]"
            )
            console.print()
            continue

        if user_input.startswith("/"):
            console.print(f"[red]Nieznana komenda: {user_input}[/red]  "
                          f"Wpisz [cyan]/help[/cyan].")
            continue

        # --- Wiadomość do modelu ---
        provider_session.validate_model(model_id)
        if agent_state.waiting:
            console.print("Agent czeka na zadanie MCP. Sprawdź panel i użyj /continue; /clear porzuca kontekst.", markup=False)
            continue
        agent_state = AgentState()
        if active_servers:
            messages = send_message_mcp(
                user_input=user_input,
                messages=messages,
                model_id=model_id,
                servers_with_tools=active_servers,
                max_iterations=max_iterations,
                state=agent_state,
            )
        else:
            messages = send_message(
                user_input=user_input,
                messages=messages,
                model_id=model_id,
            )

        # Licznik tokenów po każdej odpowiedzi
        tokens = count_chat_tokens(messages)
        tok_str = format_token_count(tokens)
        warning = get_token_warning(tokens)
        warn_str = f"  {warning}" if warning else ""
        console.print(f"[dim]📊 Tokeny (szacunek): ~{tok_str}{warn_str}[/dim]")


if __name__ == "__main__":
    main()
