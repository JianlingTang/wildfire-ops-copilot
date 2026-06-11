# Project Instructions

## Core Rule

Preserve user work. Make minimal, targeted changes. Do not delete, reset,
force-overwrite, or bulk-modify files unless the user explicitly approves the
exact command and paths.

## Standard Workflow

1. Before editing, run `git status --short` and avoid overwriting user changes.
2. Inspect only relevant files using read-only commands such as `rg`, `sed`,
   `ls`, `find`, `git diff`, and `git ls-files`.
3. Explain the intended minimal edit before changing files.
4. Use targeted patches. Do not reformat, rename, reorder, or refactor unrelated
   code.
5. Run the smallest relevant tests or checks.
6. Before committing, show `git status --short` and `git diff --stat`; commit
   only files relevant to the task.

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
alternative such as leaving it untouched or moving it to a backup folder. Wait
for approval.

## Dependencies And Data

Do not remove dependencies or run broad update commands unless explicitly
requested. Explain dependency and lockfile changes before making them. Treat
data files, notebooks, logs, figures, model outputs, and generated research
artifacts as valuable; do not delete, move, overwrite, or regenerate them unless
requested.

## Context Budget

Avoid reading generated, dependency, cache, credential, and build directories
unless the task specifically requires them: `.git`, `.venv`, `frontend/node_modules`,
`frontend/.next`, `frontend/out`, `infra/terraform/.terraform`, `.gcloud*`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `__pycache__`, and `*.tsbuildinfo`.
Prefer focused commands with limited output over broad project scans.
