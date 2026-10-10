import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.config import get_settings
from src.models.schemas import FeedbackEvent

logger = logging.getLogger("codelens.feedback")
router = APIRouter(prefix="/feedback", tags=["Feedback"])


class FeedbackResponse(BaseModel):
    status: str
    message: str | None = None


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_200_OK)
def ingest_feedback(event: FeedbackEvent) -> FeedbackResponse:
    """Ingest developer reaction (+1 or -1) on a CodeLens PR comment.

    Appends the event as a JSON line to the persistent reactions store (feedback.jsonl).
    """
    cfg = get_settings()
    store_path = Path(cfg.feedback_store_path)

    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        record = event.model_dump()

        with open(store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        logger.info(
            "Recorded feedback: PR #%d, comment %s, reaction '%s'",
            event.pr_number,
            event.comment_id,
            event.reaction,
        )
        return FeedbackResponse(status="recorded")

    except Exception as e:
        logger.error("Failed to append feedback event: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback event",
        )
