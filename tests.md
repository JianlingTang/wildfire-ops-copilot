# Testing Strategy

Testing is required for every backend workflow, deterministic tool, API route, and safety boundary.

The backend quality gates are:

- `ruff check .`
- `mypy app tests`
- `pytest -q`

The frontend MVP gates are:

- `npm run lint`
- `npm run build`

For this Next.js version, `npm run lint` runs `tsc --noEmit` because the installed `next` CLI no longer provides the old `next lint` command.

## Backend Structure

Tests live under:

```text
tests/
  unit/
  api/
  agents/
  fixtures/
```

The current tests cover deterministic risk scoring, change detection, approval policy, Elastic fallback schema, weather/fire tool validation, guardrails, FastAPI routes, and agent routing. Tests use demo data and must not call production services.

## Guardrails

Guardrails are tested as normal Python functions:

- `before_model_callback`
- `before_tool_callback`

They block approval bypass attempts, emergency authority impersonation, prompt injection patterns, and external tools without an approved approval record.

## CI

GitHub Actions runs backend lint, type checking, tests, frontend lint, and frontend build on pull requests and pushes to `main`. CI uses dummy service values and must not call real emergency, Firestore, NASA FIRMS, Google, or Elastic services.

## Smoke Test

Run the local smoke flow with:

```bash
scripts/smoke_test.sh
```

The smoke test uses the FastAPI app in-process through `TestClient`; it does not require real external services and does not send real communications.

## Codex Rules

Do not remove tests to make checks pass, replace assertions with `assert True`, mock the unit under test, add broad exception swallowing, or add CI flags that ignore failures. If a test is invalid, explain why and replace it with a better test.
