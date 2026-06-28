from __future__ import annotations


def endpoint_patch_lines(secret_name: str, *, models_preflight: bool = True) -> list[str]:
    lines = [
        f"# Patch gh-aw OpenAI proxy target from {secret_name}.",
        "python3 - <<'PY'",
        "import json",
        "import os",
        "from pathlib import Path",
        "from urllib.parse import urlparse",
        "",
        f'endpoint = os.environ["{secret_name}"].strip().rstrip("/")',
        "parsed = urlparse(endpoint)",
        'if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:',
        f'    raise SystemExit("{secret_name} must be an absolute HTTP(S) URL with only a hostname, optional port, and optional path")',
        "host = parsed.hostname",
        "target_host = parsed.netloc",
        'base_path = parsed.path.rstrip("/")',
        'if base_path == "/openai/v1":',
        '    base_path = "/backend-api/codex"',
        'print(f"::add-mask::{endpoint}")',
        'print(f"::add-mask::{host}")',
        'print(f"::add-mask::{target_host}")',
        'config_path = Path(os.environ["RUNNER_TEMP"]) / "gh-aw" / "awf-config.json"',
        "config = json.loads(config_path.read_text())",
        'allow_domains = config.setdefault("network", {}).setdefault("allowDomains", [])',
        "if host not in allow_domains:",
        "    allow_domains.append(host)",
        'openai_target = config.setdefault("apiProxy", {}).setdefault("targets", {}).setdefault("openai", {})',
        'openai_target["host"] = target_host',
        "if base_path:",
        '    openai_target["basePath"] = base_path',
        "else:",
        '    openai_target.pop("basePath", None)',
    ]
    if models_preflight:
        lines.extend(models_preflight_lines(secret_name))
    lines.extend(
        [
            'config_path.write_text(json.dumps(config, separators=(",", ":"), ensure_ascii=False) + "\\n")',
            "PY",
        ]
    )
    return lines


def models_preflight_lines(secret_name: str) -> list[str]:
    return [
        "# Verify the endpoint handles gh-aw model-list probes before starting AWF.",
        "from urllib import error, request",
        'api_key = os.environ.get("CODEX_API_KEY") or os.environ.get("OPENAI_API_KEY")',
        "if not api_key:",
        '    raise SystemExit("CODEX_API_KEY or OPENAI_API_KEY is required for Codex endpoint preflight")',
        'models_url = f"{parsed.scheme}://{target_host}{base_path}/v1/models"',
        'preflight = request.Request(models_url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})',
        "try:",
        "    with request.urlopen(preflight, timeout=20) as response:",
        "        response_body = response.read(65536)",
        "except error.HTTPError as exc:",
        f'    raise SystemExit("{secret_name} preflight failed: /v1/models returned HTTP " + str(exc.code) + "; the endpoint must answer model-list probes locally before Codex runs") from None',
        "except Exception as exc:",
        f'    raise SystemExit("{secret_name} preflight failed before Codex could run (" + type(exc).__name__ + "); check endpoint reachability and TLS without printing the secret URL") from None',
        "try:",
        '    models_payload = json.loads(response_body.decode("utf-8"))',
        "except Exception:",
        f'    raise SystemExit("{secret_name} preflight failed: /v1/models returned non-JSON content") from None',
        "if not isinstance(models_payload, dict):",
        f'    raise SystemExit("{secret_name} preflight failed: /v1/models returned an unexpected JSON shape")',
        'print("Codex endpoint /v1/models preflight passed")',
    ]


def redaction_python_lines(secret_name: str, root: str) -> list[str]:
    return [
        "import os",
        "from pathlib import Path",
        "from urllib.parse import urlparse",
        "",
        'replacement = b"[REDACTED_CODEX_ENDPOINT]"',
        f'endpoint = os.environ.get("{secret_name}", "").strip().rstrip("/")',
        "if not endpoint:",
        "    raise SystemExit(0)",
        "parsed = urlparse(endpoint)",
        "needles = {value for value in (endpoint, parsed.netloc, parsed.hostname) if value}",
        "if parsed.hostname and parsed.port:",
        '    needles.add(f"{parsed.hostname}:{parsed.port}")',
        "ordered_needles = [needle.encode() for needle in sorted(needles, key=len, reverse=True)]",
        "redacted_count = 0",
        f'for path in Path("{root}").rglob("*"):',
        "    if not path.is_file():",
        "        continue",
        "    try:",
        "        data = path.read_bytes()",
        "    except OSError:",
        "        continue",
        '    if b"\\0" in data[:4096]:',
        "        continue",
        "    redacted = data",
        "    for needle in ordered_needles:",
        "        redacted = redacted.replace(needle, replacement)",
        "    if redacted != data:",
        "        path.write_bytes(redacted)",
        "        redacted_count += 1",
        'print(f"Redacted Codex endpoint artifacts: {redacted_count} file(s)")',
    ]


def redaction_step_lines(
    *,
    step_indent: str,
    step_name: str,
    condition: str,
    secret_name: str,
    root: str,
) -> list[str]:
    lines = [
        f"{step_indent}- name: {step_name}",
        f"{step_indent}  if: {condition}",
        f"{step_indent}  env:",
        f"{step_indent}    {secret_name}: ${{{{ secrets.{secret_name} }}}}",
        f"{step_indent}  run: |",
        f"{step_indent}    python3 - <<'PY'",
    ]
    for line in redaction_python_lines(secret_name, root):
        lines.append(f"{step_indent}    {line}" if line else f"{step_indent}")
    lines.append(f"{step_indent}    PY")
    return lines
