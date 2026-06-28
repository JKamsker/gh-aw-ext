from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .patcher import PatchOptions, patch_lockfile


VALUE_FLAGS = {
    "--dir",
    "-d",
    "--engine",
    "-e",
    "--logical-repo",
    "--schedule-seed",
}


def find_repo_root(start: Path | None = None) -> Path:
    cwd = start or Path.cwd()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        return Path(result.stdout.strip())
    return cwd


def selected_lockfiles(args: list[str], repo_root: Path) -> list[Path]:
    if "--no-emit" in args:
        return []

    selected: list[Path] = []
    skip_next = False
    workflow_dir = repo_root / ".github" / "workflows"
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in VALUE_FLAGS:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue

        path = Path(arg)
        if path.suffix == ".md":
            md_path = path if path.is_absolute() else repo_root / path
            selected.append(md_path.with_suffix(".lock.yml"))
        elif arg.endswith(".lock.yml"):
            selected.append(path if path.is_absolute() else repo_root / path)
        elif "/" not in arg and "\\" not in arg:
            selected.append(workflow_dir / f"{arg}.lock.yml")

    if selected:
        return selected
    return sorted(workflow_dir.glob("*.lock.yml"))


def compile_and_patch(args: list[str], options: PatchOptions) -> int:
    repo_root = find_repo_root()
    subprocess.run(["gh", "aw", "compile", *args], cwd=repo_root, check=True)

    lockfiles = selected_lockfiles(args, repo_root)
    if not lockfiles:
        return 0

    patch_files(lockfiles, options)
    return 0


def patch_files(paths: list[Path], options: PatchOptions) -> list[Path]:
    changed: list[Path] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        result = patch_lockfile(path, options)
        if result is None:
            print(f"skipped non-Codex lockfile: {path}")
            continue
        if result.changed:
            changed.append(path)
            print(
                "patched "
                f"{path}: snippets={result.endpoint_snippets}, "
                f"awf_commands={result.awf_commands}, env_blocks={result.env_blocks}, "
                f"reasoning_blocks={result.reasoning_blocks}, "
                f"redaction_steps={result.redaction_steps}"
            )
        else:
            print(f"no gh-aw Codex lockfile changes needed: {path}")
    return changed


def run_module() -> int:
    return compile_and_patch(sys.argv[1:], PatchOptions())


if __name__ == "__main__":
    raise SystemExit(run_module())
