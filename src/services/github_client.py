import logging
import time
from typing import Any

from github import Auth, Github, GithubException, RateLimitExceededException

from src.config import Settings, get_settings
from src.models.schemas import ReviewComment

logger = logging.getLogger("codelens.github")


class GitHubClient:
    """Wrapper around PyGithub for pull request diff retrieval, comments, and reaction tracking."""

    def __init__(
        self,
        settings: Settings | None = None,
        token: str | None = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        self.settings = settings or get_settings()
        self.token = token or self.settings.github_token
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        if self.token:
            auth = Auth.Token(self.token)
            self.gh = Github(auth=auth)
        else:
            logger.warning(
                "GitHubClient initialized without token. Unauthenticated rate limits will apply."
            )
            self.gh = Github()

    def get_pull_request(self, repo_full_name: str, pr_number: int):
        """Fetch repository and pull request instance with retry logic."""
        return self._execute_with_retry(
            lambda: self.gh.get_repo(repo_full_name).get_pull(pr_number)
        )

    def format_comment_body(self, comment: ReviewComment) -> str:
        """Format the markdown body for an inline review comment."""
        severity_badges = {
            "info": "💡 **Info**",
            "warning": "⚠️ **Warning**",
            "critical": "🚨 **Critical**",
        }
        badge = severity_badges.get(comment.severity.value, "🔍 **CodeLens**")
        parts = [
            f"{badge} (Lines {comment.start_line}–{comment.end_line})\n",
            comment.body,
        ]

        if comment.retrieved_context_refs:
            refs = ", ".join(f"`{r}`" for r in comment.retrieved_context_refs)
            parts.append(f"\n\n*Codebase context referenced from:* {refs}")

        return "\n".join(parts)

    def post_single_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_id: str,
        comment: ReviewComment,
    ) -> int | None:
        """Post a single review comment. Falls back to an issue comment if outside diff lines."""
        pull = self.get_pull_request(repo_full_name, pr_number)
        formatted_body = self.format_comment_body(comment)

        try:
            # Try posting as inline review comment on the commit diff
            created = self._execute_with_retry(
                lambda: pull.create_review_comment(
                    body=formatted_body,
                    commit_id=commit_id,
                    path=comment.file_path,
                    line=comment.end_line,
                )
            )
            logger.info(
                "Posted inline review comment %s on %s#%d", created.id, repo_full_name, pr_number
            )
            return created.id

        except GithubException as exc:
            # 422: Line is not part of the PR diff or invalid position
            if exc.status == 422:
                logger.warning(
                    "Inline review comment rejected by GitHub (422) for %s:%d. Falling back to issue comment.",
                    comment.file_path,
                    comment.end_line,
                )
                fallback_body = (
                    f"**[CodeLens Review]** on `{comment.file_path}` (lines {comment.start_line}–{comment.end_line}):\n\n"
                    f"{formatted_body}"
                )
                fallback_comment = self._execute_with_retry(
                    lambda: pull.create_issue_comment(fallback_body)
                )
                return fallback_comment.id

            logger.error("Failed to post comment to %s#%d: %s", repo_full_name, pr_number, exc)
            return None

    def post_review_comments(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_id: str,
        comments: list[ReviewComment],
    ) -> list[int]:
        """Post a batch of review comments to a pull request."""
        comment_ids: list[int] = []
        for comment in comments:
            cid = self.post_single_comment(repo_full_name, pr_number, commit_id, comment)
            if cid is not None:
                comment_ids.append(cid)
        return comment_ids

    def get_comment_reactions(self, repo_full_name: str, comment_id: int) -> list[dict[str, Any]]:
        """Fetch list of reactions on a review comment."""
        repo = self._execute_with_retry(lambda: self.gh.get_repo(repo_full_name))
        comment = self._execute_with_retry(lambda: repo.get_pull_review_comment(comment_id))
        reactions = self._execute_with_retry(lambda: list(comment.get_reactions()))
        return [{"content": r.content, "user": r.user.login} for r in reactions]

    def _execute_with_retry(self, operation):
        """Execute a PyGithub operation with exponential backoff on rate limits."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return operation()
            except RateLimitExceededException as exc:
                wait_time = self.backoff_factor * (2**attempt)
                logger.warning(
                    "GitHub rate limit hit on attempt %d. Backing off for %.1fs...",
                    attempt + 1,
                    wait_time,
                )
                time.sleep(wait_time)
                last_exception = exc
            except GithubException as exc:
                if exc.status == 403 and "rate limit" in str(exc.data).lower():
                    wait_time = self.backoff_factor * (2**attempt)
                    logger.warning(
                        "GitHub 403 rate limit on attempt %d. Backing off for %.1fs...",
                        attempt + 1,
                        wait_time,
                    )
                    time.sleep(wait_time)
                    last_exception = exc
                else:
                    raise

        if last_exception:
            raise last_exception
