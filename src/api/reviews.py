import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.api.webhooks import get_index_manager, process_pr_review_pipeline
from src.config import Settings, get_settings
from src.core.ast_parser import ASTParser
from src.core.diff_parser import map_diff_to_functions, parse_unified_diff
from src.core.retriever import CodeRetriever
from src.core.reviewer import GeminiReviewer
from src.models.schemas import PREvent, ReviewComment
from src.services.github_client import GitHubClient
from src.services.index_manager import IndexManager

logger = logging.getLogger("codelens.reviews")
router = APIRouter(prefix="/reviews", tags=["Reviews"])


class ManualReviewRequest(BaseModel):
    repo_full_name: str = Field(description="Full GitHub repository name (e.g. owner/repo)")
    pr_number: int = Field(description="Pull request number")
    diff_text: Optional[str] = Field(default=None, description="Optional raw unified diff text if testing locally")
    commit_id: Optional[str] = Field(default=None, description="Target commit SHA")
    post_to_github: bool = Field(default=False, description="Whether to publish comments to GitHub PR")


class ManualReviewResponse(BaseModel):
    repo_full_name: str
    pr_number: int
    comments: list[ReviewComment]
    comments_posted: int
    processing_time_ms: float


def run_manual_review(
    req: ManualReviewRequest,
    settings: Optional[Settings] = None,
    index_mgr: Optional[IndexManager] = None,
    reviewer: Optional[GeminiReviewer] = None,
    gh_client: Optional[GitHubClient] = None,
) -> ManualReviewResponse:
    """Execute manual review logic with optional injectable dependencies."""
    start_time = time.perf_counter()

    cfg = settings or get_settings()
    mgr = index_mgr or get_index_manager()
    rev = reviewer or GeminiReviewer(settings=cfg)
    gh = gh_client or GitHubClient(settings=cfg)

    diff_content = req.diff_text
    commit_sha = req.commit_id

    # If diff_text is not supplied, fetch diff from GitHub API using GitHubClient
    if not diff_content:
        try:
            pull = gh.get_pull_request(req.repo_full_name, req.pr_number)
            if not commit_sha:
                commit_sha = pull.head.sha
            # Fetch unified diff
            diff_content = pull.get_issue_comments() # or diff
            # PyGithub pull.diff_url or pull.get_files()
            # For direct diff content, fetch through pull object or diff_url
            diff_content = getattr(pull, "diff_url", "")
        except Exception as e:
            logger.warning("Could not fetch remote PR details for %s#%d: %s", req.repo_full_name, req.pr_number, e)

    hunks = parse_unified_diff(diff_content) if diff_content else []

    # AST parsing and boundary correlation
    ast_parser = ASTParser()
    functions_by_file = {}
    for hunk in hunks:
        functions_by_file[hunk.file_path] = []

    hunks = map_diff_to_functions(hunks, functions_by_file)

    # Retrieval of codebase context
    retriever = CodeRetriever(index_manager=mgr)
    retrieval_results = retriever.retrieve_for_hunks(hunks)

    # Review comment generation via Gemini
    comments = rev.generate_review(hunks, retrieval_results)

    posted_count = 0
    if req.post_to_github and commit_sha and comments:
        posted_ids = gh.post_review_comments(
            repo_full_name=req.repo_full_name,
            pr_number=req.pr_number,
            commit_id=commit_sha,
            comments=comments,
        )
        posted_count = len(posted_ids)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    return ManualReviewResponse(
        repo_full_name=req.repo_full_name,
        pr_number=req.pr_number,
        comments=comments,
        comments_posted=posted_count,
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.post("/generate", response_model=ManualReviewResponse, status_code=status.HTTP_200_OK)
def generate_manual_review(req: ManualReviewRequest) -> ManualReviewResponse:
    """Trigger an on-demand code review for a PR, bypassing the webhook receiver."""
    return run_manual_review(req)

