"""Automatic task polling for /auto mode.

Polls a known MCP task until it reaches a terminal state.
Does NOT touch model history. The caller decides what to do with the result.
"""
import time
from typing import Callable

from services.mcp_client import call_mcp_tool
from services.agent_protocol import unwrap_mcp_result

# How long to wait between polls (seconds). Keep it short enough to feel
# responsive but not so short that it hammers the MCP server.
POLL_INTERVAL = 2.0

# Safety cap: stop polling after this many seconds regardless of task state.
# Keeps the terminal recoverable if the server goes silent.
MAX_POLL_SECONDS = 3600.0

TERMINAL_STATES = {"done", "failed", "rejected", "timed_out", "cancelled", "interrupted"}
PENDING_STATES  = {"awaiting_approval", "queued", "running"}


class PollTimeout(RuntimeError):
    """Raised when MAX_POLL_SECONDS is exceeded without a terminal state."""


def poll_task(
    *,
    url: str,
    task_id: int,
    get_task_alias: str,
    on_tick: Callable[[str, int], None] | None = None,
    tool_fn: Callable = call_mcp_tool,
    poll_interval: float = POLL_INTERVAL,
    max_seconds: float = MAX_POLL_SECONDS,
) -> dict:
    """Synchronously poll `get_task` until a terminal state is reached.

    Parameters
    ----------
    url:              MCP server URL.
    task_id:          Task identifier from AgentState.waiting.
    get_task_alias:   Resolved alias for `get_task` on that server.
    on_tick:          Optional callback(task_status, elapsed_seconds) called
                      after each poll (including the first one). Never called
                      after a terminal state is returned.
    tool_fn:          Injected transport; defaults to call_mcp_tool.
    poll_interval:    Seconds between polls.
    max_seconds:      Absolute wall-clock limit.

    Returns
    -------
    dict with keys:
      status    – terminal task status string, or "error" / "timeout"
      task_data – raw task dict from the last successful get_task response
                  (None on transport error)
      error     – human-readable description when status is "error" / "timeout"

    Never raises (except KeyboardInterrupt which propagates normally so the
    caller can display a message and return control to the user).
    """
    import json
    started = time.monotonic()

    while True:
        elapsed = int(time.monotonic() - started)

        # --- transport call -------------------------------------------------
        try:
            result = tool_fn(
                url=url,
                tool_name="get_task",
                arguments_json=json.dumps({"task_id": task_id}),
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            return {
                "status": "error",
                "task_data": None,
                "error": f"Błąd odpytywania zadania: {type(exc).__name__}",
            }

        # --- parse result ---------------------------------------------------
        if not isinstance(result, dict) or not result.get("success"):
            error = result.get("error") if isinstance(result, dict) else None
            return {
                "status": "error",
                "task_data": None,
                "error": f"get_task nieudane: {error or 'brak odpowiedzi'}",
            }

        # MCP results may use structured content or a {success, data} envelope.
        raw = unwrap_mcp_result(result.get("result", {}))
        if isinstance(raw, dict):
            raw = raw.get("structured_content", raw.get("structuredContent", raw))
        if isinstance(raw, dict):
            task_data = raw.get("data", raw)
            if not isinstance(task_data, dict):
                task_data = raw
        else:
            task_data = {}

        task_status = task_data.get("status") if isinstance(task_data, dict) else None
        if task_status not in PENDING_STATES | TERMINAL_STATES:
            return {
                "status": "error",
                "task_data": None,
                "error": "get_task zwróciło nieznany lub brakujący status; użyj /continue do ręcznego sprawdzenia.",
            }

        # --- terminal? ------------------------------------------------------
        if task_status in TERMINAL_STATES:
            return {"status": task_status, "task_data": task_data, "error": ""}

        # --- still pending --------------------------------------------------
        if task_status in PENDING_STATES and on_tick:
            on_tick(task_status, elapsed)

        # --- timeout guard --------------------------------------------------
        if time.monotonic() - started >= max_seconds:
            return {
                "status": "timeout",
                "task_data": task_data,
                "error": f"Przekroczono limit {max_seconds:.0f} s oczekiwania na zadanie.",
            }

        # --- wait -----------------------------------------------------------
        time.sleep(poll_interval)
