# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## What this repo is

This is a local taxonomy-maintenance agent platform for product standards classification. The backend is a FastAPI service with SQLite persistence; the workflow is modeled with LangGraph and split into milestone phases:

- M1: Excel upload, taxonomy parsing/building, initial versioning, structure diagnosis, report generation
- M2: Qdrant vector indexing, diagnosis planning, content diagnosis agent
- M3: suggestion generation agent, human review interrupt/resume, approved-action validation
- M4: action execution, new versioning, report/export
- M5: frontend workbench and end-to-end visualization

The design intent is to keep LangGraph nodes thin and push business logic into service/repository layers.

## Common commands

### Backend

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run the backend:

```bash
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

Run a single backend test file:

```bash
.venv/bin/python -m pytest backend/tests/test_m2_vector_content_agent.py -q
```

Run a single test case:

```bash
.venv/bin/python -m pytest backend/tests/test_langgraph_workflow.py -k <test_name> -q
```

### Frontend

The frontend is in `frontend/`.

Install and run dev server:

```bash
cd frontend
npm install
npm run dev
```

Build frontend:

```bash
cd frontend
npm run build
```

Run frontend contract test:

```bash
cd frontend
npm run test:contract
```

## High-level architecture

### Backend layers

- `backend/app/main.py` wires FastAPI routers and initializes app state / SQLite.
- `backend/app/api/` contains HTTP entry points.
- `backend/app/agents/` contains LangGraph state, node functions, graph construction, prompts, and streaming/event glue.
- `backend/app/services/` holds business logic such as Excel parsing, taxonomy building, diagnosis, vector indexing, content diagnosis, suggestion generation, review, and reporting.
- `backend/app/repositories/` handles SQLite persistence and query logic.
- `backend/app/tools/` exposes LangChain tools used by agents to inspect taxonomy data and submit structured results.
- `backend/app/vectorstores/` adapts Qdrant access.
- `backend/app/schemas/` defines Pydantic models shared across API/service/agent layers.

### Workflow model

The primary execution path is a LangGraph workflow over a shared `TaxonomyGraphState`. Nodes are expected to stay thin: read state, call a service, update state, and decide the next step.

Important patterns:

- Deterministic steps: Excel parsing, tree building, version creation, structure diagnosis, report generation
- Agentic steps: diagnosis planning, content diagnosis, suggestion generation
- Human-in-the-loop step: `wait_human_review_node` uses interrupt/resume
- M3 stops before execution/version-save; M4 adds those actions later

### Context management

The project uses layered context rather than dumping the whole taxonomy into prompts:

- Workflow state for cross-node progress and IDs
- Qdrant similarity search for local candidate retrieval
- Tree tools for node detail/path/children lookup
- Structured tool outputs for diagnosis and suggestion submission

### Persistence

SQLite is the source of truth for uploaded files, taxonomy versions, nodes, diagnosis issues, suggestions, logs, and workflow records. `task_record` is used to track workflow progress, interrupt payloads, and results.

## Working conventions that matter here

- Keep LangGraph nodes thin; put logic in services.
- M3 should not execute actions or create new versions; that belongs to M4.
- Suggestions and diagnosis results should be structured, not free-form text.
- LLMs should use tools for context retrieval and structured submission rather than mutating data directly.
- If you need to update workflow behavior, check both `backend/app/agents/graph.py` and the milestone docs under `dev-doc/` so the code and documentation stay aligned.

## Key docs

- `README.md` for setup and current runnable scope
- `dev-doc/00_开发里程碑索引.md` for milestone boundaries
- `dev-doc/10_LangGraph智能体工作流开发设计.md` for workflow topology and state design
- `dev-doc/M3_执行prompt.md` and `dev-doc/M3_最终执行计划.md` for the current M3 implementation contract
