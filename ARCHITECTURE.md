# Architecture

Living document. Update this when the runtime/package layout changes —
diagrams that drift from the code are worse than no diagram.

## System overview

```mermaid
flowchart LR
    FE["frontend/ (Next.js)"] -->|"fetch /api/*"| API["app/api/ (FastAPI routes)"]
    API --> RT{"app.runtime.get_runtime()\nAGENT_RUNTIME env var"}
    RT -->|"AGENT_RUNTIME=adk"| ADK["app/runtime/adk/\nAdkRuntime"]
    RT -->|"AGENT_RUNTIME=mock_demo"| DEMO["app/runtime/mock_demo/\nMockDemoRuntime"]
    ADK -->|"LlmAgent tool call"| WOA["wildfire_ops_agent/\n(13 ADK FunctionTools)"]
    ADK -->|"deterministic fallback"| SVC["app/services/ + app/agents/"]
    DEMO --> SVC
    WOA --> SVC
    SVC --> TOOLS["app/tools/\n(DEA hotspots, weather,\nofficial warnings, spatial,\nElastic MCP)"]
    TOOLS -->|"live mode"| EXT["External APIs +\nElastic Agent Builder MCP"]
    SVC --> STORE[("app/services/firestore_store.py\nin-memory Firestore-shaped store")]
    ADK -.->|"Gemini / Vertex AI"| GEMINI["Google ADK Runner\n(Gemini LLM)"]
```

Three runtimes implement the same chat contract:
- **`wildfire_ops_agent/`** — the LLM tool surface. Gemini picks one of 13
  `FunctionTool`s per turn; each tool builds a `ChatRequest` from ADK session
  state, calls the same `app/services` / `app/agents` logic as the other two
  runtimes, and stashes its result back into session state.
- **`app/runtime/adk/`** — drives the ADK `Runner`/Gemini turn, then
  validates the result and falls back to deterministic dispatch
  (`dispatch.py`) if Gemini didn't call a required tool or returned an
  off-target answer (`guardrails.py`, `response.py`, `synthesis.py`).
- **`app/runtime/mock_demo/`** — no LLM call at all; dispatches directly by
  classified intent (`handlers.py`) for demos and CI.

All three route intent-to-trace/response shaping through
`app/runtime/intent_responses.py` so the three stay behaviorally identical —
see the "do not change casually" note in `CLAUDE.md`.

## Chat request flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as app/api/chat.py
    participant RT as Runtime (adk or mock_demo)
    participant Gate as request_scope / chat_conversations
    participant Dispatch as per-intent handler
    participant Guard as guardrails / approval_policy

    FE->>API: POST /api/chat {message, region, aoi, ...}
    API->>RT: route_chat(request)
    RT->>Gate: is_wildfire_operations_request()
    Gate-->>RT: reject if out of scope
    RT->>RT: classify_intent(message)
    RT->>Gate: should_block_for_analysis()
    Gate-->>RT: analysis_required_response if blocked
    RT->>Dispatch: handler(request, run, ...)
    alt intent needs external action
        Dispatch->>Guard: create pending approval (never auto-execute)
    end
    Dispatch-->>RT: payload + tool_trace (intent_responses.py)
    RT-->>API: {intent, response, trace_id, timing_trace}
    API-->>FE: JSON response
```

## Approval / guardrail flow

External actions (public advisories, drafted communications) are never
executed directly — every path ends at a pending human approval:

```mermaid
flowchart TD
    Intent["ACTION_COMMAND / EXPOSURE_ACTION intent"] --> Draft["app/agents/workflows/action_workflow.py\ndraft_action()"]
    Draft --> Policy["app/services/approval_policy.py\nvalidate_action_type()"]
    Policy --> Pending["ActionRecord status=pending_approval\n(app/services/firestore_store.py)"]
    Pending --> Human{"Human operator\nreviews in frontend"}
    Human -->|"approve"| Approved["POST /api/actions/{id}/approve"]
    Human -->|"reject"| Rejected["POST /api/actions/{id}/reject"]
    Approved --> Guard["app/services/guardrails.py\nbefore_tool_callback()"]
    Guard --> Exec["app/tools/execution_tools.py"]
    Rejected --> Done["No execution"]
```

## Folder responsibilities

```mermaid
flowchart TB
    subgraph backend["Backend (Python)"]
        api["app/api/ — FastAPI routes"]
        runtime["app/runtime/ — chat orchestration\n(adk/, mock_demo/, intent_responses.py, intents.py)"]
        agents["app/agents/ — specialists + workflows"]
        services["app/services/ — deterministic business logic"]
        tools["app/tools/ — external data providers"]
        woa["wildfire_ops_agent/ — ADK LlmAgent tool surface"]
    end
    subgraph frontend["Frontend (Next.js)"]
        pages["app/ — routes"]
        components["components/ — UI, split by feature\n(agent-chat/, operations-console/,\nemergency-request/, report-center/)"]
        lib["lib/ — api/ client, utils"]
    end
    api --> runtime
    runtime --> agents
    runtime --> services
    agents --> services
    services --> tools
    woa --> agents
    woa --> services
    pages --> components
    components --> lib
```
