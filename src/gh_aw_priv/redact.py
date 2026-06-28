from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


REPLACEMENT = b"[REDACTED_CODEX_ENDPOINT]"


def redaction_needles(endpoint: str) -> list[bytes]:
    parsed = urlparse(endpoint.strip().rstrip("/"))
    candidates = {value for value in (endpoint.strip().rstrip("/"), parsed.netloc, parsed.hostname) if value}
    if parsed.hostname and parsed.port:
        candidates.add(f"{parsed.hostname}:{parsed.port}")
    return [candidate.encode() for candidate in sorted(candidates, key=len, reverse=True)]


def redact_file(path: Path, needles: list[bytes]) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\0" in data[:4096]:
        return False

    redacted = data
    for needle in needles:
        redacted = redacted.replace(needle, REPLACEMENT)
    if redacted == data:
        return False

    path.write_bytes(redacted)
    return True


def redact_tree(root: Path, needles: list[bytes]) -> int:
    if not root.exists():
        return 0

    count = 0
    for path in root.rglob("*"):
        if path.is_file() and redact_file(path, needles):
            count += 1
    return count


def redact_from_environment(paths: list[Path], secret_name: str) -> int:
    endpoint = os.environ.get(secret_name, "").strip().rstrip("/")
    if not endpoint:
        return 0

    needles = redaction_needles(endpoint)
    if not needles:
        return 0

    roots = paths or [Path("/tmp/gh-aw")]
    return sum(redact_tree(root, needles) for root in roots)
