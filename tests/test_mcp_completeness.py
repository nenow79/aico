import copy
import json
import unittest

from services.mcp_completeness import is_incomplete
from services.native_runner import AgentState, run_native
from test_native_agent import servers, tool_call, calls_response, final_response


class CompletenessTests(unittest.TestCase):
    def test_explicit_nested_metadata(self):
        for value in ({"data": {"truncated": True}},
                      {"results": [{"data": {"partial": True}}]},
                      {"instructions_complete": False},
                      {"data": {"resources_truncated": True}}):
            self.assertTrue(is_incomplete(value))

    def test_text_and_false_flags_are_not_incomplete(self):
        for value in ({"content": '{"truncated": true}'},
                      {"truncated": False, "partial": False},
                      {"truncated": "true"}, {"instructions_complete": True}):
            self.assertFalse(is_incomplete(value))

    def test_partial_result_preserved_and_model_can_request_line_200(self):
        payload = {"success": True, "data": {
            "content": "x" * 15000, "truncated": True, "end_line": 500}}
        before = copy.deepcopy(payload)
        responses = iter([
            calls_response(tool_call("read_file", arguments={"filepath": "file.py"})),
            calls_response(tool_call("read_file", "c2", {
                "filepath": "file.py", "start_line": 200, "end_line": 250,
                "line_numbers": True, "max_chars": 12000})), final_response()])
        seen, executed, notices = [], [], []
        def completion(**kwargs):
            seen.append(kwargs)
            return next(responses)
        def tool(**kwargs):
            executed.append(json.loads(kwargs["arguments_json"]))
            return {"success": True, "result": payload if len(executed) == 1 else {
                "success": True, "data": {"content": "200: continuation", "truncated": False}}}
        history = []
        run_native(history, "litellm:test", servers(), lambda *args: None,
                   on_status=lambda *args: notices.append(args),
                   completion_fn=completion, tool_fn=tool)
        stored = json.loads(seen[1]["messages"][-1]["content"])
        self.assertEqual(stored["mcp_result"], before)
        self.assertIn("Niepełny wynik", stored["aico_notice"])
        self.assertIn("end_line+1", seen[1]["messages"][0]["content"])
        self.assertEqual(executed[1]["start_line"], 200)
        self.assertEqual(payload, before)
        self.assertEqual(sum(reason == "incomplete_result" for reason, _ in notices), 1)

    def test_partial_write_result_does_not_replay_or_bypass_approval(self):
        state = AgentState()
        executed = []
        def tool(**kwargs):
            executed.append(kwargs["tool_name"])
            return {"success": True, "result": {"success": True, "data": {
                "task_id": 42, "status": "awaiting_approval", "truncated": True}}}
        run_native([], "litellm:test", servers(), lambda *args: None, state=state,
                   completion_fn=lambda **kwargs: calls_response(tool_call("edit_file")), tool_fn=tool)
        self.assertEqual(executed, ["edit_file"])
        self.assertEqual(state.reason, "approval")
        self.assertEqual(state.waiting["task_id"], 42)
