"""Offline provider routing, BMF payloads and session isolation. No real API calls."""
import copy
import os
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from services import bmf_client, llm_client
from services.agent_protocol import ProtocolError, parse_completion
from services.network import NetworkError
from services.provider_session import ProviderSession


def envelope(content="OK", calls=None, reason="stop"):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = calls
    return {"choices": [{"message": message, "finish_reason": reason}],
            "usage": {"total_tokens": 7}}


class ProviderTests(unittest.TestCase):
    def test_labels_and_legacy_models(self):
        for model, provider in [("openai/test", "openrouter"), ("openrouter:openai/test", "openrouter"),
                                ("litellm:test", "litellm"), ("bmf:azure:test", "bmf")]:
            self.assertEqual(llm_client.get_model_provider(model), provider)
            self.assertEqual(llm_client.get_provider_label(model), llm_client.PROVIDER_LABELS[provider])
        with self.assertRaises(ProtocolError):
            llm_client.get_model_provider("unknown:test")

    def test_provider_is_immutable_and_models_are_filtered(self):
        models = {"OR": "openai/test", "Lite": "litellm:test", "BMF": "bmf:azure:test"}
        original = dict(models)
        for provider, label in [("openrouter", "OR"), ("litellm", "Lite"), ("bmf", "BMF")]:
            session = ProviderSession(provider)
            self.assertEqual(session.models(models), {label: models[label]})
            session.validate_model(models[label])
            with self.assertRaises(FrozenInstanceError):
                session.provider = "other"
            for other in models.keys() - {label}:
                with self.assertRaises(ValueError):
                    session.validate_model(models[other])
        self.assertEqual(models, original)

    def test_bmf_dispatch_never_falls_back(self):
        with patch.object(llm_client, "complete_bmf", side_effect=NetworkError("LLM HTTP 401")), \
                patch.object(llm_client, "complete_openrouter") as router, \
                patch.object(llm_client, "complete_litellm") as lite:
            with self.assertRaises(NetworkError):
                llm_client.ask_completion("bmf:azure:test", [])
            router.assert_not_called()
            lite.assert_not_called()
        with patch.object(llm_client, "ask_bmf", return_value="OK") as bmf:
            self.assertEqual(llm_client.ask_llm("bmf:azure:test", []), "OK")
            bmf.assert_called_once()

    def test_bmf_key_check_and_message(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(llm_client.has_llm_api_key("bmf:azure:test"))
            self.assertIn("BMF_API_KEY", llm_client.get_missing_api_key_message("bmf:azure:test"))
            with self.assertRaises(NetworkError):
                bmf_client.get_bmf_headers()
        with patch.dict(os.environ, {"BMF_API_KEY": "unit-test-not-a-real-key"}, clear=True):
            self.assertTrue(llm_client.has_llm_api_key("bmf:azure:test"))


class BMFTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"BMF_API_KEY": "unit-test-not-a-real-key"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @patch("services.bmf_client.post_completion")
    def test_azure_payload_endpoint_and_native_tools(self, post):
        call = {"id": "c1", "type": "function", "function": {"name": "read", "arguments": "{}"}}
        post.return_value = envelope(None, [call], "tool_calls")
        history = [{"role": "user", "content": "hello"}]
        original = copy.deepcopy(history)
        tools = [{"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}]
        result = bmf_client.complete_bmf("bmf:azure:gpt-5.4-mini-2026-03-17", history, tools)
        url = post.call_args.args[0]
        self.assertIn("/openai/deployments/gpt-5.4-mini-2026-03-17/chat/completions?api-version=2025-04-01-preview", url)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer unit-test-not-a-real-key")
        self.assertEqual(kwargs["json"]["model"], "gpt-5.4-mini-2026-03-17")
        self.assertEqual(kwargs["json"]["max_completion_tokens"], 16000)
        self.assertNotIn("max_tokens", kwargs["json"])
        self.assertEqual(kwargs["json"]["tools"], tools)
        self.assertEqual(kwargs["json"]["tool_choice"], "auto")
        self.assertEqual(kwargs["connect_timeout_default"], 120)
        self.assertNotIn("proxies", kwargs)
        self.assertEqual(result.message["tool_calls"], [call])
        self.assertEqual(result.usage["total_tokens"], 7)
        self.assertEqual(history, original)

    @patch("services.bmf_client.post_completion")
    def test_vertex_url_and_publisher_prefix(self, post):
        post.return_value = envelope()
        bmf_client.complete_bmf("bmf:vertex:google/gemini-3.1-flash-lite", [])
        self.assertTrue(post.call_args.args[0].endswith("/google/v1/endpoints/gemini-3.1-flash-lite/openapi/chat/completions"))
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "google/gemini-3.1-flash-lite")
        self.assertEqual(payload["max_tokens"], 16000)
        self.assertNotIn("max_completion_tokens", payload)
        self.assertNotIn("tools", payload)

    @patch("services.bmf_client.post_completion")
    def test_invalid_configuration_never_dispatches(self, post):
        for model in ("bmf:test", "bmf:azure:../secret", "bmf:vertex:anthropic/claude", "bmf:vertex:google/../bad"):
            with self.assertRaises(ProtocolError):
                bmf_client.complete_bmf(model, [])
        for url in ("http://example.invalid", "https://user:password@example.invalid/api", "https://example.invalid/api?x=1"):
            with patch.dict(os.environ, {"BMF_BASE_URL": url}), self.assertRaises(NetworkError):
                bmf_client.complete_bmf("bmf:azure:test", [])
        with patch.dict(os.environ, {"BMF_API_VERSION": "bad&extra=1"}), self.assertRaises(ProtocolError):
            bmf_client.complete_bmf("bmf:azure:test", [])
        post.assert_not_called()

    @patch("services.bmf_client.post_completion")
    def test_optional_limit_and_api_version_override(self, post):
        post.return_value = envelope()
        for raw in ("", "bad", "0", "-1"):
            with patch.dict(os.environ, {"LLM_MAX_OUTPUT_TOKENS": raw, "BMF_API_VERSION": "2025-01-01-preview"}):
                bmf_client.complete_bmf("bmf:azure:test", [])
                self.assertNotIn("max_completion_tokens", post.call_args.kwargs["json"])
                self.assertTrue(post.call_args.args[0].endswith("api-version=2025-01-01-preview"))

    @patch("services.bmf_client.complete_bmf")
    def test_chat_rejects_truncation_tools_and_empty_content(self, complete):
        for data in (envelope("", reason="stop"), envelope("partial", reason="length"),
                     envelope("blocked", reason="content_filter"),
                     envelope(None, [{"id": "1", "type": "function", "function": {"name": "read", "arguments": "{}"}}], "tool_calls")):
            complete.return_value = parse_completion(data)
            with self.assertRaises(ProtocolError):
                bmf_client.ask_bmf("bmf:azure:test", [])
        complete.return_value = parse_completion(envelope())
        self.assertEqual(bmf_client.ask_bmf("bmf:azure:test", []), "OK")


class CLISessionTests(unittest.TestCase):
    def test_clear_and_model_change_keep_startup_provider(self):
        import aico
        models = {"OR": "openai/test", "Lite": "litellm:test", "BMF": "bmf:azure:test"}
        prompts = Mock()
        prompts.prompt.side_effect = ["/clear", "/model", "/exit"]
        with patch.object(aico, "load_models", return_value=models), \
                patch.object(aico, "pick_provider", return_value=ProviderSession("litellm")) as pick_provider, \
                patch.object(aico, "pick_model", return_value=("Lite", "litellm:test")) as pick_model, \
                patch.object(aico, "has_llm_api_key", return_value=True), \
                patch.object(aico, "PromptSession", return_value=prompts), \
                patch.object(aico, "console", Mock()):
            aico.main()
        pick_provider.assert_called_once_with(models)
        self.assertEqual(pick_model.call_count, 2)
        for call in pick_model.call_args_list:
            self.assertEqual(call.args[0], {"Lite": "litellm:test"})

    def test_model_filter_rejects_cross_provider_candidate(self):
        session = ProviderSession("bmf")
        with self.assertRaises(ValueError):
            session.validate_model("litellm:test")


if __name__ == "__main__":
    unittest.main()
