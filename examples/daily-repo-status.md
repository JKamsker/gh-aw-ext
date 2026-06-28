---
description: |
  Example gh-aw daily repo status workflow using the Codex engine.

on:
  schedule: daily
  workflow_dispatch:

permissions:
  contents: read
  issues: read
  pull-requests: read

network: defaults

tools:
  github:
    lockdown: false
    min-integrity: none

safe-outputs:
  mentions: false
  allowed-github-references: []
  create-issue:
    title-prefix: "[repo-status] "
    labels: [report, daily-status]
    close-older-issues: true

# Compile with `gh-aw-ext compile .github/workflows/daily-repo-status.md`.
# The wrapper patches the generated lockfile to read CODEX_LB_BASE_URL at runtime.
engine: codex

source: githubnext/agentics/workflows/repo-status.md@1c6668b751c51af8571f01204ceffb19362e0f66
---

# Repo Status

Create a concise daily status report for the repo as a GitHub issue.

## What to include

- Recent repository activity.
- Progress tracking and maintainer-relevant highlights.
- Project status and concrete next steps.
