from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manzanares_agent.config import ConfigurationError, Settings, read_env


class ConfigurationTest(unittest.TestCase):
    def test_read_env_rejects_malformed_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("BROKEN_LINE\n", encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                read_env(path)

    def test_external_api_requires_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "API_HOST=0.0.0.0\nLLM_PROVIDER=disabled\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    Settings.load(path)

    def test_relative_database_path_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "DATABASE_PATH=data/test.db\nLLM_PROVIDER=disabled\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.load(path)
            self.assertTrue(settings.database_path.is_absolute())


if __name__ == "__main__":
    unittest.main()
