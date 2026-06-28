# gh-aw Custom Endpoint Runbook

Use `gh-aw-ext compile` for Codex gh-aw workflows that must route through a private OpenAI-compatible endpoint.

```powershell
gh-aw-ext compile .github/workflows/daily-repo-status.md
```

The wrapper runs `gh aw compile` first, then patches the generated `.lock.yml` file.

## Runtime Contract

- `CODEX_LB_BASE_URL` contains the private endpoint base URL.
- The endpoint must be an absolute HTTP(S) URL with a hostname, optional port, and optional path.
- The generated AWF config is patched on the runner so gh-aw's OpenAI target points at that endpoint.
- The endpoint host is added to AWF's network allow-list at runtime.
- The endpoint secret is passed only to runner-side setup and redaction steps.
- The endpoint secret is excluded from the sandboxed agent environment.
- The generated workflow checks the effective `/v1/models` route before starting AWF.
- gh-aw artifacts are redacted before upload.

For NCodex-LB, the endpoint path should be `/backend-api/codex`. The patcher normalizes older `/openai/v1` values to that route inside generated lockfiles, but repository secrets should be updated to the current route when convenient.

The load balancer must answer gh-aw model-list probes locally. A successful `/v1/models` response must be JSON; `/v1/responses` traffic can still be proxied to the configured backend or virtual token. If the preflight reports a 503, update the endpoint or load-balancer routing before rerunning the workflow.

The endpoint host and full URL are treated as secret. The secret name is safe to mention; the value is not.

## Recommended Workflow

1. Edit `.github/workflows/<name>.md`.
2. Run `gh-aw-ext compile .github/workflows/<name>.md`.
3. Run `gh aw validate .github/workflows/<name>.md --no-check-update --stats`.
4. Review the generated `.lock.yml` diff.
5. Commit both the source markdown and lockfile.

If raw `gh aw compile` is run accidentally, rerun the wrapper before committing.
