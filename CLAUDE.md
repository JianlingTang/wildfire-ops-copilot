# CLAUDE.md

Wildfire Ops Copilot: FastAPI (Python) backend + Next.js/React frontend.
Google ADK (Gemini) powers the LLM chat runtime; a deterministic Python
fallback and an LLM-free demo runtime provide the same behavior without live
LLM calls. An in-memory Firestore-shaped store persists runs/reports/alerts/
actions. Elastic Agent Builder MCP supplies operational evidence.

## Folders
- `app/api/` — FastAPI routes (chat, runs, alerts, actions, reports, hotspots).
- `app/runtime/` — chat orchestration: `adk/` (LLM + deterministic fallback),
  `mock_demo/` (LLM-free demo), `intent_responses.py` (shared trace/response
  builders all three runtimes use), `intents.py` (intent classification).
- `app/agents/` — specialist/workflow logic (analyst Q&A, what-if, action
  drafting, daily intelligence pipeline).
- `app/services/` — deterministic business logic (risk scoring, hotspot
  visualization, monitoring tasks, conversation memory, guardrails).
- `app/tools/` — external data providers (DEA hotspots, weather, official
  warnings, spatial exposure, Elastic MCP evidence).
- `wildfire_ops_agent/` — the Google ADK `LlmAgent` tool surface (13
  FunctionTools) exposed to Gemini.
- `frontend/` — Next.js app; `lib/api/` is the backend client, `components/`
  the UI, with `agent-chat/`, `operations-console/`, `emergency-request/`,
  `report-center/` holding each big component's split-out pieces.
- `tests/` — pytest suite; `conftest.py` forces the demo runtime for all
  tests except `test_adk_runtime.py`.

## Do not change casually
- **Never let the agent answer without grounding in real tool/evidence
  output.** This app is used by emergency responders — a wrong guess is
  worse than "I don't know." `knowledge_retrieval_required_tool` /
  `knowledge_required_response` must keep refusing rather than inventing an
  answer; `app/services/request_scope.py`'s out-of-scope gate must stay in
  front of every chat request.
- **Anything requiring human approval must have an accurate draft before it
  reaches `app/services/guardrails.py` / `approval_policy.py`.** The app
  never auto-executes an external action — approval is the safety boundary,
  not a formality.
- **Keep the three chat runtimes behaviorally identical per intent**
  (`wildfire_ops_agent/`, `app/runtime/adk/`, `app/runtime/mock_demo/`).
  Trace/response shape drift between them is a real bug class here (fixed
  once already) — route new per-intent logic through
  `app/runtime/intent_responses.py`, not a runtime-local copy.

See `ARCHITECTURE.md` for system diagrams.
