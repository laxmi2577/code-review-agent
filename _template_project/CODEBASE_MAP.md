# 🗺️ Codebase Map & Symbol Registry

> **Agent Directive**: Consult this registry BEFORE searching for files or symbols.
> When a new file is added or functions/classes are created, modified, or deleted, update the corresponding entry in this file.

---

## 📂 Core Configuration & Documentation Files

| File Path | Purpose | Key Symbols / Exports / Sections |
| :--- | :--- | :--- |
| `_template_project/GEMINI.md` | Agent directives, token reduction rules, auto-updates | Token Directives, Doc Maintenance, Workflow Rules |
| `_template_project/AGENTS.md` | Architecture boundaries & hardware compute constraints | Hardware specs, Local control plane, Colab offloading |
| `_template_project/PROJECT_OVERVIEW.md` | CodeLens product spec — personas, features, non-goals | 3 Personas (Eng Lead, IC Reviewer, Junior Engineer), 6 Features (F1–F6), Non-Goals, Success Metrics |
| `_template_project/ARCHITECTURE.md` | Decoupled system design, API contracts, data models | Tech Stack, 3-Tier Architecture Diagram, Directory Layout, Pydantic Schemas (§4), API Endpoints (§5), Supported Languages (§6), Compute Boundaries (§7) |
| `_template_project/TASK_LIST.md` | Sprint tracker with `[CURRENT FOCUS]` | Phase 1 (Tasks 1.1–1.8), Phase 2 (Tasks 2.1–2.10), Phase 3 (Tasks 3.1–3.6) |
| `_template_project/CHANGELOG.md` | Delta memory tracking file-by-file changes | Timestamped chronological modification log |
| `_template_project/CODEBASE_MAP.md` | Registry of every file and its exported symbols | This index table & detailed function map below |
| `_template_project/PROJECT_IDEAS.md` | Archived: 10 production-grade project proposals (selection complete → Idea #5) | Ideas 1–10: LegalTech, IoT, FinTech, DataEng, DevTooling, MfgCV, KnowledgeMgmt, Support, HRTech, SupplyChain |
| `pyproject.toml` | Build configuration, packaging metadata, tool configs | `project`, `tool.ruff`, `tool.pytest.ini_options` |
| `requirements.txt` | Pinned production dependencies | FastAPI, Uvicorn, Pydantic, GitPython, Tree-sitter, FAISS, Gemini API |
| `requirements-dev.txt` | Pinned test and developer dependencies | pytest, pytest-asyncio, ruff |
| `.env.example` | Environment variable template | GitHub, Gemini API, and Storage credentials / config |

---

## 🧩 Source Code Registry

| File Path | Exported Functions / Classes / Components | Purpose |
| :--- | :--- | :--- |
| `src/__init__.py` | `__version__` | Package initialization and version definition |
| `src/main.py` | `create_app`, `app`, `RequestIdMiddleware`, `lifespan`, `root_endpoint` | FastAPI application factory, CORS, request ID middleware, and root endpoint |
| `src/api/__init__.py` | `health_router`, `webhooks_router`, `feedback_router`, `reviews_router` | API route modules namespace |
| `src/api/feedback.py` | `router`, `ingest_feedback`, `FeedbackResponse` | Feedback ingestion endpoint (`POST /feedback`) appending to `reactions.jsonl` |
| `src/api/health.py` | `get_health`, `HealthResponse` | Readiness probe endpoint (`GET /health`) |
| `src/api/reviews.py` | `router`, `generate_manual_review`, `run_manual_review`, `ManualReviewRequest`, `ManualReviewResponse` | Manual on-demand review trigger endpoint (`POST /reviews/generate`) |
| `src/api/webhooks.py` | `router`, `process_pr_review_pipeline`, `WebhookResponse`, `get_index_manager` | GitHub webhook receiver endpoint (`POST /webhook/github`) and pipeline runner |
| `src/core/__init__.py` | `ASTParser`, `CodeRetriever`, `GeminiReviewer`, `detect_language`, `parse_unified_diff`, `extract_diff_from_repo`, `map_diff_to_functions` | Pipeline components namespace |
| `src/core/ast_parser.py` | `ASTParser` | Tree-sitter AST parser extracting FunctionNode objects for Python and TypeScript |
| `src/core/diff_parser.py` | `detect_language`, `parse_unified_diff`, `extract_diff_from_repo`, `map_diff_to_functions` | Git diff extraction, hunk parsing, and diff-to-AST mapping |
| `src/core/retriever.py` | `CodeRetriever` | Similarity retriever orchestrating vector lookup, self-exclusion, and RetrievalResult building |
| `src/core/reviewer.py` | `GeminiReviewer` | Gemini API client with prompt construction and structured ReviewComment output validation |
| `src/config.py` | `Settings`, `get_settings` | Environment and application settings via pydantic-settings |
| `src/models/__init__.py` | Module root | Pydantic models namespace |
| `src/models/enums.py` | `ChangeType`, `Language`, `ReviewSeverity` | Domain enums for change types, languages, and review severities |
| `src/models/schemas.py` | `FunctionNode`, `DiffHunk`, `PREvent`, `RetrievalResult`, `ReviewComment`, `FeedbackEvent` | Core Pydantic domain models and schemas |
| `src/services/__init__.py` | `StorageClient`, `IndexManager`, `GitHubClient`, `IncrementalIndexer` | External services namespace |
| `src/services/github_client.py` | `GitHubClient` | PyGithub client posting inline review comments with 422 fallback and rate-limit backoff |
| `src/services/storage_client.py` | `StorageClient` | Local cache and cloud storage (GCS) download/upload client for FAISS vector indices |
| `src/services/index_manager.py` | `IndexManager` | In-memory FAISS lifecycle management, nearest-neighbor vector querying, and metadata resolution |
| `src/services/incremental_indexer.py` | `IncrementalIndexer`, `IncrementalUpdateResult` | Incremental vector index updates on PR diffs/merges with selective re-embedding and FAISS sync |
| `src/admin/app.py` | Streamlit Dashboard | Web control plane for vector index health, feedback telemetry (+1/-1 rates), and live PR review testing |
| `src/utils/__init__.py` | Module root | Utilities namespace |
| `src/utils/logging.py` | `JSONFormatter`, `setup_logging`, `request_id_ctx` | Structured JSON logging with request ID correlation |
| `src/utils/security.py` | `verify_webhook_signature` | HMAC-SHA256 GitHub webhook signature verification |
| `tests/__init__.py` | Test suite root | Test suite package namespace |
| `tests/test_ast_parser.py` | `test_parse_python_functions_and_methods`, `test_parse_typescript_functions_and_methods`, `test_parse_empty_or_unsupported` | Unit tests for polyglot AST parser |
| `tests/test_config.py` | `test_default_settings`, `test_custom_settings_via_env`, `test_get_settings_singleton` | Unit tests for configuration management |
| `tests/test_diff_parser.py` | `test_detect_language`, `test_parse_unified_diff_single_hunk`, `test_parse_unified_diff_multi_file`, `test_map_diff_to_functions` | Unit tests for diff parser and hunk mapping |
| `tests/test_enums.py` | `test_change_type_values`, `test_language_values`, `test_review_severity_values`, `test_enum_invalid_value` | Unit tests for domain enums |
| `tests/test_feedback.py` | `test_ingest_feedback_success`, `test_ingest_multiple_feedback`, `test_manual_review_generate` | Unit tests for feedback ingestion and manual review generation |
| `tests/test_github_client.py` | `test_format_comment_body`, `test_post_single_comment_inline_success`, `test_post_single_comment_fallback_on_422`, `test_post_review_comments_batch`, `test_retry_on_rate_limit` | Unit tests for PyGithub client wrapper |
| `tests/test_health.py` | `test_health_endpoint`, `test_health_with_custom_request_id`, `test_root_endpoint` | Unit tests for health probe, request ID, and root endpoint |
| `tests/test_incremental_indexer.py` | `test_incremental_indexer_update_empty_index`, `test_incremental_indexer_update_hunks`, `test_incremental_indexer_sync_on_merge` | Unit tests for incremental indexer service |
| `tests/test_logging.py` | `test_json_formatter_basic`, `test_json_formatter_with_request_id`, `test_json_formatter_with_exception`, `test_setup_logging` | Unit tests for structured JSON logging |
| `tests/test_retriever.py` | `test_index_manager_unloaded`, `test_index_manager_load_and_query`, `test_retriever_query_with_self_exclusion`, `test_retriever_unloaded_index`, `test_retriever_for_hunks` | Unit tests for IndexManager and CodeRetriever |
| `tests/test_reviewer.py` | `test_build_prompt_structure`, `test_parse_clean_json_response`, `test_parse_markdown_wrapped_json`, `test_parse_malformed_json`, `test_generate_review_with_mock` | Unit tests for Gemini review generator |
| `tests/test_schemas.py` | `test_function_node_creation`, `test_diff_hunk_with_affected_functions`, `test_pr_event_model`, `test_retrieval_result_model`, `test_review_comment_model`, `test_feedback_event_model`, `test_validation_errors_on_missing_required_fields` | Unit tests for domain schemas |
| `tests/test_storage.py` | `test_storage_paths_and_sanitization`, `test_missing_index_returns_none`, `test_save_and_retrieve_local_index`, `test_upload_missing_files_fails`, `test_upload_existing_files` | Unit tests for StorageClient |
| `tests/test_webhook_pipeline.py` | `test_webhook_invalid_signature`, `test_webhook_ignored_event`, `test_webhook_ignored_action`, `test_webhook_full_pipeline_success`, `test_process_pr_review_pipeline_direct` | Integration tests for webhook endpoint & pipeline |
| `tests/test_webhooks.py` | `test_valid_webhook_signature`, `test_invalid_webhook_signature`, `test_tampered_payload`, `test_missing_or_empty_header`, `test_missing_secret` | Unit tests for webhook HMAC verification |

---

## 📓 Colab Notebooks Registry

| File Path | Purpose | Inputs / Outputs |
| :--- | :--- | :--- |
| `colab/colab_indexer.ipynb` | Remote GPU-accelerated repository cloning, polyglot AST parsing, sentence transformer embedding, FAISS index creation, and cloud storage upload | **Input**: `TARGET_REPO` GitHub repo URL<br>**Output**: `faiss_index.bin`, `metadata.json` exported to Google Drive / GCS |
| `colab/colab_evaluator.ipynb` | Remote offline evaluation computing Precision@5, MRR, NDCG@10, and human review acceptance rates (+1/-1) | **Input**: `reactions.jsonl` feedback dataset<br>**Output**: Precision@5, MRR, NDCG@10, Acceptance & False Positive metrics |

