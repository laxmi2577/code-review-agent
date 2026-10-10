from typing import Optional
from pydantic import BaseModel, Field

from src.models.enums import ChangeType, Language, ReviewSeverity


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
        description="File paths of functions used as context for this comment",
    )


class FeedbackEvent(BaseModel):
    pr_number: int
    comment_id: str
    repo_full_name: str
    reaction: str  # "+1" or "-1"
    timestamp: str
