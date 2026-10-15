import json
import re
from datetime import datetime


def sanitize_filename(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "_", text, flags=re.UNICODE)
    text = text.strip("_")

    if not text:
        return "chat"

    return text[:80]


def export_chat_to_markdown(model: str, messages: list[dict]) -> str:
    timestamp = datetime.now().isoformat(timespec="seconds")

    parts = [
        f"# Chat export",
        "",
        "## Metadane",
        "",
        f"- Model: `{model}`",
        f"- Eksport: `{timestamp}`",
        "",
        "## Wiadomości",
        "",
    ]

    for index, message in enumerate(messages, start=1):
        role = message.get("role", "unknown")
        content = message.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2)
        if message.get("tool_calls"):
            content += "\n\nWywołania narzędzi:\n```json\n" + json.dumps(
                message["tool_calls"], ensure_ascii=False, indent=2
            ) + "\n```"
        if role == "tool":
            content = f"tool_call_id: `{message.get('tool_call_id', '')}`\n\n{content}"

        # Pomijamy system messages w eksporcie
        if role == "system":
            continue

        parts.extend(
            [
                f"### {index}. {role}",
                "",
                content,
                "",
                "---",
                "",
            ]
        )

    return "\n".join(parts)


def export_chat_to_json(model: str, messages: list[dict]) -> str:
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "messages": [m for m in messages if m.get("role") != "system"],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def build_export_filename(extension: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"chat_{timestamp}.{extension}"
