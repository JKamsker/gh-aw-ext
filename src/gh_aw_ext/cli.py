from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compile import compile_and_patch, patch_files
from .patcher import PatchOptions
from .redact import redact_from_environment
from .repair import DEFAULT_VALIDATION_STEP_NAMES, run_from_environment


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: gh-aw-ext <compile|patch-lockfiles|redact-artifacts|dispatch-repair> ...", file=sys.stderr)
        return 2

    command = args.pop(0)
    if command == "compile":
        return compile_command(args)
    if command == "patch-lockfiles":
        return patch_lockfiles_command(args)
    if command == "redact-artifacts":
        return redact_artifacts_command(args)
    if command == "dispatch-repair":
        return dispatch_repair_command(args)

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


def add_patch_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--secret-name", default="CODEX_LB_BASE_URL")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--no-reasoning-effort", action="store_true")
    parser.add_argument("--no-agent-redaction", action="store_true")
    parser.add_argument("--no-detection-redaction", action="store_true")
    parser.add_argument("--no-models-preflight", action="store_true")


def build_patch_options(namespace: argparse.Namespace) -> PatchOptions:
    return PatchOptions(
        secret_name=namespace.secret_name,
        reasoning_effort=None if namespace.no_reasoning_effort else namespace.reasoning_effort,
        agent_redaction=not namespace.no_agent_redaction,
        detection_redaction=not namespace.no_detection_redaction,
        models_preflight=not namespace.no_models_preflight,
    )


def compile_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gh-aw-ext compile")
    add_patch_options(parser)
    namespace, gh_aw_args = parser.parse_known_args(argv)
    return compile_and_patch(gh_aw_args, build_patch_options(namespace))


def patch_lockfiles_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gh-aw-ext patch-lockfiles")
    add_patch_options(parser)
    parser.add_argument("paths", nargs="*")
    namespace = parser.parse_args(argv)
    paths = [Path(path) for path in namespace.paths] or sorted(Path(".github/workflows").glob("*.lock.yml"))
    patch_files(paths, build_patch_options(namespace))
    return 0


def redact_artifacts_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gh-aw-ext redact-artifacts")
    parser.add_argument("--secret-name", default="CODEX_LB_BASE_URL")
    parser.add_argument("paths", nargs="*")
    namespace = parser.parse_args(argv)
    count = redact_from_environment([Path(path) for path in namespace.paths], namespace.secret_name)
    print(f"Redacted Codex endpoint artifacts: {count} file(s)")
    return 0


def dispatch_repair_command(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gh-aw-ext dispatch-repair")
    parser.add_argument("--source-run-id")
    parser.add_argument("--repo")
    parser.add_argument("--default-branch")
    parser.add_argument("--workflow-file")
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--job-name", default="agent")
    parser.add_argument("--validation-step", action="append", default=[])
    namespace = parser.parse_args(argv)
    validation_steps = set(namespace.validation_step or DEFAULT_VALIDATION_STEP_NAMES)
    return run_from_environment(
        source_run_id=namespace.source_run_id,
        repo=namespace.repo,
        default_branch=namespace.default_branch,
        workflow_file=namespace.workflow_file,
        max_attempts=namespace.max_attempts,
        dry_run=namespace.dry_run or None,
        validation_steps=validation_steps,
        job_name=namespace.job_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
