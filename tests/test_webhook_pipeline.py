import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.webhooks import process_pr_review_pipeline
from src.config import Settings
from src.main import create_app
from src.models.enums import ReviewSeverity
from src.models.schemas import PREvent, ReviewComment


@pytest.fixture
def secret() -> str:
    return "webhook-test-secret"


@pytest.fixture
def test_client(secret: str):
    cfg = Settings(github_webhook_secret=secret, gemini_api_key="mock-key")
    with patch("src.api.webhooks.get_settings", return_value=cfg), patch(
        "src.config.get_settings", return_value=cfg
    ):
        app = create_app()
        yield TestClient(app)



def sign_payload(payload: dict, secret: str) -> tuple[bytes, str]:
    payload_bytes = json.dumps(payload).encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return payload_bytes, f"sha256={mac}"


def test_webhook_invalid_signature(test_client: TestClient):
    payload = {"action": "opened"}
    payload_bytes = json.dumps(payload).encode("utf-8")

    response = test_client.post(
        "/webhook/github",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=invalid_signature",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook signature"


def test_webhook_ignored_event(test_client: TestClient, secret: str):
    payload = {"zen": "Keep it logically awesome."}
    payload_bytes, signature = sign_payload(payload, secret)

    response = test_client.post(
        "/webhook/github",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_ignored_action(test_client: TestClient, secret: str):
    payload = {"action": "closed", "pull_request": {"number": 1}}
    payload_bytes, signature = sign_payload(payload, secret)

    response = test_client.post(
        "/webhook/github",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_full_pipeline_success(test_client: TestClient, secret: str):
    payload = {
        "action": "opened",
        "number": 42,
        "repository": {"full_name": "org/repo"},
        "pull_request": {
            "number": 42,
            "head": {"sha": "head123"},
            "base": {"sha": "base456"},
            "diff_url": "https://api.github.com/repos/org/repo/pulls/42.diff",
        },
        "sender": {"login": "octocat"},
    }
    payload_bytes, signature = sign_payload(payload, secret)

    diff_fixture = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -10,3 +10,4 @@ def calculate():\n"
        "+    return 42\n"
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get, patch(
        "src.api.webhooks.process_pr_review_pipeline"
    ) as mock_pipeline:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = diff_fixture
        mock_get.return_value = mock_resp

        mock_pipeline.return_value = [101]


        response = test_client.post(
            "/webhook/github",
            content=payload_bytes,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": signature,
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "accepted"
        assert body["pr_number"] == 42
        assert body["comments_posted"] == 1
        assert "job_id" in body


def test_process_pr_review_pipeline_direct():
    pr_event = PREvent(
        action="opened",
        pr_number=7,
        repo_full_name="org/test-repo",
        head_sha="head999",
        base_sha="base888",
        diff_url="",
        sender_login="tester",
    )

    diff_text = (
        "diff --git a/src/math.py b/src/math.py\n"
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+def add(a, b): return a + b\n"
    )

    mock_reviewer = MagicMock()
    mock_reviewer.generate_review.return_value = [
        ReviewComment(
            file_path="src/math.py",
            start_line=1,
            end_line=2,
            body="Consider type annotations for parameters.",
            severity=ReviewSeverity.INFO,
        )
    ]

    mock_gh = MagicMock()
    mock_gh.post_review_comments.return_value = [555]

    comment_ids = process_pr_review_pipeline(
        pr_event=pr_event,
        diff_text=diff_text,
        reviewer=mock_reviewer,
        gh_client=mock_gh,
    )

    assert comment_ids == [555]
    mock_reviewer.generate_review.assert_called_once()
    mock_gh.post_review_comments.assert_called_once()
