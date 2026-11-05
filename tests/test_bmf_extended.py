"""Offline tests for Claude Vertex, MSP and all requested BMF models."""
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from services import bmf_client
from services.anthropic_protocol import build_payload, parse_response
from services.agent_protocol import ProtocolError
from services.native_runner import AgentState, run_native
from test_native_agent import servers, tool_call


class ExtendedBMFTests(unittest.TestCase):
    @patch("services.bmf_client.post_completion")
    def test_msp_model_ids_and_payloads(self, post):
        post.return_value = {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}
        with patch.dict(os.environ, {"BMF_API_KEY": "unit-test-not-real"}, clear=True):
            for model_id, payload_model in [("qwen3.8-27b", "Qwen-38-27B"), ("glm-5.2", "zai-glm-52")]:
                result = bmf_client.complete_bmf("bmf:msp:" + model_id, [])
                self.assertEqual(result.message["content"], "OK")
                self.assertTrue(post.call_args.args[0].endswith(f"/providers/bosch/msp/{model_id}/v1/chat/completions"))
                self.assertEqual(post.call_args.kwargs["json"]["model"], payload_model)
        with self.assertRaises(ProtocolError):
            bmf_client.resolve_bmf_model("bmf:msp:unknown")

    def test_all_configured_bmf_models_resolve(self):
        models = json.loads((Path(__file__).resolve().parents[1] / "config/models.json").read_text(encoding="utf-8"))
        bmf = [model for model in models.values() if model.startswith("bmf:")]
        self.assertEqual(len(bmf), 10)
        for model in bmf:
            url, _, _ = bmf_client.resolve_bmf_model(model)
            self.assertTrue(url.startswith("https://"))

    def test_history_conversion_preserves_tools_without_mutation(self):
        call = tool_call("read_file")
        history = [{"role": "system", "content": "rules"}, {"role": "user", "content": "Read"},
                   {"role": "assistant", "content": "", "tool_calls": [call]},
                   {"role": "tool", "tool_call_id": call["id"], "content": '{"partial":true}'},
                   {"role": "user", "content": "Continue"}]
        before = copy.deepcopy(history)
        payload = build_payload(history, [], 1000)
        self.assertEqual(payload["system"], "rules")
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "tool_use")
        self.assertEqual(payload["messages"][2]["content"][0]["tool_use_id"], call["id"])
        self.assertEqual(history, before)

    @patch("services.bmf_client.post_completion")
    def test_claude_transport_and_tool_schema(self, post):
        post.return_value = {"content": [{"type": "text", "text": "OK"}], "stop_reason": "end_turn",
                             "usage": {"input_tokens": 10, "output_tokens": 2}}
        tools = [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]
        with patch.dict(os.environ, {"BMF_API_KEY": "unit-test-not-real"}, clear=True):
            for model in ("claude-sonnet-4-6", "claude-sonnet-5-5"):
                result = bmf_client.complete_bmf("bmf:anthropic:" + model, [{"role": "user", "content": "Hi"}], tools)
                self.assertTrue(post.call_args.args[0].endswith(f"/publishers/anthropic/models/{model}:rawPredict"))
                payload = post.call_args.kwargs["json"]
                self.assertNotIn("model", payload)
                self.assertEqual(payload["anthropic_version"], "vertex-2023-10-16")
                self.assertEqual(payload["tool_choice"], {"type": "auto"})
                self.assertEqual(payload["tools"][0]["input_schema"], {"type": "object"})
                self.assertEqual(result.usage["total_tokens"], 12)

    def test_claude_invalid_history_and_response_are_rejected(self):
        for history in ([{"role": "tool", "tool_call_id": "missing", "content": "x"}],
                        [{"role": "assistant", "content": "Hi"}]):
            with self.assertRaises(ProtocolError):
                build_payload(history, [], 1000)
        for data in ({}, {"content": [{"type": "thinking", "thinking": "private"}], "stop_reason": "end_turn"},
                     {"content": [], "stop_reason": "pause_turn"}):
            with self.assertRaises(ProtocolError):
                parse_response(data)
        with self.assertRaises(ProtocolError):
            bmf_client.resolve_bmf_model("bmf:anthropic:../bad")

    def test_claude_length_maps_to_runner_guard(self):
        result = parse_response({"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"})
        self.assertEqual(result.finish_reason, "length")

    def test_claude_native_agent_tool_round_trip(self):
        call = tool_call("read_file")
        first = parse_response({"content": [{"type": "tool_use", "id": call["id"],
                    "name": call["function"]["name"], "input": {"filepath": "sample"}}], "stop_reason": "tool_use"})
        final = parse_response({"content": [{"type": "text", "text": "Done"}], "stop_reason": "end_turn"})
        responses = iter([first, final])
        payloads, executed = [], []
        def completion(**kwargs):
            payloads.append(build_payload(kwargs["messages"], kwargs["tools"], 1000))
            return next(responses)
        def tool(**kwargs):
            executed.append(kwargs)
            return {"success": True, "result": {"content": "file"}}
        state = AgentState()
        run_native([{"role": "user", "content": "Read"}], "bmf:anthropic:claude-sonnet-4-6", servers(),
                   lambda *args: None, state=state, completion_fn=completion, tool_fn=tool)
        self.assertEqual(state.reason, "finished")
        self.assertEqual(len(executed), 1)
        self.assertEqual(payloads[1]["messages"][-1]["content"][0]["type"], "tool_result")


if __name__ == "__main__":
    unittest.main()
