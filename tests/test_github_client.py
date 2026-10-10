from unittest.mock import MagicMock, patch

import pytest
from github import GithubException, RateLimitExceededException

from src.models.enums import ReviewSeverity
from src.models.schemas import ReviewComment
from src.services.github_client import GitHubClient


@pytest.fixture
def sample_comment() -> ReviewComment:
    return ReviewComment(
        file_path="src/service.py",
        start_line=10,
        end_line=15,
        body="Consider catching specific exception instead of Exception.",
        severity=ReviewSeverity.WARNING,
        retrieved_context_refs=["src/utils/errors.py"],
    )


def test_format_comment_body(sample_comment: ReviewComment):
    client = GitHubClient(token="mock-token")
    body = client.format_comment_body(sample_comment)

    assert "⚠️ **Warning**" in body
    assert "Lines 10–15" in body
    assert "Consider catching specific exception" in body
    assert "`src/utils/errors.py`" in body


def test_post_single_comment_inline_success(sample_comment: ReviewComment):
    client = GitHubClient(token="mock-token")

    mock_pull = MagicMock()
    mock_comment = MagicMock()
    mock_comment.id = 9999
    mock_pull.create_review_comment.return_value = mock_comment

    with patch.object(client, "get_pull_request", return_value=mock_pull):
        cid = client.post_single_comment("owner/repo", 42, "sha123", sample_comment)

        assert cid == 9999
        mock_pull.create_review_comment.assert_called_once()
        mock_pull.create_issue_comment.assert_not_called()


def test_post_single_comment_fallback_on_422(sample_comment: ReviewComment):
    client = GitHubClient(token="mock-token")

    mock_pull = MagicMock()
    # 422 indicates line is not in PR diff
    err = GithubException(status=422, data={"message": "Validation Failed"}, headers=None)
    mock_pull.create_review_comment.side_effect = err

    mock_issue_comment = MagicMock()
    mock_issue_comment.id = 8888
    mock_pull.create_issue_comment.return_value = mock_issue_comment

    with patch.object(client, "get_pull_request", return_value=mock_pull):
        cid = client.post_single_comment("owner/repo", 42, "sha123", sample_comment)

        assert cid == 8888
        mock_pull.create_issue_comment.assert_called_once()


def test_post_review_comments_batch(sample_comment: ReviewComment):
    client = GitHubClient(token="mock-token")

    with patch.object(client, "post_single_comment", return_value=101):
        ids = client.post_review_comments(
            "owner/repo", 42, "sha123", [sample_comment, sample_comment]
        )
        assert ids == [101, 101]


def test_retry_on_rate_limit(sample_comment: ReviewComment):
    client = GitHubClient(token="mock-token", max_retries=2, backoff_factor=0.01)

    mock_op = MagicMock()
    mock_op.side_effect = [
        RateLimitExceededException(
            status=403, data={"message": "Rate limit exceeded"}, headers=None
        ),
        "success_result",
    ]

    result = client._execute_with_retry(mock_op)
    assert result == "success_result"
    assert mock_op.call_count == 2
