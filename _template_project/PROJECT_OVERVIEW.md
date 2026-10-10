# 🎯 Project Overview & Mastermind Specification

---

## 1. Project Identity & Purpose
- **Project Name**: CodeLens — Retrieval-Augmented Code Review Agent with Codebase-Aware Context
- **Version**: 1.0.0
- **Summary**: CodeLens is a production-grade code review assistant that understands a repository's architectural patterns, testing conventions, and historical bug patterns. Unlike existing tools that analyze PRs in isolation, CodeLens retrieves semantically similar code from the codebase's vector index to provide context-aware review comments. The system enforces a decoupled architecture: FastAPI webhook receiver and AST-aware diff parsing run locally (control plane), while embedding generation, batch re-indexing, and fine-tuning execute on Google Colab (compute plane), with FAISS/Qdrant indices and evaluation artifacts persisted on Google Drive/GCS (storage tier).

---

## 2. Core User Personas & Use Cases

1. **Engineering Lead / Tech Lead**:
   - Target User Profile: Senior engineer responsible for code quality across 3–8 repositories with 100K–500K+ LOC.
   - Primary Goal: Reduce review cycle time from 45 min/PR to <15 min/PR by surfacing architecturally relevant context automatically.
   - Pain Point Addressed: Reviewers unfamiliar with specific modules approve structurally inconsistent code (e.g., N+1 queries, missing error handling patterns, violating established abstractions) because they lack surrounding codebase context.

2. **Individual Contributor (IC) Reviewer**:
   - Target User Profile: Mid-level engineer reviewing 5–10 PRs/week across unfamiliar modules.
   - Primary Goal: Receive AI-generated review suggestions grounded in actual codebase patterns — not generic linting rules — so they can approve/reject with confidence.
   - Pain Point Addressed: Spending 30+ minutes reading surrounding code in unfamiliar modules before writing a meaningful review comment.

3. **Junior Engineer (PR Author)**:
   - Target User Profile: Engineer with <1 year on the team, submitting PRs into established codebases.
   - Primary Goal: Receive immediate feedback on architectural deviations before human reviewers engage, reducing review round-trips from 3–4 to 1–2.
   - Pain Point Addressed: Unknowingly violating team conventions (wrong abstraction layer, inconsistent error handling, missing batch patterns) and discovering it only after human review delays.

---

## 3. Key Features & Acceptance Criteria

- [ ] **F1 — GitHub Webhook Receiver**: FastAPI endpoint receives `pull_request.opened` and `pull_request.synchronize` events, validates HMAC signatures, extracts diff payload. **Pass**: Webhook processes a real GitHub PR event end-to-end within 5 seconds.
- [ ] **F2 — AST-Aware Diff Parsing**: Tree-sitter parses changed files into function-level AST nodes. Diff hunks are mapped to specific functions/classes, not raw line ranges. **Pass**: Given a PR touching 3 files, output is a structured list of `{file, function_name, change_type, code_snippet}` objects validated against Pydantic schema.
- [ ] **F3 — Codebase Vector Index**: Function-level embeddings generated via CodeBERT (on Colab) are stored in FAISS/Qdrant. Retrieval returns top-k architecturally similar functions for each changed function in a PR. **Pass**: For a query function, retrieval returns ≥3 functions from the same architectural layer with cosine similarity >0.75.
- [ ] **F4 — Context-Aware Review Generation**: Gemini API receives the PR diff + retrieved similar functions as context and generates review comments. **Pass**: Generated comments reference specific patterns from the retrieved context (e.g., "Other functions in this module use batch fetching — see `fetch_users_batch()` at L45").
- [ ] **F5 — PR Comment Posting**: Review comments are posted as inline GitHub PR review comments via the GitHub REST API. **Pass**: Comments appear on the correct file and line range in the GitHub PR UI.
- [ ] **F6 — Human Feedback Loop**: Reviewers can react (👍/👎) to AI comments. Reactions are collected and exported as a labeled dataset for fine-tuning the review quality classifier on Colab. **Pass**: Feedback events are stored in structured JSON with PR ID, comment ID, reaction, and timestamp.

---

## 4. Scope & Boundaries (Non-Goals)

To prevent token waste and agent drift, the following items are strictly **OUT OF SCOPE** for v1.0:

- ❌ Do NOT build: Real-time IDE integration (VS Code extension, JetBrains plugin) — deferred to v2.
- ❌ Do NOT build: Multi-repository cross-referencing (analyzing dependencies across separate repos) — single-repo scope only for v1.
- ❌ Do NOT build: Automated PR approval or merge — system is advisory only, never auto-approves.
- ❌ Do NOT build: Custom LLM fine-tuning for review generation — v1 uses Gemini API zero-shot with retrieved context; fine-tuning is a v2 optimization.
- ❌ Do NOT build: GitLab/Bitbucket support — GitHub only for v1; other platforms deferred.
- ❌ Do NOT build: Local GPU inference or local embedding generation — all heavy compute runs on Colab per AGENTS.md.
- ❌ Do NOT build: User authentication/authorization system — v1 operates as a single-tenant service with GitHub App credentials.
- ❌ Do NOT build: Web UI dashboard — v1 is API-first + Streamlit admin panel only; no custom frontend.

---

## 5. Success Metrics

| Metric | Target | Measurement Method |
| :--- | :--- | :--- |
| Review comment acceptance rate (👍 / total) | ≥40% within first 30 days | Tracked via GitHub reaction webhook events |
| Retrieval relevance (precision@5) | ≥0.70 | Offline evaluation on labeled function-pair dataset |
| PR processing latency (webhook → comments posted) | <30 seconds for PRs with ≤10 changed files | FastAPI request timing middleware |
| False positive rate (👎 / total) | ≤25% | Tracked via feedback loop |
| Codebase index freshness | Re-indexed within 1 hour of merge to main | Colab scheduler + index timestamp comparison |
| 100% adherence to `CODEBASE_MAP.md` and `CHANGELOG.md` tracking rules | Continuous | Agent self-audit per GEMINI.md directives |
