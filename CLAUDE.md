# CLAUDE.md

This repository contains a local product-taxonomy maintenance platform built with FastAPI, LangGraph, SQLite, Qdrant, and Vue.

## Source of truth

Read these files before changing code:

1. `开发文档/README.md`
2. `开发文档/00_当前状态/当前实现情况.md`
3. `开发文档/00_当前状态/当前开发路线图.md`
4. The relevant PRD or R1–R3 execution plan

The code and automated tests take precedence over descriptive documents. Files under `开发文档/99_历史归档/` are historical references, not the current implementation contract.

## Current direction

The current priority is `开发文档/03_开发执行计划/R1_可信诊断与完整结果_执行计划.md`: complete taxonomy and diagnosis queries, establish measurable diagnosis coverage, make plans and Token budgets constrain execution, preserve partial results when model budgets are exhausted, and connect nodes, issues, evidence, and reports.

Do not expand into a distributed multi-agent platform before the R1–R3 user loop is complete.

## Commands on Windows PowerShell

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
npm.cmd run dev
```

Do not use a global Python environment to install project dependencies.

## Architecture and engineering rules

- `backend/app/main.py` wires the FastAPI application and persistence initialization.
- `backend/app/api/` contains HTTP entry points.
- `backend/app/agents/` contains LangGraph state, thin nodes, graph construction, prompts, and event glue.
- `backend/app/services/` contains business logic.
- `backend/app/repositories/` contains SQLite persistence and queries.
- `backend/app/tools/` exposes scoped read and structured-submission tools.
- `backend/app/vectorstores/` adapts Qdrant access.
- `backend/app/schemas/` contains Pydantic contracts.

Keep LangGraph nodes thin. Deterministic parsing, diagnosis rules, SQL, vector-store operations, prompt construction, and action execution belong in services or repositories. LLMs must not directly mutate Excel, SQLite, or Qdrant. High-risk actions require human review. Preserve run, version, review, idempotency, and audit evidence for every side effect.

Do not expose raw chain-of-thought. Show decision summaries, tools, evidence, confidence, and cost instead. A failed node must not later be overwritten as completed, and reports or quality scores must never be hard-coded.

When changing workflow behavior, inspect the relevant code and current R1–R3 plan. Consult `开发文档/99_历史归档/历史功能设计/10_智能体工作流开发设计.md` only for historical design context.
