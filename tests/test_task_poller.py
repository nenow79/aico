"""Offline tests for automatic MCP task polling."""
import json
import unittest
from unittest.mock import patch

from services.task_poller import poll_task


class PollTaskTests(unittest.TestCase):
    def test_pending_then_done_polls_known_task_without_other_tool_calls(self):
        responses = [
            {"success": True, "result": {"success": True, "data": {"task_id": 7, "status": "running"}}},
            {"success": True, "result": {"success": True, "data": {"task_id": 7, "status": "done"}}},
        ]
        calls = []
        ticks = []

        def tool_fn(**kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with patch("services.task_poller.time.sleep") as sleep:
            result = poll_task(
                url="http://localhost:8101/mcp", task_id=7,
                get_task_alias="get_task_alias", tool_fn=tool_fn,
                on_tick=lambda status, elapsed: ticks.append(status),
            )

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["task_data"]["task_id"], 7)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["tool_name"] == "get_task" for call in calls))
        self.assertTrue(all(json.loads(call["arguments_json"]) == {"task_id": 7} for call in calls))
        self.assertEqual(ticks, ["running"])
        sleep.assert_called_once_with(2.0)

    def test_awaiting_approval_is_reported_and_keeps_polling(self):
        responses = [
            {"success": True, "result": {"data": {"task_id": 8, "status": "awaiting_approval"}}},
            {"success": True, "result": {"data": {"task_id": 8, "status": "rejected"}}},
        ]
        ticks = []
        with patch("services.task_poller.time.sleep"):
            result = poll_task(
                url="local", task_id=8, get_task_alias="alias",
                tool_fn=lambda **_: responses.pop(0),
                on_tick=lambda status, elapsed: ticks.append(status),
            )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(ticks, ["awaiting_approval"])

    def test_structured_content_envelope(self):
        result = poll_task(
            url="local", task_id=9, get_task_alias="alias",
            tool_fn=lambda **_: {"success": True, "result": {
                "structured_content": {"success": True, "data": {"task_id": 9, "status": "done"}}
            }},
        )
        self.assertEqual(result["status"], "done")

    def test_unknown_status_stops_instead_of_polling_forever(self):
        result = poll_task(
            url="local", task_id=10, get_task_alias="alias",
            tool_fn=lambda **_: {"success": True, "result": {"data": {"status": "mystery"}}},
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("nieznany", result["error"])

    def test_transport_error_returns_error_without_retrying(self):
        calls = []

        def tool_fn(**kwargs):
            calls.append(kwargs)
            return {"success": False, "error": "timeout"}

        result = poll_task(url="local", task_id=11, get_task_alias="alias", tool_fn=tool_fn)
        self.assertEqual(result["status"], "error")
        self.assertEqual(len(calls), 1)

    def test_keyboard_interrupt_propagates(self):
        def tool_fn(**kwargs):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            poll_task(url="local", task_id=12, get_task_alias="alias", tool_fn=tool_fn)

    def test_timeout_is_bounded(self):
        pending = {"success": True, "result": {"data": {"status": "running"}}}
        with patch("services.task_poller.time.monotonic", side_effect=[0, 0, 2]), \
             patch("services.task_poller.time.sleep"):
            result = poll_task(
                url="local", task_id=13, get_task_alias="alias",
                tool_fn=lambda **_: pending, poll_interval=1, max_seconds=1,
            )
        self.assertEqual(result["status"], "timeout")


if __name__ == "__main__":
    unittest.main()
