import pytest
from pydantic import ValidationError

from src.models.enums import ChangeType, Language, ReviewSeverity
from src.models.schemas import (
    DiffHunk,
    FeedbackEvent,
    FunctionNode,
    PREvent,
    RetrievalResult,
    ReviewComment,
)


def test_function_node_creation():
    node = FunctionNode(
        file_path="src/api/health.py",
        function_name="health_check",
        language=Language.PYTHON,
        start_line=10,
        end_line=25,
        code_snippet="def health_check(): return {'status': 'ok'}",
    )
    assert node.class_name is None
    assert node.embedding_id is None
    assert node.function_name == "health_check"
    assert node.language == Language.PYTHON


def test_diff_hunk_with_affected_functions():
    func = FunctionNode(
        file_path="src/main.py",
        function_name="create_app",
        language=Language.PYTHON,
        start_line=1,
        end_line=20,
        code_snippet="def create_app(): pass",
    )
    hunk = DiffHunk(
        file_path="src/main.py",
        language=Language.PYTHON,
        change_type=ChangeType.MODIFIED,
        old_start=5,
        new_start=5,
        new_end=15,
        diff_content="@@ -5,5 +5,10 @@",
        affected_functions=[func],
    )
    assert len(hunk.affected_functions) == 1
    assert hunk.affected_functions[0].function_name == "create_app"


def test_pr_event_model():
    event = PREvent(
        action="opened",
        pr_number=42,
        repo_full_name="octocat/Hello-World",
        head_sha="6dcb09b5b57875f334f61aebed695e2e4193db5e",
        base_sha="0000000000000000000000000000000000000000",
        diff_url="https://github.com/octocat/Hello-World/pull/42.diff",
        sender_login="octocat",
    )
    assert event.pr_number == 42
    assert event.action == "opened"


def test_retrieval_result_model():
    query_fn = FunctionNode(
        file_path="src/query.py",
        function_name="find_items",
        language=Language.PYTHON,
        start_line=1,
        end_line=10,
        code_snippet="def find_items(): pass",
    )
    sim_fn = FunctionNode(
        file_path="src/repo.py",
        function_name="batch_items",
        language=Language.PYTHON,
        start_line=20,
        end_line=30,
        code_snippet="def batch_items(): pass",
    )
    res = RetrievalResult(
        query_function=query_fn,
        similar_functions=[sim_fn],
        similarity_scores=[0.89],
    )
    assert len(res.similar_functions) == 1
    assert res.similarity_scores[0] == 0.89


def test_review_comment_model():
    comment = ReviewComment(
        file_path="src/core/parser.py",
        start_line=45,
        end_line=50,
        body="Consider batch fetching instead of single loop queries.",
        severity=ReviewSeverity.WARNING,
        retrieved_context_refs=["src/core/batch_parser.py"],
    )
    assert comment.severity == ReviewSeverity.WARNING
    assert comment.retrieved_context_refs == ["src/core/batch_parser.py"]


def test_feedback_event_model():
    fb = FeedbackEvent(
        pr_number=101,
        comment_id="c_987",
        repo_full_name="org/repo",
        reaction="+1",
        timestamp="2026-10-10T12:00:00Z",
    )
    assert fb.reaction == "+1"
    assert fb.pr_number == 101


def test_validation_errors_on_missing_required_fields():
    with pytest.raises(ValidationError):
        FunctionNode(
            file_path="test.py",
            # missing function_name, language, start_line, end_line, code_snippet
        )
