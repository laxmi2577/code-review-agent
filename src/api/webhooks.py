import json
import logging
import uuid

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from src.config import Settings, get_settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import extract_diff_from_repo, map_diff_to_functions, parse_unified_diff
from src.core.retriever import CodeRetriever
from src.core.reviewer import GeminiReviewer
from src.models.schemas import PREvent, ReviewComment
from src.services.github_client import GitHubClient
from src.services.index_manager import IndexManager
from src.utils.security import verify_webhook_signature

logger = logging.getLogger("codelens.webhooks")
router = APIRouter(prefix="/webhook", tags=["Webhooks"])

# Singleton or injectable services
_index_manager: IndexManager | None = None


def get_index_manager() -> IndexManager:
    global _index_manager
    if _index_manager is None:
        _index_manager = IndexManager()
        # Attempt initial load
        _index_manager.load_index()
    return _index_manager


class WebhookResponse(BaseModel):
    status: str
    pr_number: int | None = None
    job_id: str | None = None
    comments_posted: int | None = None
    message: str | None = None


def process_pr_review_pipeline(
    pr_event: PREvent,
    diff_text: str | None = None,
    repo_path: str | None = None,
    settings: Settings | None = None,
    index_mgr: IndexManager | None = None,
    reviewer: GeminiReviewer | None = None,
    gh_client: GitHubClient | None = None,
) -> list[int]:
    """Execute the end-to-end PR review pipeline.

    Stages:
    1. Extract diff hunks (from provided diff_text or local git repo)
    2. Parse AST function nodes and map line spans to diff hunks
    3. Retrieve similar codebase functions from FAISS vector index
    4. Call Gemini LLM to generate structured review comments
    5. Post inline review comments via GitHub client
    """
    settings = settings or get_settings()
    index_mgr = index_mgr or get_index_manager()
    reviewer = reviewer or GeminiReviewer(settings=settings)
    gh_client = gh_client or GitHubClient(settings=settings)

    # Stage 1: Extract Diffs
    hunks = []
    if diff_text:
        hunks = parse_unified_diff(diff_text)
    elif repo_path:
        try:
            hunks = extract_diff_from_repo(repo_path, pr_event.base_sha, pr_event.head_sha)
        except Exception as e:
            logger.warning("Failed to extract git diff from repo %s: %s", repo_path, e)

    if not hunks:
        logger.info(
            "No parseable diff hunks for PR #%d in %s", pr_event.pr_number, pr_event.repo_full_name
        )
        return []

    # Stage 2: AST Parsing & Diff-to-AST Mapping
    ast_parser = ASTParser()
    functions_by_file = {}
    for hunk in hunks:
        if hunk.file_path not in functions_by_file:
            # If repo_path is available, parse file content from disk
            if repo_path:
                try:
                    full_p = f"{repo_path}/{hunk.file_path}"
                    with open(full_p, encoding="utf-8") as f:
                        code = f.read()
                    nodes = ast_parser.extract_function_nodes(code, hunk.file_path, hunk.language)
                    functions_by_file[hunk.file_path] = nodes
                except Exception as e:
                    logger.debug("Could not parse file %s: %s", hunk.file_path, e)
            else:
                functions_by_file[hunk.file_path] = []

    hunks = map_diff_to_functions(hunks, functions_by_file)

    # Stage 3: Code Retrieval
    retriever = CodeRetriever(index_manager=index_mgr)
    retrieval_results = retriever.retrieve_for_hunks(hunks)

    # Stage 4: Gemini Review Generation
    comments: list[ReviewComment] = reviewer.generate_review(hunks, retrieval_results)
    if not comments:
        logger.info("No review comments generated for PR #%d", pr_event.pr_number)
        return []

    # Stage 5: GitHub Comment Posting
    comment_ids = gh_client.post_review_comments(
        repo_full_name=pr_event.repo_full_name,
        pr_number=pr_event.pr_number,
        commit_id=pr_event.head_sha,
        comments=comments,
    )
    logger.info("Successfully posted %d comments on PR #%d", len(comment_ids), pr_event.pr_number)
    return comment_ids


@router.post("/github", response_model=WebhookResponse, status_code=status.HTTP_200_OK)
async def github_webhook_endpoint(
    request: Request,
    x_github_event: str | None = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> WebhookResponse:
    """Receive and process GitHub webhook notifications."""
    settings = get_settings()
    body_bytes = await request.body()

    # Verify HMAC signature
    if not verify_webhook_signature(
        body_bytes, x_hub_signature_256 or "", settings.github_webhook_secret
    ):
        logger.warning("Rejected webhook: invalid HMAC signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # Filter events: Only process pull_request
    if x_github_event != "pull_request":
        logger.info("Ignoring non-PR GitHub event: %s", x_github_event)
        return WebhookResponse(status="ignored", message=f"Event {x_github_event} ignored")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    action = payload.get("action")
    if action not in ["opened", "synchronize", "reopened"]:
        logger.info("Ignoring PR action: %s", action)
        return WebhookResponse(status="ignored", message=f"Action '{action}' ignored")

    pr_dict = payload.get("pull_request", {})
    repo_dict = payload.get("repository", {})

    pr_event = PREvent(
        action=action,
        pr_number=payload.get("number", pr_dict.get("number", 0)),
        repo_full_name=repo_dict.get("full_name", ""),
        head_sha=pr_dict.get("head", {}).get("sha", ""),
        base_sha=pr_dict.get("base", {}).get("sha", ""),
        diff_url=pr_dict.get("diff_url", ""),
        sender_login=payload.get("sender", {}).get("login", ""),
    )

    job_id = str(uuid.uuid4())
    logger.info(
        "Processing PR event: %s #%d (job: %s)", pr_event.repo_full_name, pr_event.pr_number, job_id
    )

    # Fetch diff text from diff_url if available
    diff_text = None
    if pr_event.diff_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(pr_event.diff_url)
                if resp.status_code == 200:
                    diff_text = resp.text
        except Exception as e:
            logger.warning("Could not fetch diff from %s: %s", pr_event.diff_url, e)

    posted_ids = process_pr_review_pipeline(pr_event=pr_event, diff_text=diff_text)

    return WebhookResponse(
        status="accepted",
        pr_number=pr_event.pr_number,
        job_id=job_id,
        comments_posted=len(posted_ids),
    )
