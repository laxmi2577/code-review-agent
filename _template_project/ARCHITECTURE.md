# 🏛️ Architecture & Technical Specification

---

## 1. Technology Stack

| Category | Technology | Rationale |
| :--- | :--- | :--- |
| **Runtime / Language** | Python 3.11+ | Ecosystem maturity for ML tooling, AST parsing, and API development |
| **API Framework** | FastAPI + Uvicorn | Async webhook handling, automatic OpenAPI docs, Pydantic integration |
| **AST Parsing** | Tree-sitter (py-tree-sitter) | Language-agnostic AST extraction; supports Python, TypeScript, JavaScript, Go, Java, Rust |
| **Git Operations** | GitPython | Clone, diff extraction, branch management for target repositories |
| **LLM Integration** | Google Gemini 2.0 Flash API | Review comment generation with retrieved context; zero local GPU load |
| **Embeddings** | CodeBERT (microsoft/codebert-base) | Function-level code embeddings; fine-tuned variants trained on Colab |
| **Vector Database** | FAISS (local dev) / Qdrant Cloud (production) | Similarity search on function-level embeddings |
| **Admin Dashboard** | Streamlit | Lightweight admin panel for index status, feedback metrics, config |
| **Data Validation** | Pydantic v2 | Strict schema enforcement for all API contracts and internal data flow |
| **Testing** | pytest + pytest-asyncio + httpx | Unit and integration tests for webhook handlers, parsers, retrieval |
| **GitHub Integration** | PyGithub + httpx | Webhook validation, PR comment posting, reaction event ingestion |

---

## 2. System Architecture — Three-Tier Decoupled Design

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        GITHUB PLATFORM                              │
│  PR Events (webhook) ──────────────┐    ┌── PR Comments (REST API)  │
│                                    │    │                           │
└────────────────────────────────────┼────┼───────────────────────────┘
                                     │    │
                                     ▼    ▲
┌─────────────────────────────────────────────────────────────────────┐
│              LOCAL CONTROL PLANE (Antigravity Host)                  │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ FastAPI       │  │ Diff Extractor│  │ Retrieval Engine         │ │
│  │ Webhook       │──│ + Tree-sitter │──│ (FAISS/Qdrant client)    │ │
│  │ Receiver      │  │ AST Parser    │  │ top-k similar functions  │ │
│  └──────────────┘  └───────────────┘  └──────────┬───────────────┘ │
│                                                   │                 │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────▼───────────────┐ │
│  │ Feedback      │  │ PR Comment    │  │ Review Generator         │ │
│  │ Collector     │  │ Poster        │◄─│ (Gemini API client)      │ │
│  │ (reactions)   │  │ (GitHub API)  │  │ diff + context → comment │ │
│  └──────┬───────┘  └───────────────┘  └──────────────────────────┘ │
│         │                                                           │
│  ┌──────▼───────┐  ┌───────────────┐                               │
│  │ Feedback     │  │ Streamlit     │                               │
│  │ Store (JSON) │  │ Admin Panel   │                               │
│  └──────────────┘  └───────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
                          │                        ▲
                          │ (index download)       │ (index upload)
                          ▼                        │
┌─────────────────────────────────────────────────────────────────────┐
│              CLOUD STORAGE (Google Drive / GCS — 5 TB)              │
│                                                                     │
│  📁 codelens-storage/                                               │
│  ├── indices/{repo_name}/faiss_index.bin    ← Vector indices        │
│  ├── indices/{repo_name}/metadata.json      ← Function metadata     │
│  ├── embeddings/{repo_name}/embeddings.npy  ← Raw embedding arrays  │
│  ├── datasets/feedback/reactions.jsonl      ← Human feedback data   │
│  ├── datasets/training/code_pairs.jsonl     ← Fine-tuning pairs     │
│  ├── checkpoints/{model_version}/           ← Fine-tuned weights    │
│  └── evaluations/{run_id}/                  ← Eval metrics & logs   │
└─────────────────────────────────────────────────────────────────────┘
                          ▲                        │
                          │ (clone repo,           │ (upload index,
                          │  generate embeddings)  │  checkpoints)
                          │                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│              REMOTE COMPUTE (Google Colab — T4/A100 GPU)            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Notebook: colab_indexer.ipynb                                │   │
│  │ • Clone target repo from GitHub                              │   │
│  │ • Parse all source files with Tree-sitter → function nodes   │   │
│  │ • Generate CodeBERT embeddings per function                  │   │
│  │ • Build FAISS index + metadata JSON                          │   │
│  │ • Upload index + embeddings to GCS/Drive                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Notebook: colab_evaluator.ipynb                              │   │
│  │ • Download feedback dataset from GCS                         │   │
│  │ • Compute retrieval metrics: precision@k, MRR, NDCG         │   │
│  │ • Compute review quality: acceptance rate, false positive %  │   │
│  │ • Generate evaluation report → upload to GCS                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ Notebook: colab_finetuner.ipynb (v2 — deferred)              │   │
│  │ • Fine-tune CodeBERT on domain-specific code pairs           │   │
│  │ • Fine-tune review quality classifier on feedback labels     │   │
│  │ • Export checkpoints to GCS                                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Directory Layout & Module Structure

```text
codelens/
├── _template_project/         # Blueprint & Context Engine Documentation
│   ├── AGENTS.md             # Hardware boundaries & compute offloading rules
│   ├── GEMINI.md             # Token preservation directives & workflow rules
│   ├── PROJECT_OVERVIEW.md   # Product spec, personas, features, non-goals
│   ├── ARCHITECTURE.md       # System design & API contracts
│   ├── TASK_LIST.md          # Sprint roadmap with [CURRENT FOCUS]
│   ├── CHANGELOG.md          # Delta memory — file modification log
│   ├── CODEBASE_MAP.md       # Symbol registry — function & class index
│   └── PROJECT_IDEAS.md      # Archived: 10 project proposals (selection complete)
│
├── pyproject.toml            # Project metadata, ruff config, pytest config
├── requirements.txt          # Pinned production dependencies
├── requirements-dev.txt      # Dev/test dependencies (pytest, httpx, ruff)
├── .env.example              # Template: GITHUB_WEBHOOK_SECRET, GEMINI_API_KEY, GCS_BUCKET
│
├── src/
│   ├── __init__.py
│   ├── main.py               # FastAPI app factory, router registration
│   ├── config.py             # Settings via pydantic-settings (env vars)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhooks.py       # POST /webhook/github — PR event handler
│   │   ├── reviews.py        # POST /reviews/generate — manual trigger
│   │   ├── feedback.py       # POST /feedback — reaction ingestion
│   │   └── health.py         # GET /health — readiness probe
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── diff_parser.py    # GitPython diff extraction + hunk mapping
│   │   ├── ast_parser.py     # Tree-sitter function/class node extraction
│   │   ├── retriever.py      # FAISS/Qdrant query client — top-k retrieval
│   │   └── reviewer.py       # Gemini API client — context → review comment
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py        # Pydantic models: PREvent, DiffHunk, FunctionNode, ReviewComment
│   │   └── enums.py          # ChangeType, Language, ReviewSeverity enums
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── github_client.py  # PyGithub wrapper: post comments, fetch reactions
│   │   ├── storage_client.py # GCS/Drive download/upload for indices
│   │   └── index_manager.py  # Local index lifecycle: load, query, refresh
│   │
│   └── utils/
│       ├── __init__.py
│       ├── security.py       # HMAC signature verification for webhooks
│       └── logging.py        # Structured JSON logging configuration
│
├── colab/
│   ├── colab_indexer.ipynb    # Embedding generation + FAISS index build
│   ├── colab_evaluator.ipynb  # Retrieval & review quality evaluation
│   └── colab_finetuner.ipynb  # (v2) Fine-tuning harness
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures: mock PR events, sample diffs
│   ├── test_webhooks.py      # Webhook HMAC validation, event parsing
│   ├── test_diff_parser.py   # Diff extraction correctness
│   ├── test_ast_parser.py    # Tree-sitter function extraction per language
│   ├── test_retriever.py     # FAISS query result validation
│   └── test_reviewer.py      # Gemini prompt construction, response parsing
│
├── .env.example              # Template: GITHUB_WEBHOOK_SECRET, GEMINI_API_KEY, GCS_BUCKET
├── requirements.txt          # Pinned production dependencies
├── requirements-dev.txt      # Dev/test dependencies (pytest, httpx, ruff)
└── pyproject.toml            # Project metadata, ruff config, pytest config
```

---

## 4. Data Models & Schemas

```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class Language(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    JAVA = "java"
    RUST = "rust"


class ReviewSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FunctionNode(BaseModel):
    file_path: str
    function_name: str
    class_name: Optional[str] = None
    language: Language
    start_line: int
    end_line: int
    code_snippet: str
    embedding_id: Optional[str] = None


class DiffHunk(BaseModel):
    file_path: str
    language: Language
    change_type: ChangeType
    old_start: int
    new_start: int
    new_end: int
    diff_content: str
    affected_functions: list[FunctionNode] = Field(default_factory=list)


class PREvent(BaseModel):
    action: str
    pr_number: int
    repo_full_name: str
    head_sha: str
    base_sha: str
    diff_url: str
    sender_login: str


class RetrievalResult(BaseModel):
    query_function: FunctionNode
    similar_functions: list[FunctionNode]
    similarity_scores: list[float]


class ReviewComment(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    body: str
    severity: ReviewSeverity
    retrieved_context_refs: list[str] = Field(
        default_factory=list,
        description="File paths of functions used as context for this comment"
    )


class FeedbackEvent(BaseModel):
    pr_number: int
    comment_id: str
    repo_full_name: str
    reaction: str  # "+1" or "-1"
    timestamp: str
```

---

## 5. API Endpoints & Contracts

| Method | Route | Description | Request Body | Response |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Readiness probe — confirms index loaded, Gemini API reachable | None | `{ "status": "ok", "index_loaded": true, "index_age_seconds": 3600 }` |
| `POST` | `/webhook/github` | GitHub webhook receiver for PR events | GitHub webhook JSON payload (validated via `X-Hub-Signature-256` header) | `{ "status": "accepted", "pr_number": 42, "job_id": "uuid" }` |
| `POST` | `/reviews/generate` | Manual review trigger (bypass webhook) | `{ "repo_full_name": "org/repo", "pr_number": 42 }` | `{ "comments": [ReviewComment], "processing_time_ms": 1200 }` |
| `POST` | `/feedback` | Ingest human reaction on AI comment | `FeedbackEvent` JSON | `{ "status": "recorded" }` |
| `GET` | `/index/status` | Index metadata — repo name, function count, last updated | None | `{ "repo": "org/repo", "function_count": 2450, "last_indexed": "2026-10-10T04:00:00Z" }` |
| `POST` | `/index/refresh` | Trigger index re-download from cloud storage | `{ "repo_full_name": "org/repo" }` | `{ "status": "refreshing", "estimated_seconds": 30 }` |

---

## 6. Supported Languages (Tree-sitter Grammars)

| Language | Tree-sitter Grammar Package | Function Query Pattern |
| :--- | :--- | :--- |
| Python | `tree-sitter-python` | `(function_definition name: (identifier) @name)` |
| TypeScript | `tree-sitter-typescript` | `(function_declaration name: (identifier) @name)` |
| JavaScript | `tree-sitter-javascript` | `(function_declaration name: (identifier) @name)` |
| Go | `tree-sitter-go` | `(function_declaration name: (identifier) @name)` |
| Java | `tree-sitter-java` | `(method_declaration name: (identifier) @name)` |
| Rust | `tree-sitter-rust` | `(function_item name: (identifier) @name)` |

---

## 7. Compute Boundary Enforcement (per AGENTS.md)

| Operation | Execution Location | Rationale |
| :--- | :--- | :--- |
| Webhook reception & HMAC validation | **Local** | Lightweight I/O, <1ms per request |
| Git diff extraction (GitPython) | **Local** | Text processing on small diff payloads |
| Tree-sitter AST parsing | **Local** | CPU-only, <100ms per file |
| FAISS index querying (top-k search) | **Local** | Pre-built index loaded into RAM (~200 MB for 50K functions) |
| Gemini API call (review generation) | **Local → Remote API** | API call only; no local GPU |
| GitHub API calls (post comments) | **Local → Remote API** | HTTP client calls |
| CodeBERT embedding generation (full repo) | **Colab (GPU)** | 50K functions × 768-dim embeddings requires GPU acceleration |
| FAISS index construction | **Colab** | Building index from 50K+ embeddings |
| Model fine-tuning (CodeBERT adapter) | **Colab (GPU)** | LoRA/adapter training on feedback data |
| Batch evaluation (precision@k, MRR) | **Colab** | Requires full embedding matrix operations |
| Index & checkpoint persistence | **GCS/Drive** | 5 TB tier; never stored on local 239 GB SSD |

---

## 8. Security & Safety Guidelines

- **Webhook Authentication**: All incoming GitHub webhooks are validated using HMAC-SHA256 signature verification against `GITHUB_WEBHOOK_SECRET`. Requests with invalid signatures are rejected with HTTP 401.
- **API Keys**: `GEMINI_API_KEY`, `GITHUB_APP_PRIVATE_KEY`, and `GCS_SERVICE_ACCOUNT_JSON` are stored in `.env` files, loaded via `pydantic-settings`, and never committed to version control.
- **Code Access**: The system only reads code from repositories the GitHub App is installed on. It never writes to source files — only posts review comments.
- **Data Privacy**: PR diffs sent to Gemini API may contain proprietary code. For production deployment, use Gemini API with data use controls or a private Vertex AI endpoint.
- **Rate Limiting**: GitHub API rate limits (5000 req/hour for authenticated apps) are tracked and respected with exponential backoff.
