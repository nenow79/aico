"""Offline compaction tests: mock LLM, no network or exports."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

from services.agent_protocol import Completion, ProtocolError
from services.context_compactor import compact_history, SUMMARY_PREFIX
from services.native_runner import AgentState
from services.token_counter import count_chat_tokens


def tool_turn():
    return [
        {"role": "user", "content": "Sprawdź plik"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": "odczytano"},
        {"role": "assistant", "content": "Gotowe"},
    ]


class CompactorTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"role": "system", "content": "Oryginalne zasady"},
            {"role": "user", "content": "Stare zadanie " * 1000},
            {"role": "assistant", "content": "Ustalenia " * 1000},
        ] + tool_turn()
        self.original = copy.deepcopy(self.messages)
        self.llm = Mock(return_value=Completion({"role": "assistant", "content": "Cel, ustalenia i stan."}, "stop"))

    def test_smaller_preserves_system_and_complete_last_turn(self):
        result = compact_history(self.messages, "bmf:test", self.llm)
        self.assertEqual(self.messages, self.original)
        self.assertEqual(result[0], self.messages[0])
        self.assertEqual(result[1]["role"], "user")
        self.assertTrue(result[1]["content"].startswith(SUMMARY_PREFIX))
        self.assertEqual(result[2:], tool_turn())
        self.assertLess(count_chat_tokens(result), count_chat_tokens(self.messages))
        result[-1]["content"] = "changed"
        self.assertEqual(self.messages, self.original)
        kwargs = self.llm.call_args.kwargs
        self.assertEqual(kwargs["model"], "bmf:test")
        self.assertIsNone(kwargs["tools"])
        self.assertEqual([m["role"] for m in kwargs["messages"]], ["system", "user"])
        self.assertIn("tool_call_id", kwargs["messages"][1]["content"])
        self.assertIn("Oryginalne zasady", kwargs["messages"][1]["content"])

    def test_single_large_turn_is_compacted(self):
        result = compact_history(self.messages[:3], "litellm:test", self.llm)
        self.assertEqual(len(result), 2)

    def test_empty_history_does_not_call_llm(self):
        for messages in ([], self.messages[:1]):
            with self.assertRaises(ValueError):
                compact_history(messages, "test", self.llm)
        self.llm.assert_not_called()

    def test_bad_completion_does_not_change_history(self):
        for reason, content, calls in [("length", "partial", None), ("content_filter", "blocked", None),
                                       (None, "text", None), ("stop", " ", None), ("stop", None, None),
                                       ("stop", "text", [{"id": "x"}])]:
            self.llm.return_value = Completion({"role": "assistant", "content": content, "tool_calls": calls}, reason)
            with self.assertRaises(ProtocolError):
                compact_history(self.messages, "test", self.llm)
            self.assertEqual(self.messages, self.original)

    def test_errors_and_interrupt_preserve_history(self):
        for error in (RuntimeError("offline"), KeyboardInterrupt()):
            self.llm.side_effect = error
            with self.assertRaises(type(error)):
                compact_history(self.messages, "test", self.llm)
            self.assertEqual(self.messages, self.original)

    def test_no_reduction_is_rejected(self):
        self.llm.return_value = Completion({"role": "assistant", "content": "long " * 20000}, "stop")
        with self.assertRaises(ValueError):
            compact_history(self.messages, "test", self.llm)
        self.assertEqual(self.messages, self.original)

    def test_invalid_tool_history_does_not_call_llm(self):
        cases = [self.messages[:-2], self.messages[:3] + [tool_turn()[2]],
                 self.messages[:3] + [tool_turn()[1], {"role": "user", "content": "new"}]]
        for messages in cases:
            with self.assertRaises(ProtocolError):
                compact_history(messages, "test", self.llm)
        self.llm.assert_not_called()

    def test_second_compaction_includes_previous_summary(self):
        first = compact_history(self.messages, "test", self.llm)
        first += [{"role": "user", "content": "Nowe zadanie " * 1000},
                  {"role": "assistant", "content": "Nowe wyniki " * 1000}]
        # Add another small turn so the large turn can be dropped.
        first += [{"role": "user", "content": "Co dalej?"}, {"role": "assistant", "content": "Testy."}]
        second = compact_history(first, "test", self.llm)
        transcript = json.loads(self.llm.call_args.kwargs["messages"][1]["content"])
        self.assertTrue(any(m["content"].startswith(SUMMARY_PREFIX) for m in transcript))
        self.assertEqual(sum(m["content"].startswith(SUMMARY_PREFIX) for m in second), 1)


class CompactCLITests(unittest.TestCase):
    def test_paused_agent_is_blocked(self):
        import aico
        for state in (AgentState(reason="approval"), AgentState(reason="budget"),
                      AgentState(waiting={"task_id": 1}), AgentState(pending=["call"])):
            messages = [{"role": "user", "content": "test"}]
            with patch.object(aico, "compact_history") as compact, patch.object(aico, "console", Mock()):
                self.assertIs(aico.cmd_compact(messages, "test", state), messages)
            compact.assert_not_called()

    def test_success_and_failure_are_transactional_without_export(self):
        import aico
        messages = [{"role": "user", "content": "test"}]
        compacted = [{"role": "user", "content": "summary"}]
        with patch.object(aico, "console", Mock()), patch.object(aico, "cmd_export") as export:
            with patch.object(aico, "compact_history", return_value=compacted):
                self.assertIs(aico.cmd_compact(messages, "litellm:test", AgentState()), compacted)
            for error in (ProtocolError("bad"), KeyboardInterrupt()):
                with patch.object(aico, "compact_history", side_effect=error):
                    self.assertIs(aico.cmd_compact(messages, "litellm:test", AgentState()), messages)
            export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
