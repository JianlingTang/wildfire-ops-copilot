# Testing Strategy

Testing covers backend workflows, tools, API routes, and safety boundaries.

## Main Checks

```bash
ruff check .
mypy app tests
pytest -q
cd frontend && npm run lint && npm run build
```

## Layout

```text
tests/
  unit/
  api/
  agents/
  fixtures/
```

Tests use demo data only and must not call production services.

## Guardrails

`before_model_callback` and `before_tool_callback` block approval bypasses,
emergency-authority impersonation, prompt injection, and unapproved external
tools.

## Smoke Test

```bash
bash scripts/smoke_test.sh
```

## Rules

Do not delete tests to make checks pass, replace assertions with `assert True`,
or add broad exception swallowing. If a test is wrong, replace it with a better
one.
