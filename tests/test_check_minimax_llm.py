import os
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

from openai import APIConnectionError, APITimeoutError, AuthenticationError

from scripts.check_minimax_llm import run_check


class CheckMiniMaxLlmScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.args = Namespace(
            api_key="",
            base_url="",
            model="",
            timeout=8.0,
            prompt="ping",
            stream=False,
        )

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch.dict(os.environ, {}, clear=True)
    def test_run_check_reports_missing_api_key(self, _load_dotenv) -> None:
        exit_code, result = run_check(self.args)

        self.assertEqual(exit_code, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "missing_api_key")

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch("scripts.check_minimax_llm.OpenAI")
    @patch.dict(
        os.environ,
        {
            "MINIMAX_API_KEY": "sk-test-1234567890",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
            "MINIMAX_MODEL": "MiniMax-M2.7",
        },
        clear=True,
    )
    def test_run_check_reports_success(self, openai_cls, _load_dotenv) -> None:
        client = openai_cls.return_value
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))]
        )

        exit_code, result = run_check(self.args)

        self.assertEqual(exit_code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["category"], "ok")
        self.assertEqual(result["response_preview"], "pong")
        self.assertFalse(result["stream"])

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch("scripts.check_minimax_llm.OpenAI")
    @patch.dict(
        os.environ,
        {
            "MINIMAX_API_KEY": "sk-test-1234567890",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
            "MINIMAX_MODEL": "MiniMax-M2.7",
        },
        clear=True,
    )
    def test_run_check_reports_stream_success(self, openai_cls, _load_dotenv) -> None:
        stream_args = Namespace(
            api_key="",
            base_url="",
            model="",
            timeout=8.0,
            prompt="ping",
            stream=True,
        )
        client = openai_cls.return_value
        client.chat.completions.create.return_value = iter(
            [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="po"))]
                ),
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content="ng"))]
                ),
            ]
        )

        exit_code, result = run_check(stream_args)

        self.assertEqual(exit_code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["response_preview"], "pong")
        self.assertTrue(result["stream"])

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch("scripts.check_minimax_llm.OpenAI")
    @patch.dict(
        os.environ,
        {
            "MINIMAX_API_KEY": "sk-test-1234567890",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
            "MINIMAX_MODEL": "MiniMax-M2.7",
        },
        clear=True,
    )
    def test_run_check_reports_invalid_api_key(self, openai_cls, _load_dotenv) -> None:
        client = openai_cls.return_value
        client.chat.completions.create.side_effect = AuthenticationError(
            "invalid api key",
            response=SimpleNamespace(request=None, status_code=401, headers={}),
            body={},
        )

        exit_code, result = run_check(self.args)

        self.assertEqual(exit_code, 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "invalid_api_key")

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch("scripts.check_minimax_llm.OpenAI")
    @patch.dict(
        os.environ,
        {
            "MINIMAX_API_KEY": "sk-test-1234567890",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
            "MINIMAX_MODEL": "MiniMax-M2.7",
        },
        clear=True,
    )
    def test_run_check_reports_connection_error(self, openai_cls, _load_dotenv) -> None:
        client = openai_cls.return_value
        client.chat.completions.create.side_effect = APIConnectionError(request=None)

        exit_code, result = run_check(self.args)

        self.assertEqual(exit_code, 5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "connection_error")

    @patch("scripts.check_minimax_llm._load_dotenv")
    @patch("scripts.check_minimax_llm.OpenAI")
    @patch.dict(
        os.environ,
        {
            "MINIMAX_API_KEY": "sk-test-1234567890",
            "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
            "MINIMAX_MODEL": "MiniMax-M2.7",
        },
        clear=True,
    )
    def test_run_check_reports_timeout(self, openai_cls, _load_dotenv) -> None:
        client = openai_cls.return_value
        client.chat.completions.create.side_effect = APITimeoutError(request=None)

        exit_code, result = run_check(self.args)

        self.assertEqual(exit_code, 4)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "timeout")


if __name__ == "__main__":
    unittest.main()
