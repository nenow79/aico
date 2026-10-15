"""Local, read-only pager for an assistant response; no model or MCP calls."""
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea


def last_assistant_response(messages: list[dict]) -> str | None:
    for message in reversed(messages):
        content = message.get("content")
        if message.get("role") == "assistant" and isinstance(content, str) and content.strip():
            return content
    return None


def build_reader(content: str) -> Application:
    text = TextArea(text=content, read_only=True, scrollbar=True, wrap_lines=True)
    text.buffer.cursor_position = 0
    keys = KeyBindings()

    @keys.add("escape", eager=True)
    @keys.add("q")
    @keys.add("c-c")
    @keys.add("c-d")
    def close(event):
        event.app.exit()

    @keys.add("home")
    @keys.add("c-home")
    def beginning(event):
        text.buffer.cursor_position = 0

    @keys.add("end")
    @keys.add("c-end")
    def end(event):
        text.buffer.cursor_position = len(text.buffer.text)

    return Application(
        layout=Layout(HSplit([
            Window(FormattedTextControl("Ostatnia odpowiedź | tekst Markdown"), height=1),
            text,
            Window(FormattedTextControl(
                "↑↓ / PgUp/PgDn: przewijaj | Home/End: początek/koniec | Esc/q: wróć"
            ), height=1),
        ]), focused_element=text),
        key_bindings=keys,
        full_screen=True,
        mouse_support=True,
        enable_page_navigation_bindings=True,
    )


def read_response(content: str) -> None:
    try:
        build_reader(content).run()
    except (EOFError, KeyboardInterrupt):
        # Return to the chat; closing a reader never changes agent/task state.
        pass
