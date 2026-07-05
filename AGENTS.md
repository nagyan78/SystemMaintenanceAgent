# Project Agent Notes

This file is for future coding agents working in this repository. Read it before changing code. Do not replace the product/design documents with assumptions from memory.

## Project Identity

- Project path: `/Users/flflfl/Documents/code/SystemMaintenanceAgent`
- Project name: 产品标准体系维护智能体
- Goal: build a local product taxonomy maintenance agent platform using FastAPI, LangGraph, LangChain, SQLite, Qdrant, and a Vue frontend.
- Core workflow: upload Excel, parse taxonomy tree, save initial version, run structure diagnosis, run content diagnosis agent, generate suggestions agent, wait for human review, validate and execute approved actions, save a new version, and generate a report.
- This is not meant to be a generic Excel uploader or a simple chatbot. The central product is a LangGraph-orchestrated taxonomy maintenance agent with human-in-the-loop review.

## Source Of Truth

Use `dev-doc/` as the source of truth. Do not invent requirements or architecture details.

Read these first:

1. `dev-doc/00_开发里程碑索引.md`
2. `dev-doc/10_LangGraph智能体工作流开发设计.md`
3. `dev-doc/产品标准体系维护智能体_技术架构设计.md`
4. `dev-doc/架构评审报告.md`

When implementing a node, also read the corresponding feature document:

- `parse_excel_node`: `dev-doc/01_Excel上传与导入开发设计.md`
- `build_tree_node`, `save_initial_version_node`: `dev-doc/02_分类树解析与体系概览开发设计.md`
- `structure_diagnosis_node`: `dev-doc/03_结构诊断开发设计.md`
- `index_vector_node`, `content_diagnosis_node`: `dev-doc/04_向量索引与内容诊断开发设计.md`
- `generate_suggestion_node`: `dev-doc/05_智能建议生成开发设计.md`
- `wait_human_review_node`: `dev-doc/06_人工审核开发设计.md`
- `validate_action_node`, `execute_action_node`, `save_new_version_node`: `dev-doc/07_动作执行与版本管理开发设计.md`
- `generate_report_node`: `dev-doc/08_导出与诊断报告开发设计.md`
- frontend workflow/status/review/resume work: `dev-doc/09_前端工作台开发设计.md`

Note: an older README reference to `dev-doc/00_分功能开发文档索引.md` is outdated. The current milestone entry is `dev-doc/00_开发里程碑索引.md`.

## Current Implemented State

As of the current scaffold:

- FastAPI backend exists and starts from `backend/app/main.py`.
- SQLite initialization exists in `backend/app/db.py`.
- Excel upload is implemented through `backend/app/api/files.py`, `backend/app/services/excel_service.py`, and `backend/app/repositories/file_repo.py`.
- Basic tables exist: `uploaded_file`, `task_record`, `taxonomy_version`, `category_node`, `diagnosis_issue`, `adjustment_suggestion`, `operation_log`.
- LangGraph scaffold exists in `backend/app/agents/graph.py`, `backend/app/agents/nodes.py`, and `backend/app/agents/states.py`.
- The current LangGraph nodes are still MVP placeholders with hardcoded/demo results. They are not yet real business service calls.
- `wait_human_review_node` uses LangGraph interrupt, and tests cover interrupt/resume with `Command(resume=...)`.
- API modules for taxonomy, diagnosis, suggestions, versions, and chat are still placeholders returning 501.
- Vue frontend scaffold exists under `frontend/`, with upload and overview screens plus placeholder routes.
- Qdrant, LangChain agent loops, workflow API, streaming events, SQLite checkpointer, real taxonomy parsing, real diagnosis, suggestion generation, version execution, and report generation are not fully implemented yet.

## Current Development Direction

Follow the milestone plan, not the old 01-to-10 linear sequence.

Current target from `dev-doc/00_开发里程碑索引.md`:

- M1: 工作流骨架接真实数据（确定性闭环）
- Replace hardcoded graph node outputs with real service calls.
- M1 only implements deterministic workflow pieces: Excel parse, taxonomy tree build, initial version save, structure diagnosis, and template report.
- M1 must not call LLM or Qdrant.
- M2 and later introduce intelligent agent behavior through content diagnosis, suggestion generation, and report generation.

The architecture review says the current project feels like a workflow because LLM/tool-calling/ReAct loops are missing. The intended shape is:

- LangGraph remains the deterministic orchestration spine.
- Agent behavior belongs inside selected nodes/services:
  - `diagnosis_planning_node`
  - `content_diagnosis_node`
  - `generate_suggestion_node`
  - `generate_report_node`
- Deterministic nodes must stay deterministic.

## Important Engineering Rules From Dev Docs

- LangGraph nodes must be thin: call services, update state, decide routing.
- Do not put Excel parsing, tree building, SQL, Qdrant logic, prompt construction, or action execution logic directly inside nodes.
- Rule-based diagnosis should not use LLM.
- LLM must not directly modify Excel, SQLite, or Qdrant.
- All high-risk actions require human review before execution.
- Original Excel files must remain unchanged; new versions and exports are separate artifacts.
- In M1, do not hardcode values such as `structure_issue_count = 44`; that value must come from real data when M1 is implemented.

## Local Environment

- A Python virtual environment already exists at `.venv/`.
- Use `.venv/bin/python` for backend commands.
- Dependencies are installed in `.venv`, including FastAPI, pytest, pandas, openpyxl, langchain-ollama, and langgraph.
- Do not install packages globally with system Python.
- Frontend dependencies are installed under `frontend/node_modules/`.
- `.gitignore` already ignores `.venv/`, `frontend/node_modules/`, `frontend/dist/`, `frontend/*.tsbuildinfo`, and runtime data directories.

Useful commands:

```bash
.venv/bin/python -m pytest backend/tests
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend
npm run test:contract
npm run build
npm run dev
```

## Verification Baseline

Before claiming backend work is complete, run:

```bash
.venv/bin/python -m pytest backend/tests
```

Before claiming frontend work is complete, run from `frontend/`:

```bash
npm run test:contract
npm run build
```

The latest observed backend baseline was 17 tests passing with one third-party FastAPI/Starlette TestClient deprecation warning.

## Git And Workspace Notes

- The repository may contain user-authored or generated changes. Do not revert unrelated changes.
- At the time this file was created, `dev-doc/` had uncommitted document changes, including the migration from the old functional index to `00_开发里程碑索引.md`.
- Preserve user edits unless explicitly asked to change them.
