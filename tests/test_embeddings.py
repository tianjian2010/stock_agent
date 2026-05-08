import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.llm import OpenAICompatibleEmbeddings
from services.vector_store import VectorStoreService


class _FakeEmbeddingsAPI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OpenAICompatibleEmbeddingsTests(unittest.TestCase):
    def test_minimax_native_payload_uses_texts_and_query_type(self) -> None:
        model = OpenAICompatibleEmbeddings(
            model="MiniMax-embedding-01",
            provider="minimax",
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
        )

        with patch("services.llm.requests.post") as post:
            post.return_value = SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {
                    "vectors": [[0.1, 0.2]],
                    "base_resp": {"status_code": 0, "status_msg": "ok"},
                },
                text='{"vectors":[[0.1,0.2]]}',
            )

            result = model.embed_query("hello")

        self.assertEqual(result, [0.1, 0.2])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["texts"], ["hello"])
        self.assertEqual(payload["type"], "query")

    def test_minimax_native_error_is_surfaceable(self) -> None:
        model = OpenAICompatibleEmbeddings(
            model="MiniMax-embedding-01",
            provider="minimax",
            api_key="test-key",
            base_url="https://api.minimaxi.com/v1",
        )

        with patch("services.llm.requests.post") as post:
            post.return_value = SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {
                    "vectors": None,
                    "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
                },
                text='{"vectors":null}',
            )

            with self.assertRaisesRegex(RuntimeError, "insufficient balance"):
                model.embed_query("hello")

    def test_retries_without_dimensions_when_provider_rejects_it(self) -> None:
        model = OpenAICompatibleEmbeddings(
            model="demo-embed",
            dimensions=1536,
            provider="custom",
            api_key="test-key",
            base_url="https://example.com/v1",
        )
        fake_api = _FakeEmbeddingsAPI(
            [
                RuntimeError("unsupported dimensions parameter"),
                SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])]),
            ]
        )
        model.client = SimpleNamespace(embeddings=fake_api)

        result = model.embed_documents(["hello"])

        self.assertEqual(result, [[0.1, 0.2]])
        self.assertEqual(len(fake_api.calls), 2)
        self.assertIn("dimensions", fake_api.calls[0])
        self.assertNotIn("dimensions", fake_api.calls[1])

    def test_raises_clear_error_when_embedding_payload_is_empty(self) -> None:
        model = OpenAICompatibleEmbeddings(
            model="demo-embed",
            provider="custom",
            api_key="test-key",
            base_url="https://example.com/v1",
        )
        model.client = SimpleNamespace(embeddings=_FakeEmbeddingsAPI([SimpleNamespace(data=[])]))

        with self.assertRaisesRegex(RuntimeError, "No embedding data received"):
            model.embed_documents(["hello"])

    def test_ollama_configuration_is_valid_with_base_url(self) -> None:
        model = OpenAICompatibleEmbeddings(
            model="nomic-embed-text",
            provider="ollama",
            api_key="",
            base_url="http://localhost:11434/v1",
        )

        self.assertTrue(model.configured)


class VectorStoreServiceTests(unittest.TestCase):
    def test_enabled_follows_embedding_configuration(self) -> None:
        service = VectorStoreService()

        with patch("services.vector_store.create_embedding_model") as create_model:
            create_model.return_value = SimpleNamespace(configured=True)
            self.assertTrue(service.enabled)

            create_model.return_value = SimpleNamespace(configured=False)
            self.assertFalse(service.enabled)


if __name__ == "__main__":
    unittest.main()
