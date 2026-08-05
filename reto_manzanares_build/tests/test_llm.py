from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from manzanares_agent.llm import synthesize_with_ollama
from tests.common import test_settings


class FakeResponse:
    headers = {"Content-Type": "application/json"}

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _: int) -> bytes:
        return json.dumps(
            {
                "response": "Respuesta local",
                "prompt_eval_count": 120,
                "eval_count": 60,
                "eval_duration": 2_000_000_000,
                "total_duration": 3_500_000_000,
            }
        ).encode()


class LlmMetricsTest(unittest.TestCase):
    def test_ollama_metrics_are_calculated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = test_settings(Path(directory) / "test.db")
            settings = replace(settings, llm_provider="ollama")
            with patch(
                "urllib.request.urlopen",
                return_value=FakeResponse(),
            ):
                result = synthesize_with_ollama("hola", settings)
        self.assertTrue(result.used)
        self.assertEqual(result.prompt_tokens, 120)
        self.assertEqual(result.output_tokens, 60)
        self.assertEqual(result.tokens_per_second, 30.0)
        self.assertEqual(result.total_duration_seconds, 3.5)


if __name__ == "__main__":
    unittest.main()
