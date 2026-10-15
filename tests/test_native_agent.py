"""Offline tests: python -m unittest discover -s tests -v"""
import json
import unittest

from services.agent_protocol import Completion, ProtocolError, build_native_tools, parse_completion, public_result
from services.native_runner import AgentState, run_native


def servers():
    return [{"name": "sklr", "url": "http://localhost:8101/mcp", "success": True, "tools": [
        {"name": name, "input_schema": {"type": "object", "properties": {}}}
        for name in ("read_file", "edit_file", "get_task", "secret_reveal")
    ]}]


def tool_call(name, call_id="c1", arguments=None):
    _, bindings = build_native_tools(servers())
    alias = next(key for key, (_, tool) in bindings.items() if tool == name)
    return {"id": call_id, "type": "function", "function": {
        "name": alias, "arguments": json.dumps(arguments or {}),
    }}


def calls_response(*calls):
    return Completion({"role": "assistant", "content": "", "tool_calls": list(calls)}, "tool_calls")


def final_response():
    return Completion({"role": "assistant", "content": "Gotowe."}, "stop")


class ProtocolTests(unittest.TestCase):
    def test_reasoning_is_not_final_content(self):
        result = parse_completion({"choices": [{"message": {
            "content": None, "reasoning_content": "Muszę sprawdzić plik.",
        }, "finish_reason": "stop"}]})
        self.assertEqual(result.message["content"], "")

    def test_native_calls_and_usage_preserved(self):
        call = tool_call("read_file")
        response = parse_completion({"choices": [{"message": {"tool_calls": [call]},
                                                   "finish_reason": "tool_calls"}],
                                     "usage": {"total_tokens": 12}})
        self.assertEqual(response.message["tool_calls"], [call])
        self.assertEqual(response.usage["total_tokens"], 12)

    def test_duplicate_ids_rejected(self):
        call = tool_call("read_file")
        with self.assertRaises(ProtocolError):
            parse_completion({"choices": [{"message": {"tool_calls": [call, call]}}]})

    def test_aliases_and_secrets(self):
        tools, bindings = build_native_tools(servers())
        self.assertEqual(len(tools), 3)
        self.assertNotIn("secret_reveal", [name for _, name in bindings.values()])
        self.assertTrue(all(len(item["function"]["name"]) <= 64 for item in tools))
        self.assertNotIn("sensitive", json.dumps(public_result({"secret_result": {"value": "sensitive"}})))

    def test_same_tool_on_two_servers_has_distinct_alias(self):
        configured = servers()
        configured.append({**configured[0], "name": "other", "url": "http://localhost:8200/mcp"})
        tools, bindings = build_native_tools(configured)
        self.assertEqual(len(bindings), 6)


class RunnerTests(unittest.TestCase):
    def run_agent(self, responses, tool_fn, messages=None, state=None, budget=40):
        iterator = iter(responses)
        seen = []
        def completion_fn(**kwargs):
            seen.append(kwargs)
            return next(iterator)
        history = messages if messages is not None else [{"role": "user", "content": "Sprawdź."}]
        state = state if state is not None else AgentState()
        run_native(history, "litellm:test", servers(), lambda *args: None,
                   max_iterations=budget, state=state, completion_fn=completion_fn, tool_fn=tool_fn)
        return history, state, seen

    def test_real_tool_history_and_final(self):
        executed = []
        def tool(**kwargs):
            executed.append(kwargs)
            return {"success": True, "result": {"structured_content": {"success": True, "data": "text"}}}
        history, state, seen = self.run_agent([calls_response(tool_call("read_file")), final_response()], tool)
        self.assertEqual(state.reason, "finished")
        self.assertEqual(len(executed), 1)
        self.assertEqual(history[2]["role"], "tool")
        self.assertEqual(history[2]["tool_call_id"], history[1]["tool_calls"][0]["id"])
        self.assertEqual(seen[1]["messages"][-1]["role"], "tool")

    def test_budget_resumes_without_reexecuting(self):
        executed = []
        def tool(**kwargs):
            executed.append(kwargs)
            return {"success": True, "result": {"success": True}}
        history, state, _ = self.run_agent([calls_response(tool_call("read_file"))], tool, budget=1)
        self.assertEqual(state.reason, "budget")
        self.run_agent([final_response()], tool, history, state)
        self.assertEqual(len(executed), 1)
        self.assertEqual(state.reason, "finished")

    def test_approval_resume_checks_task_only(self):
        executed = []
        task_status = ["awaiting_approval", "done"]
        def tool(**kwargs):
            executed.append(kwargs["tool_name"])
            if kwargs["tool_name"] == "edit_file":
                return {"success": True, "result": {"success": True, "data": {
                    "task_id": 42, "status": "awaiting_approval"}}}
            return {"success": True, "result": {"success": True, "data": {
                "id": 42, "status": task_status.pop(0)}}}
        history, state, _ = self.run_agent([calls_response(tool_call("edit_file"))], tool)
        self.assertEqual(state.reason, "approval")
        self.run_agent([], tool, history, state)
        self.assertEqual(state.reason, "approval")
        self.run_agent([final_response()], tool, history, state)
        self.assertEqual(executed, ["edit_file", "get_task", "get_task"])
        self.assertIsNone(state.waiting)
        self.assertEqual(state.reason, "finished")

    def test_rejected_task_does_not_restart(self):
        def tool(**kwargs):
            data = {"task_id": 42, "status": "awaiting_approval" if kwargs["tool_name"] == "edit_file" else "rejected"}
            return {"success": True, "result": {"success": True, "data": data}}
        history, state, _ = self.run_agent([calls_response(tool_call("edit_file"))], tool)
        self.run_agent([], tool, history, state)
        self.assertEqual(state.reason, "finished")
        self.assertIsNone(state.waiting)

    def test_transport_error_no_retry_and_all_calls_resolved(self):
        executed = []
        def tool(**kwargs):
            executed.append(kwargs)
            return {"success": False, "error": "timeout"}
        history, state, _ = self.run_agent([calls_response(tool_call("edit_file"), tool_call("read_file", "c2"))], tool)
        self.assertEqual(len(executed), 1)
        self.assertEqual(state.reason, "error")
        self.assertEqual([m["tool_call_id"] for m in history if m["role"] == "tool"], ["c1", "c2"])

    def test_truncated_call_not_executed(self):
        response = calls_response(tool_call("edit_file"))
        response.finish_reason = "length"
        def tool(**kwargs):
            self.fail("Truncated completion must not execute")
        history, state, _ = self.run_agent([response], tool)
        self.assertEqual(state.reason, "error")
        self.assertEqual(len(history), 1)

    def test_reasoning_only_stops_with_error(self):
        response = Completion({"role": "assistant", "content": ""}, "stop")
        _, state, _ = self.run_agent([response], lambda **kwargs: self.fail("No tool call"))
        self.assertEqual(state.reason, "error")

    def test_long_skill_result_not_truncated(self):
        text = "instruction " * 2000
        def tool(**kwargs):
            return {"success": True, "result": {"content": [{"type": "text", "text": text}]}}
        history, state, seen = self.run_agent([calls_response(tool_call("read_file")), final_response()], tool)
        self.assertIn(text, seen[1]["messages"][-1]["content"])

    def test_repeat_guard_stops_before_fourth_dispatch(self):
        executed = []
        def tool(**kwargs):
            executed.append(kwargs)
            return {"success": True, "result": {"success": False, "error": "bad input"}}
        responses = [calls_response(tool_call("read_file", f"c{i}")) for i in range(4)]
        _, state, _ = self.run_agent(responses, tool)
        self.assertEqual(len(executed), 3)
        self.assertEqual(state.reason, "loop")

    def test_interrupt_keeps_history_protocol_valid(self):
        def tool(**kwargs):
            raise KeyboardInterrupt()
        history, state, _ = self.run_agent([calls_response(tool_call("edit_file"), tool_call("read_file", "c2"))], tool)
        self.assertEqual(state.reason, "stopped")
        self.assertEqual(len([m for m in history if m["role"] == "tool"]), 2)
        self.assertEqual(state.pending, [])

    def test_secret_result_removed_from_history(self):
        def tool(**kwargs):
            return {"success": True, "result": {"content": [{"type": "text", "text": json.dumps({
                "success": True, "secret_result": {"value": "sensitive"}})}]}}
        history, _, _ = self.run_agent([calls_response(tool_call("get_task")), final_response()], tool)
        self.assertNotIn("sensitive", json.dumps(history))


class IntegrationTests(unittest.TestCase):
    def test_both_providers_send_native_tools(self):
        from unittest.mock import Mock, patch
        from services import litellm_client, openrouter_client
        tools, _ = build_native_tools(servers())
        response = Mock(ok=True)
        response.json.return_value = {"choices": [{"message": {
            "tool_calls": [tool_call("read_file")]
        }, "finish_reason": "tool_calls"}], "usage": {"total_tokens": 8}}
        for module, function, model, headers_fn in (
            (litellm_client, litellm_client.complete_litellm, "litellm:test", "get_litellm_headers"),
            (openrouter_client, openrouter_client.complete_openrouter, "openrouter:test", "get_headers"),
        ):
            with self.subTest(model=model), patch.object(module.requests, "post", return_value=response) as post, patch.object(module, headers_fn, return_value={}):
                result = function(model, [{"role": "user", "content": "Test"}], tools)
                payload = post.call_args.kwargs["json"]
                self.assertEqual(payload["model"], "test")
                self.assertEqual(payload["tools"], tools)
                self.assertEqual(payload["tool_choice"], "auto")
                self.assertEqual(result.finish_reason, "tool_calls")
                self.assertEqual(result.usage["total_tokens"], 8)

    def test_provider_router_has_no_fallback(self):
        from unittest.mock import patch
        from services import llm_client
        with patch.object(llm_client, "complete_litellm", side_effect=RuntimeError()), patch.object(llm_client, "complete_openrouter") as private:
            with self.assertRaises(RuntimeError):
                llm_client.ask_completion("litellm:test", [], [])
            private.assert_not_called()

    def test_text_chat_rejects_reasoning_only(self):
        from unittest.mock import patch
        from services import litellm_client
        response = Completion({"role": "assistant", "content": ""}, "stop")
        with patch.object(litellm_client, "complete_litellm", return_value=response):
            with self.assertRaises(ProtocolError):
                litellm_client.ask_litellm("litellm:test", [])

    def test_export_handles_native_tool_calls(self):
        from services.chat_exporter import export_chat_to_markdown
        history = [calls_response(tool_call("read_file")).message,
                   {"role": "tool", "tool_call_id": "c1", "content": "result"}]
        exported = export_chat_to_markdown("test", history)
        self.assertIn("Wywołania narzędzi", exported)
        self.assertIn("tool_call_id: `c1`", exported)

    def test_async_runtime_error_is_not_replayed(self):
        from services.mcp_client import run_async
        dispatched = []
        async def operation():
            dispatched.append(True)
            raise RuntimeError("after dispatch")
        with self.assertRaises(RuntimeError):
            run_async(operation())
        self.assertEqual(len(dispatched), 1)

    def test_interrupt_during_task_check_resolves_history(self):
        state = AgentState(reason="approval", model="litellm:test")
        _, bindings = build_native_tools(servers())
        alias = next(key for key, (_, name) in bindings.items() if name == "get_task")
        state.waiting = {"url": servers()[0]["url"], "task_id": 42, "get_task_alias": alias}
        history = []
        def interrupted(**kwargs):
            raise KeyboardInterrupt()
        run_native(history, "litellm:test", servers(), lambda *args: None, state=state,
                   completion_fn=lambda **kwargs: self.fail("No LLM call"), tool_fn=interrupted)
        self.assertEqual(state.reason, "stopped")
        self.assertEqual(history[-1]["role"], "tool")
        self.assertIsNotNone(state.waiting)


if __name__ == "__main__":
    unittest.main()
