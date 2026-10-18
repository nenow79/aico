import asyncio
import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
from services.network import NetworkError, post_completion, seconds
from services import mcp_client


def response(code=200, data=None, headers=None):
    result = Mock(ok=code < 400, status_code=code, headers=headers or {})
    result.json.return_value = data or {"choices": []}
    return result


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"LLM_RETRIES": "2", "LLM_CONNECT_TIMEOUT": "10",
                                          "LLM_READ_TIMEOUT": "120"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def send(self):
        return post_completion("https://example.invalid/v1/chat/completions", headers={}, json={})

    @patch("services.network.time.sleep")
    @patch("services.network.requests.post")
    def test_transient_gateway_then_success(self, post, sleep):
        bad, good = response(503), response(data={"ok": True})
        post.side_effect = [bad, good]
        self.assertEqual(self.send(), {"ok": True})
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 120))
        self.assertNotIn("proxies", post.call_args.kwargs)
        bad.close.assert_called_once()
        good.close.assert_called_once()

    @patch("services.network.time.sleep")
    @patch("services.network.requests.post")
    def test_timeout_retries_are_bounded_and_redacted(self, post, sleep):
        post.side_effect = requests.exceptions.ReadTimeout("secret-proxy-password")
        with self.assertRaises(NetworkError) as caught:
            self.send()
        self.assertEqual(post.call_count, 3)
        self.assertNotIn("secret", str(caught.exception))

    @patch("services.network.requests.post")
    def test_permanent_failures_are_not_retried(self, post):
        for code in (400, 401, 403, 407):
            post.reset_mock()
            post.return_value = response(code)
            with self.assertRaises(NetworkError):
                self.send()
            post.assert_called_once()

    @patch("services.network.requests.post")
    def test_tls_and_invalid_json_are_not_retried(self, post):
        post.side_effect = requests.exceptions.SSLError("private url")
        with self.assertRaisesRegex(NetworkError, "TLS"):
            self.send()
        post.assert_called_once()
        post.reset_mock()
        post.side_effect = None
        post.return_value = response()
        post.return_value.json.side_effect = ValueError("private body")
        with self.assertRaisesRegex(NetworkError, "JSON"):
            self.send()
        post.assert_called_once()

    @patch("services.network.time.sleep")
    @patch("services.network.requests.post")
    def test_retry_after(self, post, sleep):
        post.side_effect = [response(429, headers={"Retry-After": "5"}), response()]
        self.send()
        sleep.assert_called_once_with(5)
        post.reset_mock()
        post.side_effect = None
        post.return_value = response(429, headers={"Retry-After": "300"})
        with self.assertRaises(NetworkError):
            self.send()
        post.assert_called_once()

    @patch("services.network.requests.post")
    def test_provider_timeout_defaults_and_environment_override(self, post):
        post.return_value = response()
        with patch.dict(os.environ, {}, clear=True):
            post_completion("https://example.invalid", headers={}, json={})
            self.assertEqual(post.call_args.kwargs["timeout"], (10, 120))
            post_completion("https://example.invalid", headers={}, json={},
                            connect_timeout_default=120)
            self.assertEqual(post.call_args.kwargs["timeout"], (120, 120))
            with patch.dict(os.environ, {"LLM_CONNECT_TIMEOUT": "45"}):
                post_completion("https://example.invalid", headers={}, json={},
                                connect_timeout_default=120)
                self.assertEqual(post.call_args.kwargs["timeout"], (45, 120))

    @patch("services.network.time.sleep")
    @patch("services.network.requests.post")
    def test_explicit_proxy_is_copied_for_each_retry(self, post, sleep):
        original = {"https": "http://proxy.invalid:8080"}
        seen = []
        def send(*args, **kwargs):
            seen.append(dict(kwargs["proxies"]))
            kwargs["proxies"]["http"] = "http://other.invalid:8080"
            return response(503 if len(seen) == 1 else 200)
        post.side_effect = send
        post_completion("https://example.invalid", headers={}, json={}, proxies=original)
        self.assertEqual(seen, [original, original])
        self.assertEqual(original, {"https": "http://proxy.invalid:8080"})

    @patch("services.network.requests.sessions.Session.send")
    def test_litellm_proxy_selection_and_ca_without_network(self, send):
        # Exercise real Requests preparation and environment merging, not requests.post.
        # Stub only the final send: no DNS, sockets, API keys or real provider calls.
        from services import litellm_client
        envelope = {"choices": [{"message": {"role": "assistant", "content": "OK"},
                                 "finish_reason": "stop"}]}
        cases = [
            ({}, {}, True),
            ({"HTTPS_PROXY": "", "HTTP_PROXY": "",
              "ALL_PROXY": "http://all.invalid:8080"},
             {"all": "http://all.invalid:8080"}, True),
            ({"HTTPS_PROXY": "http://proxy.invalid:8080", "NO_PROXY": "example.invalid"},
             {"https": "http://proxy.invalid:8080"}, True),
            ({"https_proxy": "http://lower.invalid:8080"},
             {"https": "http://lower.invalid:8080"}, True),
            ({"https_proxy": "http://lower.invalid:8080", "NO_PROXY": "example.invalid"},
             {}, True),
            ({"REQUESTS_CA_BUNDLE": "test-company-ca.pem"}, {}, "test-company-ca.pem"),
        ]
        for environment, expected_proxies, expected_verify in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), \
                    patch.object(litellm_client, "LITELLM_URL", "https://example.invalid/v1/chat/completions"), \
                    patch.object(litellm_client, "get_litellm_headers", return_value={}):
                send.return_value = response(data=envelope)
                result = litellm_client.complete_litellm("litellm:test-model", [])
                self.assertEqual(result.message["content"], "OK")
                actual = send.call_args.kwargs
                selected = {key: value for key, value in actual["proxies"].items()
                            if key != "no"}
                self.assertEqual(selected, expected_proxies)
                self.assertEqual(actual["verify"], expected_verify)
                self.assertEqual(actual["timeout"], (120, 120))
                send.return_value.close.assert_called_once()

    @patch("services.network.requests.sessions.Session.send")
    def test_default_transport_keeps_no_proxy_without_network(self, send):
        send.return_value = response()
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.invalid:8080",
                                     "NO_PROXY": "example.invalid"}, clear=True):
            post_completion("https://example.invalid", headers={}, json={})
        self.assertEqual(send.call_args.kwargs["proxies"], {})
        self.assertIs(send.call_args.kwargs["verify"], True)
        self.assertEqual(send.call_args.kwargs["timeout"], (10, 120))

    def test_invalid_timeout_cannot_disable_limits(self):
        for value in ("0", "-1", "nan", "inf", "oops"):
            with patch.dict(os.environ, {"MCP_CALL_TIMEOUT": value}):
                with self.assertRaises(NetworkError):
                    seconds("MCP_CALL_TIMEOUT", 60)

    def test_mcp_timeout_cancels_once_and_closes_client(self):
        calls, closed = [], []
        class Client:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                closed.append(True)
            async def call_tool(self, *args):
                calls.append(args)
                await asyncio.sleep(10)
        with patch.object(mcp_client, "Client", Client), patch.dict(os.environ, {"MCP_CALL_TIMEOUT": "0.02"}):
            result = mcp_client.call_mcp_tool("http://localhost/mcp", "edit_file", "{}")
        self.assertFalse(result["success"])
        self.assertIn("limit czasu", result["error"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(closed, [True])

    def test_discovery_timeout_includes_handshake(self):
        class Client:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                await asyncio.sleep(10)
            async def __aexit__(self, *args):
                pass
        with patch.object(mcp_client, "Client", Client), patch.dict(os.environ, {"MCP_DISCOVERY_TIMEOUT": "0.02"}):
            result = mcp_client.list_mcp_tools("http://localhost/mcp")
        self.assertFalse(result["success"])
        self.assertIn("limit czasu", result["error"])

    def test_default_token_counter_never_imports_network_tokenizer(self):
        from services.token_counter import count_chat_tokens
        with patch.dict(os.environ, {"AICO_EXACT_TOKENS": "0"}), patch.dict(sys.modules, {"tiktoken": None}):
            self.assertGreater(count_chat_tokens([{"role": "user", "content": "Sprawdź plik."}]), 0)

    def test_disabled_mcp_servers_are_skipped(self):
        from services.mcp_runner import load_mcp_servers
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "servers.json"
            path.write_text('[null, {"name":"old","url":"http://localhost:8100/mcp","enabled":false},'
                            '{"name":"sklr","url":"http://localhost:8101/mcp"}]', encoding="utf-8")
            self.assertEqual(load_mcp_servers(path), [{"name": "sklr", "url": "http://localhost:8101/mcp"}])

    def test_malformed_api_envelope_is_protocol_error(self):
        from services.agent_protocol import ProtocolError, parse_completion
        for data in ([], None, {"choices": [None]}):
            with self.assertRaises(ProtocolError):
                parse_completion(data)

    @patch("services.network.time.sleep", side_effect=KeyboardInterrupt)
    @patch("services.network.requests.post")
    def test_ctrl_c_during_backoff_stops_retries(self, post, sleep):
        post.return_value = response(503)
        with self.assertRaises(KeyboardInterrupt):
            self.send()
        post.assert_called_once()
