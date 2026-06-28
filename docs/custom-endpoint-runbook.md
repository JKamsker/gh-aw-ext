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
- gh-aw artifacts are redacted before upload.

The endpoint host and full URL are treated as secret. The secret name is safe to mention; the value is not.

## Recommended Workflow

1. Edit `.github/workflows/<name>.md`.
2. Run `gh-aw-ext compile .github/workflows/<name>.md`.
3. Run `gh aw validate .github/workflows/<name>.md --no-check-update --stats`.
4. Review the generated `.lock.yml` diff.
5. Commit both the source markdown and lockfile.

If raw `gh aw compile` is run accidentally, rerun the wrapper before committing.
