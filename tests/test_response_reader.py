import asyncio
import copy
import unittest

from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from services.response_reader import build_reader, last_assistant_response


class ResponseReaderTests(unittest.TestCase):
    def test_selects_latest_visible_assistant_without_mutating_history(self):
        messages = [
            {"role": "assistant", "content": "Starsza odpowiedź"},
            {"role": "assistant", "content": "# Odpowiedź\n\n```py\nprint('ą')\n```"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "Wynik narzędzia"},
            {"role": "user", "content": "Pytanie"},
        ]
        before = copy.deepcopy(messages)
        self.assertEqual(last_assistant_response(messages), messages[1]["content"])
        self.assertEqual(messages, before)
        self.assertIsNone(last_assistant_response([]))
        self.assertIsNone(last_assistant_response([{"role": "assistant", "content": "  "}]))


class ReaderInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_readonly_idle_and_exit(self):
        content = "\n".join(f"Linia {i}: żółć " + "tekst " * 15 for i in range(150))
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            app = build_reader(content)
            task = asyncio.create_task(app.run_async())

            async def send(keys):
                handled = asyncio.Event()
                def after_key(sender):
                    handled.set()
                app.key_processor.after_key_press += after_key
                try:
                    pipe.send_text(keys)
                    await asyncio.wait_for(handled.wait(), 2)
                finally:
                    app.key_processor.after_key_press -= after_key

            try:
                await asyncio.sleep(0.05)
                buf = app.current_buffer
                self.assertEqual(buf.cursor_position, 0)
                await send("\x1b[6~")  # Page Down
                self.assertGreater(buf.cursor_position, 0)
                await send("\x1b[F")  # End
                self.assertEqual(buf.cursor_position, len(content))
                await send("\x1b[5~")  # Page Up
                self.assertLess(buf.cursor_position, len(content))
                position = buf.cursor_position
                await asyncio.sleep(0.1)
                self.assertEqual(buf.cursor_position, position)
                await send("\x1b[H")  # Home
                self.assertEqual(buf.cursor_position, 0)
                await send("x")
                self.assertEqual(buf.text, content)
                await send("q")
                await asyncio.wait_for(task, 2)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_escape_exits(self):
        with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
            app = build_reader("Odpowiedź")
            task = asyncio.create_task(app.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text("\x1b")
                await asyncio.wait_for(task, 2)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
