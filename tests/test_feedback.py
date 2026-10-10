import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.reviews import generate_manual_review
from src.config import Settings
from src.main import create_app
from src.models.enums import ReviewSeverity
from src.models.schemas import FeedbackEvent, ReviewComment


@pytest.fixture
def temp_env(tmp_path: Path):
    feedback_file = tmp_path / "feedback" / "reactions.jsonl"
    cfg = Settings(_env_file=None, feedback_store_path=str(feedback_file), gemini_api_key="mock-key")
    with patch("src.api.feedback.get_settings", return_value=cfg), patch(
        "src.api.reviews.get_settings", return_value=cfg
    ), patch("src.config.get_settings", return_value=cfg):
        app = create_app()
        yield TestClient(app), feedback_file


def test_ingest_feedback_success(temp_env):
    client, feedback_file = temp_env

    payload = {
        "pr_number": 42,
        "comment_id": "comment-abc-123",
        "repo_full_name": "owner/repo",
        "reaction": "+1",
        "timestamp": "2026-10-10T12:00:00Z",
    }

    response = client.post("/feedback", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"

    assert feedback_file.exists()
    lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["pr_number"] == 42
    assert data["reaction"] == "+1"


def test_ingest_multiple_feedback(temp_env):
    client, feedback_file = temp_env

    for r in ["+1", "-1"]:
        payload = {
            "pr_number": 10,
            "comment_id": f"cid-{r}",
            "repo_full_name": "owner/repo",
            "reaction": r,
            "timestamp": "2026-10-10T12:05:00Z",
        }
        resp = client.post("/feedback", json=payload)
        assert resp.status_code == 200

    lines = feedback_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_manual_review_generate(temp_env):
    client, _ = temp_env

    diff_text = (
        "diff --git a/src/calc.py b/src/calc.py\n"
        "--- a/src/calc.py\n"
        "+++ b/src/calc.py\n"
        "@@ -1,3 +1,4 @@\n"
        "+def multiply(x, y): return x * y\n"
    )

    mock_reviewer = MagicMock()
    mock_reviewer.generate_review.return_value = [
        ReviewComment(
            file_path="src/calc.py",
            start_line=1,
            end_line=2,
            body="Add type hints for arguments.",
            severity=ReviewSeverity.INFO,
        )
    ]

    with patch("src.api.reviews.GeminiReviewer", return_value=mock_reviewer):
        req_payload = {
            "repo_full_name": "owner/repo",
            "pr_number": 5,
            "diff_text": diff_text,
            "post_to_github": False,
        }
        resp = client.post("/reviews/generate", json=req_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["pr_number"] == 5
        assert len(body["comments"]) == 1
        assert body["comments"][0]["body"] == "Add type hints for arguments."
        assert body["comments_posted"] == 0
        assert "processing_time_ms" in body
