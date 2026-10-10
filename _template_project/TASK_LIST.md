# 📋 Master Task List & Sprint Roadmap

> **Agent Directive**: Execute ONLY the item tagged with `[CURRENT FOCUS]`. Do not attempt subsequent tasks until the current task is verified and marked `[x]`.

---

## 🎯 Current Status
- **Project**: CodeLens — Retrieval-Augmented Code Review Agent
- **Current Sprint**: Sprint 3 — Evaluation, Optimization & Hardening
- **Active Task**: Task 3.1

---

## Phase 1: Foundation & Local Control Plane

- [x] **Task 1.1**: Populate `PROJECT_OVERVIEW.md` with scope, personas, features, non-goals. Draft decoupled architecture in `ARCHITECTURE.md`. Establish roadmap in `TASK_LIST.md`. Update `CODEBASE_MAP.md` and `CHANGELOG.md`.
- [x] **Task 1.2**: Initialize Python project structure. Create `pyproject.toml` with project metadata and tool configs (ruff, pytest). Create `requirements.txt` with pinned production deps (fastapi, uvicorn, pydantic, gitpython, py-tree-sitter, faiss-cpu, google-generativeai, PyGithub, httpx). Create `requirements-dev.txt` (pytest, pytest-asyncio, httpx, ruff). Create `.env.example` with all required env vars. Scaffold empty `src/` package with `__init__.py` files per `ARCHITECTURE.md` directory layout.
- [x] **Task 1.3**: Implement `src/models/enums.py` — `ChangeType`, `Language`, `ReviewSeverity` enums as defined in ARCHITECTURE.md §4.
- [x] **Task 1.4**: Implement `src/models/schemas.py` — all Pydantic models (`PREvent`, `DiffHunk`, `FunctionNode`, `RetrievalResult`, `ReviewComment`, `FeedbackEvent`) as defined in ARCHITECTURE.md §4.
- [x] **Task 1.5**: Implement `src/config.py` — `Settings` class using `pydantic-settings` loading from `.env` (GitHub webhook secret, Gemini API key, GCS bucket, FAISS index path, target repo).
- [x] **Task 1.6**: Implement `src/utils/security.py` — `verify_webhook_signature(payload, signature, secret)` using HMAC-SHA256. Write `tests/test_webhooks.py` with valid/invalid signature test cases.
- [x] **Task 1.7**: Implement `src/utils/logging.py` — structured JSON logging configuration with request ID propagation.
- [x] **Task 1.8**: Implement `src/main.py` — FastAPI app factory with router registration, CORS middleware, lifespan handler (load FAISS index on startup). Implement `src/api/health.py` — `GET /health` endpoint returning index status.

---

## Phase 2: Core Intelligence Pipeline

- [x] **Task 2.1**: Implement `src/core/diff_parser.py` — extract PR diff hunks using GitPython. Input: base_sha, head_sha, repo_path. Output: `list[DiffHunk]`. Write `tests/test_diff_parser.py` with fixture diffs.
- [x] **Task 2.2**: Implement `src/core/ast_parser.py` — Tree-sitter integration for Python and TypeScript grammars. Extract `FunctionNode` objects from source files. Write `tests/test_ast_parser.py` with multi-language fixture files.
- [x] **Task 2.3**: Connect diff parser + AST parser: for each `DiffHunk`, resolve which `FunctionNode`(s) are affected by mapping diff line ranges to AST node boundaries. Populate `DiffHunk.affected_functions`.
- [x] **Task 2.4**: Implement `src/services/storage_client.py` — download/upload FAISS index files and metadata JSON from GCS/Google Drive. Handle missing index gracefully (return empty state, log warning).
- [x] **Task 2.5**: Implement `src/services/index_manager.py` — load FAISS index into memory, expose `query(embedding, top_k)` method returning `RetrievalResult`. Implement `src/core/retriever.py` — orchestrate: given `FunctionNode`, look up its embedding ID, query index, return similar functions with scores. Write `tests/test_retriever.py`.
- [x] **Task 2.6**: Implement `src/core/reviewer.py` — construct Gemini API prompt from PR diff + retrieved similar functions. Parse Gemini response into `list[ReviewComment]`. Enforce output structure via Pydantic validation. Write `tests/test_reviewer.py` with mocked Gemini responses.
- [x] **Task 2.7**: Implement `src/services/github_client.py` — post `ReviewComment` objects as GitHub PR review comments using PyGithub. Handle rate limiting with exponential backoff.
- [x] **Task 2.8**: Implement `src/api/webhooks.py` — full `POST /webhook/github` handler: validate signature → parse `PREvent` → extract diffs → parse AST → retrieve similar functions → generate review → post comments. Wire the complete pipeline.
- [x] **Task 2.9**: Implement `src/api/feedback.py` — `POST /feedback` endpoint ingesting `FeedbackEvent` and appending to `feedback.jsonl`. Implement `src/api/reviews.py` — `POST /reviews/generate` for manual trigger.
- [x] **Task 2.10**: Create `colab/colab_indexer.ipynb` — notebook that clones a target repo, parses all source files with Tree-sitter, generates CodeBERT embeddings, builds FAISS index, and uploads to GCS/Drive.

---

## Phase 3: Evaluation, Optimization & Hardening

- [x] **Task 3.1**: Create `colab/colab_evaluator.ipynb` — compute retrieval metrics (precision@5, MRR, NDCG@10) and review quality metrics (acceptance rate, false positive rate) on feedback dataset.
- [x] **Task 3.2**: Implement incremental indexing — detect changed files on merge, re-embed only affected functions, merge into existing FAISS index.
- [x] **Task 3.3**: Implement Streamlit admin panel — index status, feedback metrics dashboard, manual re-index trigger.
- [ ] **Task 3.4** `[CURRENT FOCUS]`: Create `colab/colab_finetuner.ipynb` — fine-tune CodeBERT adapter on domain-specific code pairs from feedback data.
- [ ] **Task 3.5**: End-to-end integration test: simulate full PR lifecycle (webhook → diff → AST → retrieve → review → post → feedback).
- [ ] **Task 3.6**: Final validation — verify `CODEBASE_MAP.md` completeness, run ruff linter, confirm all tests pass.
