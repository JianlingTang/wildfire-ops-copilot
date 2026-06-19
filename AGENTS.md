# Project Instructions

## Core Rule

Preserve user work. Make minimal, targeted changes. Do not delete, reset,
force-overwrite, or bulk-modify files without explicit approval.

## Standard Workflow

1. Run `git status --short` before editing.
2. Inspect only relevant files with read-only commands.
3. Explain the minimal edit before changing files.
4. Use targeted patches only.
5. Run the smallest relevant test or check.
6. Before committing, show `git status --short` and `git diff --stat`.

## Forbidden Without Explicit Approval

- `rm`, recursive `rm`, `sudo rm`, `find ... -delete`, `find ... -exec rm`,
  `xargs rm`
- `git clean`, `git reset --hard`, `git checkout -- .`, `git restore .`,
  `git restore --source`
- `truncate`, broad overwrite redirection such as `> file` or `cat > file`
- Any command that deletes, wipes, resets, force-overwrites, or bulk-modifies
  files

## Cleanup And Deletion

If cleanup seems useful, do not execute it first. Provide the exact paths, why
each is believed safe, git-tracked status, reference check, and a safer
alternative. Wait for approval.

## Dependencies And Data

Do not remove dependencies or run broad update commands unless requested.
Treat data files, logs, figures, model outputs, and generated research
artifacts as valuable.

## Context Budget

Avoid generated, dependency, cache, credential, and build directories unless
required: `.git`, `.venv`, `frontend/node_modules`, `frontend/.next`,
`frontend/out`, `infra/terraform/.terraform`, `.gcloud*`, `.pytest_cache`,
`.mypy_cache`, `.ruff_cache`, `__pycache__`, `*.tsbuildinfo`.
Prefer focused commands with limited output.
