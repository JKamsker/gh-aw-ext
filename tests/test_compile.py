from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gh_aw_ext.compile import selected_lockfiles


class CompileSelectionTests(unittest.TestCase):
    def test_selects_lockfile_for_markdown_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = selected_lockfiles([".github/workflows/status.md"], root)
            self.assertEqual(selected, [root / ".github/workflows/status.lock.yml"])

    def test_selects_named_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = selected_lockfiles(["--engine", "codex", "status"], root)
            self.assertEqual(selected, [root / ".github/workflows/status.lock.yml"])


if __name__ == "__main__":
    unittest.main()
