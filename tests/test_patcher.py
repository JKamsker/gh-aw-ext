from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gh_aw_ext.patcher import PatchOptions, patch_lockfile


SAMPLE_LOCKFILE = """# gh-aw-manifest: {"version":1,"secrets":["CODEX_API_KEY"]}
# Secrets used:
#   - CODEX_API_KEY
on:
  schedule:
    - cron: "41 14 * * *"
jobs:
  agent:
    steps:
      - name: Execute Codex CLI
        run: |
          cat > "/tmp/gh-aw/mcp-config/config.toml" << GH_AW_CODEX_SHELL_POLICY_EOF
          model_provider = "openai-proxy"
          GH_AW_CODEX_SHELL_POLICY_EOF
          printf '%s\\n' "{\\"$schema\\":\\"https://example.test/awf-config.schema.json\\"}" > "${RUNNER_TEMP}/gh-aw/awf-config.json"
          sudo -E awf --config "${RUNNER_TEMP}/gh-aw/awf-config.json" --env-all --exclude-env CODEX_API_KEY -- /bin/bash -c 'node codex_harness.cjs'
        env:
          CODEX_API_KEY: ${{ secrets.CODEX_API_KEY || secrets.OPENAI_API_KEY }}
      - env:
          CODEX_LB_BASE_URL: ${{ secrets.CODEX_LB_BASE_URL }}
        if: always()
        name: Redact Codex endpoint artifacts
        run: python3 .github/scripts/redact_codex_endpoint_artifacts.py
      - name: Upload agent artifacts
        if: always()
        uses: actions/upload-artifact@v4
      - name: Upload threat detection log
        if: always()
        uses: actions/upload-artifact@v4
"""


class PatcherTests(unittest.TestCase):
    def test_patch_lockfile_injects_endpoint_and_inline_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.lock.yml"
            path.write_text(SAMPLE_LOCKFILE, encoding="utf-8")

            result = patch_lockfile(path)

            self.assertIsNotNone(result)
            self.assertTrue(result.changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn("Patch gh-aw OpenAI proxy target from CODEX_LB_BASE_URL", text)
            self.assertIn("--exclude-env CODEX_LB_BASE_URL", text)
            self.assertIn("CODEX_LB_BASE_URL: ${{ secrets.CODEX_LB_BASE_URL }}", text)
            self.assertIn('model_reasoning_effort = "high"', text)
            self.assertIn("python3 - <<'PY'", text)
            self.assertNotIn("redact_codex_endpoint_artifacts.py", text)
            self.assertIn("Redact Codex endpoint detection artifacts", text)
            self.assertIn('- cron: "41 14 * * *"', text)

            manifest_line = text.splitlines()[0].removeprefix("# gh-aw-manifest: ")
            manifest = json.loads(manifest_line)
            self.assertIn("CODEX_LB_BASE_URL", manifest["secrets"])

    def test_patch_lockfile_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.lock.yml"
            path.write_text(SAMPLE_LOCKFILE, encoding="utf-8")

            first = patch_lockfile(path)
            second = patch_lockfile(path)

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)

    def test_custom_secret_and_disabled_reasoning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.lock.yml"
            path.write_text(SAMPLE_LOCKFILE, encoding="utf-8")

            patch_lockfile(path, PatchOptions(secret_name="PRIVATE_OPENAI_BASE_URL", reasoning_effort=None))

            text = path.read_text(encoding="utf-8")
            self.assertIn("PRIVATE_OPENAI_BASE_URL: ${{ secrets.PRIVATE_OPENAI_BASE_URL }}", text)
            self.assertIn("--exclude-env PRIVATE_OPENAI_BASE_URL", text)
            self.assertNotIn("model_reasoning_effort", text)


if __name__ == "__main__":
    unittest.main()
