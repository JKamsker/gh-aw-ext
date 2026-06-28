from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .snippets import endpoint_patch_lines, redaction_step_lines


CONFIG_WRITE = '> "${RUNNER_TEMP}/gh-aw/awf-config.json"'
AWF_SCHEMA = "awf-config.schema.json"
AWF_COMMAND = "sudo -E awf --config"
PATCH_MARKER_PREFIX = "Patch gh-aw OpenAI proxy target from"
CODEX_CONFIG_HEREDOC = 'cat > "/tmp/gh-aw/mcp-config/config.toml" << GH_AW_CODEX_SHELL_POLICY_'
AGENT_REDACTION_STEP = "Redact Codex endpoint artifacts"
DETECTION_REDACTION_STEP = "Redact Codex endpoint detection artifacts"
AGENT_UPLOAD_STEP = "Upload agent artifacts"
DETECTION_UPLOAD_STEP = "Upload threat detection log"


@dataclass(frozen=True)
class PatchOptions:
    secret_name: str = "CODEX_LB_BASE_URL"
    reasoning_effort: str | None = "high"
    agent_redaction: bool = True
    detection_redaction: bool = True
    models_preflight: bool = True

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", self.secret_name):
            raise ValueError("secret_name must be an uppercase environment variable name")
        if self.reasoning_effort and not re.fullmatch(r"[A-Za-z0-9_-]+", self.reasoning_effort):
            raise ValueError("reasoning_effort must be a simple config token")


@dataclass(frozen=True)
class PatchResult:
    path: Path
    changed: bool
    endpoint_snippets: int
    awf_commands: int
    env_blocks: int
    reasoning_blocks: int
    redaction_steps: int


def patch_lockfile(path: Path, options: PatchOptions = PatchOptions()) -> PatchResult | None:
    options.validate()
    text = path.read_text(encoding="utf-8")
    if "codex_harness.cjs" not in text:
        return None

    lines = text.splitlines()
    lines, manifest_changed = ensure_manifest_secret(lines, options.secret_name)
    lines, endpoint_replace_count = replace_runtime_patches(
        lines,
        options.secret_name,
        options.models_preflight,
    )
    lines, endpoint_count = insert_runtime_patch(lines, options.secret_name, options.models_preflight)
    lines, awf_count = patch_awf_commands(lines, options.secret_name)
    lines, env_count = insert_endpoint_env(lines, options.secret_name)
    lines, reasoning_count = insert_codex_reasoning_effort(lines, options.reasoning_effort)
    lines, redaction_count = ensure_redaction_steps(lines, options)
    lines = [line.rstrip() for line in lines]
    while lines and lines[-1] == "":
        lines.pop()

    patched_text = "\n".join(lines) + "\n"
    validate_patched_text(patched_text, path, options)
    changed = patched_text != text
    if changed:
        path.write_text(patched_text, encoding="utf-8")

    return PatchResult(
        path=path,
        changed=changed,
        endpoint_snippets=endpoint_count + endpoint_replace_count,
        awf_commands=awf_count,
        env_blocks=env_count,
        reasoning_blocks=reasoning_count,
        redaction_steps=redaction_count + int(manifest_changed),
    )


def ensure_manifest_secret(lines: list[str], secret_name: str) -> tuple[list[str], bool]:
    changed = False
    patched = list(lines)

    for index, line in enumerate(patched):
        prefix = "# gh-aw-manifest: "
        if not line.startswith(prefix):
            continue
        manifest = json.loads(line[len(prefix) :])
        secrets = manifest.setdefault("secrets", [])
        if secret_name not in secrets:
            secrets.append(secret_name)
            manifest["secrets"] = sorted(secrets)
            patched[index] = prefix + json.dumps(manifest, separators=(",", ":"), ensure_ascii=False)
            changed = True
        break

    for index, line in enumerate(patched):
        if line != "# Secrets used:":
            continue
        end = index + 1
        existing: list[str] = []
        while end < len(patched) and patched[end].startswith("#   - "):
            existing.append(patched[end][6:])
            end += 1
        if secret_name not in existing:
            existing.append(secret_name)
            replacement = [f"#   - {secret}" for secret in sorted(existing)]
            patched[index + 1 : end] = replacement
            changed = True
        break

    return patched, changed


def replace_runtime_patches(lines: list[str], secret_name: str, models_preflight: bool) -> tuple[list[str], int]:
    patched: list[str] = []
    replacements = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if PATCH_MARKER_PREFIX not in line:
            patched.append(line)
            index += 1
            continue

        indent = line[: len(line) - len(line.lstrip())]
        patched.extend(
            f"{indent}{snippet_line}" if snippet_line else ""
            for snippet_line in endpoint_patch_lines(secret_name, models_preflight=models_preflight)
        )
        replacements += 1
        index += 1
        while index < len(lines):
            if lines[index].strip() == "PY":
                index += 1
                break
            index += 1

    return patched, replacements


def insert_runtime_patch(lines: list[str], secret_name: str, models_preflight: bool) -> tuple[list[str], int]:
    patched: list[str] = []
    insertions = 0
    for index, line in enumerate(lines):
        patched.append(line)
        if CONFIG_WRITE not in line or AWF_SCHEMA not in line:
            continue
        lookahead = "\n".join(lines[index + 1 : index + 45])
        if PATCH_MARKER_PREFIX in lookahead:
            continue

        indent = line[: len(line) - len(line.lstrip())]
        patched.extend(
            f"{indent}{snippet_line}" if snippet_line else ""
            for snippet_line in endpoint_patch_lines(secret_name, models_preflight=models_preflight)
        )
        insertions += 1
    return patched, insertions


def patch_awf_commands(lines: list[str], secret_name: str) -> tuple[list[str], int]:
    patched = list(lines)
    changes = 0
    for index, line in enumerate(patched):
        if AWF_COMMAND not in line or f"--exclude-env {secret_name}" in line:
            continue
        if "--env-all " not in line:
            raise RuntimeError("Found awf command without --env-all")
        patched[index] = line.replace("--env-all ", f"--env-all --exclude-env {secret_name} ", 1)
        changes += 1
    return patched, changes


def insert_endpoint_env(lines: list[str], secret_name: str) -> tuple[list[str], int]:
    patched = list(lines)
    insertions = 0
    awf_indices = [index for index, line in enumerate(patched) if AWF_COMMAND in line]

    for awf_index in reversed(awf_indices):
        _, next_step = containing_step_bounds(patched, awf_index)
        env_index = next(
            (index for index in range(awf_index + 1, next_step) if patched[index].strip() == "env:"),
            None,
        )
        if env_index is None:
            raise RuntimeError("Found awf command without a following env block")
        if any(f"{secret_name}:" in line for line in patched[env_index + 1 : next_step]):
            continue
        env_indent = patched[env_index][: len(patched[env_index]) - len(patched[env_index].lstrip())]
        patched.insert(env_index + 1, f"{env_indent}  {secret_name}: ${{{{ secrets.{secret_name} }}}}")
        insertions += 1

    return patched, insertions


def insert_codex_reasoning_effort(lines: list[str], reasoning_effort: str | None) -> tuple[list[str], int]:
    if not reasoning_effort:
        return lines, 0

    patched: list[str] = []
    insertions = 0
    for index, line in enumerate(lines):
        patched.append(line)
        if CODEX_CONFIG_HEREDOC not in line:
            continue
        lookahead = "\n".join(lines[index + 1 : index + 12])
        if "model_reasoning_effort =" in lookahead:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        patched.append(f'{indent}model_reasoning_effort = "{reasoning_effort}"')
        insertions += 1
    return patched, insertions


def ensure_redaction_steps(lines: list[str], options: PatchOptions) -> tuple[list[str], int]:
    patched = list(lines)
    changes = 0
    if options.agent_redaction:
        patched, count = replace_or_insert_redaction(
            patched,
            step_name=AGENT_REDACTION_STEP,
            before_step=AGENT_UPLOAD_STEP,
            condition="always()",
            root="/tmp/gh-aw",
            secret_name=options.secret_name,
        )
        changes += count
    if options.detection_redaction:
        patched, count = replace_or_insert_redaction(
            patched,
            step_name=DETECTION_REDACTION_STEP,
            before_step=DETECTION_UPLOAD_STEP,
            condition="always() && steps.detection_guard.outputs.run_detection == 'true'",
            root="/tmp/gh-aw/threat-detection",
            secret_name=options.secret_name,
        )
        changes += count
    return patched, changes


def replace_or_insert_redaction(
    lines: list[str],
    *,
    step_name: str,
    before_step: str,
    condition: str,
    root: str,
    secret_name: str,
) -> tuple[list[str], int]:
    patched = replace_named_steps(lines, step_name, condition, root, secret_name)
    if patched != lines:
        return patched, 1
    if any(line.strip() == f"- name: {step_name}" for line in lines):
        return lines, 0

    for index, line in enumerate(lines):
        if line.strip() != f"- name: {before_step}":
            continue
        indent = line[: len(line) - len(line.lstrip())]
        replacement = redaction_step_lines(
            step_indent=indent,
            step_name=step_name,
            condition=condition,
            secret_name=secret_name,
            root=root,
        )
        return lines[:index] + replacement + lines[index:], 1
    return lines, 0


def replace_named_steps(lines: list[str], step_name: str, condition: str, root: str, secret_name: str) -> list[str]:
    ranges = named_step_ranges(lines, step_name)
    if not ranges:
        return lines

    patched: list[str] = []
    cursor = 0
    for start, end in ranges:
        patched.extend(lines[cursor:start])
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        patched.extend(
            redaction_step_lines(
                step_indent=indent,
                step_name=step_name,
                condition=condition,
                secret_name=secret_name,
                root=root,
            )
        )
        cursor = end
    patched.extend(lines[cursor:])
    return patched


def is_step_start(line: str) -> bool:
    indent = len(line) - len(line.lstrip())
    return indent >= 6 and bool(re.match(r"^\s*-\s+", line))


def named_step_ranges(lines: list[str], step_name: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    seen_starts: set[int] = set()
    for index, line in enumerate(lines):
        if line.strip() not in {f"name: {step_name}", f"- name: {step_name}"}:
            continue
        start = containing_step_start(lines, index)
        if start in seen_starts:
            continue
        seen_starts.add(start)
        ranges.append((start, next_step_index(lines, start)))
    return ranges


def containing_step_start(lines: list[str], line_index: int) -> int:
    for start in range(line_index, -1, -1):
        if is_step_start(lines[start]):
            return start
    raise RuntimeError(f"Found named step without a step start near line {line_index + 1}")


def next_step_index(lines: list[str], start: int) -> int:
    step_indent = len(lines[start]) - len(lines[start].lstrip())
    for index in range(start + 1, len(lines)):
        if is_step_start(lines[index]) and len(lines[index]) - len(lines[index].lstrip()) == step_indent:
            return index
    return len(lines)


def containing_step_bounds(lines: list[str], line_index: int) -> tuple[int, int]:
    for start in range(line_index, -1, -1):
        if not is_step_start(lines[start]):
            continue
        return start, next_step_index(lines, start)
    return 0, len(lines)


def validate_patched_text(text: str, path: Path, options: PatchOptions) -> None:
    if PATCH_MARKER_PREFIX not in text:
        raise RuntimeError(f"{path} was not patched; no AWF config write was found")
    if f"--exclude-env {options.secret_name}" not in text:
        raise RuntimeError(f"{path} was not patched; no AWF command was updated")
    if f"{options.secret_name}: ${{{{ secrets.{options.secret_name} }}}}" not in text:
        raise RuntimeError(f"{path} was not patched; endpoint secret env is missing")
    if options.reasoning_effort and f'model_reasoning_effort = "{options.reasoning_effort}"' not in text:
        raise RuntimeError(f"{path} was not patched; Codex reasoning effort is missing")
    if options.agent_redaction and AGENT_REDACTION_STEP not in text:
        raise RuntimeError(f"{path} was not patched; agent redaction step is missing")
