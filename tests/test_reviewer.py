import json
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings
from src.core.reviewer import GeminiReviewer
from src.models.enums import ChangeType, Language, ReviewSeverity
from src.models.schemas import DiffHunk, FunctionNode, RetrievalResult


@pytest.fixture
def sample_diff_hunk() -> DiffHunk:
    return DiffHunk(
        file_path="src/auth.py",
        language=Language.PYTHON,
        change_type=ChangeType.MODIFIED,
        old_start=10,
        new_start=10,
        new_end=15,
        diff_content="+ def verify_user(user, pwd):\n+     if not user: return False",
    )


@pytest.fixture
def sample_retrieval_result() -> RetrievalResult:
    q = FunctionNode(
        file_path="src/auth.py",
        function_name="verify_user",
        language=Language.PYTHON,
        start_line=10,
        end_line=15,
        code_snippet="def verify_user(user, pwd): ...",
    )
    sim = FunctionNode(
        file_path="src/security.py",
        function_name="validate_credentials",
        language=Language.PYTHON,
        start_line=20,
        end_line=30,
        code_snippet="def validate_credentials(u, p):\n    # secure timing comparison\n    pass",
    )
    return RetrievalResult(
        query_function=q,
        similar_functions=[sim],
        similarity_scores=[0.895],
    )


def test_build_prompt_structure(
    sample_diff_hunk: DiffHunk, sample_retrieval_result: RetrievalResult
):
    reviewer = GeminiReviewer(settings=Settings(gemini_api_key="mock-key"))
    prompt = reviewer.build_prompt([sample_diff_hunk], [sample_retrieval_result])

    assert "PULL REQUEST DIFF HUNKS TO REVIEW" in prompt
    assert "src/auth.py" in prompt
    assert "verify_user" in prompt
    assert "src/security.py" in prompt
    assert "validate_credentials" in prompt
    assert "0.895" in prompt


def test_parse_clean_json_response():
    reviewer = GeminiReviewer(settings=Settings(gemini_api_key="mock-key"))
    raw_json = json.dumps(
        [
            {
                "file_path": "src/auth.py",
                "start_line": 10,
                "end_line": 12,
                "body": "Use constant time comparison for passwords.",
                "severity": "critical",
                "retrieved_context_refs": ["src/security.py"],
            }
        ]
    )

    comments = reviewer.parse_review_response(raw_json)
    assert len(comments) == 1
    assert comments[0].file_path == "src/auth.py"
    assert comments[0].severity == ReviewSeverity.CRITICAL
    assert comments[0].retrieved_context_refs == ["src/security.py"]


def test_parse_markdown_wrapped_json():
    reviewer = GeminiReviewer(settings=Settings(gemini_api_key="mock-key"))
    wrapped = (
        "```json\n"
        "[\n"
        '  {"file_path": "src/main.py", "start_line": 5, "end_line": 6, '
        '   "body": "Missing docstring", "severity": "info"}\n'
        "]\n"
        "```"
    )

    comments = reviewer.parse_review_response(wrapped)
    assert len(comments) == 1
    assert comments[0].file_path == "src/main.py"
    assert comments[0].severity == ReviewSeverity.INFO


def test_parse_malformed_json():
    reviewer = GeminiReviewer(settings=Settings(gemini_api_key="mock-key"))
    comments = reviewer.parse_review_response("Not valid JSON {[]}")
    assert comments == []


def test_generate_review_with_mock():
    reviewer = GeminiReviewer(settings=Settings(gemini_api_key="mock-key"))

    mock_resp = MagicMock()
    mock_resp.text = json.dumps(
        [
            {
                "file_path": "src/foo.py",
                "start_line": 1,
                "end_line": 3,
                "body": "Potential NoneType dereference",
                "severity": "warning",
            }
        ]
    )

    with patch("google.generativeai.GenerativeModel") as mock_model_cls:
        instance = mock_model_cls.return_value
        instance.generate_content.return_value = mock_resp

        comments = reviewer.generate_review([], [])
        assert len(comments) == 1
        assert comments[0].body == "Potential NoneType dereference"
