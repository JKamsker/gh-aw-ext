# gh-aw-ext

Reusable extension helpers for `gh-aw` Codex workflows.

The extracted workflow glue does three things:

- Runs `gh aw compile`, then patches generated Codex lockfiles.
- Routes gh-aw's OpenAI-compatible Codex traffic through a secret-backed endpoint.
- Verifies the endpoint's `/v1/models` route before starting the sandbox.
- Redacts that endpoint from gh-aw artifacts before upload.

The default endpoint secret name is `CODEX_LB_BASE_URL`. The secret value is read only inside GitHub Actions at runtime; do not commit the endpoint host or full URL.

## Local Use

Install from this checkout:

```powershell
python -m pip install -e .
```

Compile a gh-aw workflow from another repo:

```powershell
gh-aw-ext compile .github/workflows/daily-repo-status.md
```

Patch existing lockfiles without compiling:

```powershell
gh-aw-ext patch-lockfiles .github/workflows/daily-repo-status.lock.yml
```

For unusual endpoints that cannot be reached directly from the runner, pass `--no-models-preflight`. The default should stay enabled for normal gh-aw Codex workflows.

Validate as usual after compiling:

```powershell
gh aw validate .github/workflows/daily-repo-status.md --no-check-update --stats
git diff -- .github/workflows
```

## Consumer Repository Requirements

Add these secrets to every repo that uses the patched Codex workflows:

- `CODEX_LB_BASE_URL`: absolute HTTP(S) base URL for the private OpenAI-compatible endpoint.
- `CODEX_API_KEY` or `OPENAI_API_KEY`: key consumed by the Codex engine.

For NCodex-LB, set `CODEX_LB_BASE_URL` to the endpoint path that maps gh-aw requests through `/backend-api/codex`. Older `/openai/v1` values are normalized in generated lockfiles for compatibility, but new secrets should use the `/backend-api/codex` route directly.

The endpoint must return a successful JSON response from the effective `/v1/models` route. gh-aw probes models before and after Codex runs; the load balancer should handle that route locally and proxy `/v1/responses` traffic to the configured backend/virtual token.

In gh-aw workflow markdown, keep `engine: codex`. Compile with this wrapper instead of raw `gh aw compile`.

## GitHub Actions

This repo also exposes composite actions:

- `actions/patch-lockfiles`: patch generated gh-aw lockfiles in CI.
- `actions/redact-artifacts`: redact endpoint values from artifact directories.
- `actions/dispatch-repair`: dispatch bounded repair runs after validation-gate failures.

See `examples/` for minimal workflow snippets.
