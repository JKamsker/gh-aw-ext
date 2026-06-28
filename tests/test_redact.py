from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gh_aw_ext.redact import redact_from_environment


class RedactTests(unittest.TestCase):
    def test_redacts_endpoint_host_and_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "artifact.log"
            artifact.write_text(
                "https://secret.example.test/openai/v1 and secret.example.test/openai/v1",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"CODEX_LB_BASE_URL": "https://secret.example.test/openai/v1"}):
                count = redact_from_environment([root], "CODEX_LB_BASE_URL")

            self.assertEqual(count, 1)
            text = artifact.read_text(encoding="utf-8")
            self.assertNotIn("secret.example.test", text)
            self.assertIn("[REDACTED_CODEX_ENDPOINT]", text)


if __name__ == "__main__":
    unittest.main()
