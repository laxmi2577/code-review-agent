import json
import logging
import re

import google.generativeai as genai

from src.config import Settings, get_settings
from src.models.schemas import DiffHunk, RetrievalResult, ReviewComment

logger = logging.getLogger("codelens.reviewer")

REVIEWER_SYSTEM_PROMPT = """You are CodeLens, an expert automated code review agent.
You provide precise, actionable, and codebase-aware feedback on pull request diffs.

Review Guidelines:
1. Identify logical bugs, potential runtime errors, security vulnerabilities, and antipatterns.
2. Check for alignment with existing codebase patterns and architectural standards using the provided codebase context.
3. Keep feedback constructive, concise, and focused on modified or added lines.
4. Categorize each comment by severity: "info", "warning", or "critical".
5. Reference retrieved context files if they influenced your recommendations.
6. Return your review strictly as a valid JSON array of objects conforming to the ReviewComment schema:
[
  {
    "file_path": "string",
    "start_line": int,
    "end_line": int,
    "body": "string",
    "severity": "info" | "warning" | "critical",
    "retrieved_context_refs": ["string"]
  }
]
Do not wrap your output in conversational filler. Only output valid JSON.
"""


class GeminiReviewer:
    """Constructs codebase-aware prompts and invokes Gemini to generate PR review comments."""

    def __init__(
        self,
        settings: Settings | None = None,
        model_name: str = "gemini-1.5-flash",
    ):
        self.settings = settings or get_settings()
        self.model_name = model_name
        self._configured = False

        if self.settings.gemini_api_key:
            genai.configure(api_key=self.settings.gemini_api_key)
            self._configured = True
        else:
            logger.warning(
                "Gemini API key is not configured in settings. Calls will require mocked responses."
            )

    def build_prompt(
        self,
        diff_hunks: list[DiffHunk],
        retrieval_results: list[RetrievalResult],
    ) -> str:
        """Construct the prompt combining PR diff hunks and retrieved codebase context."""
        prompt_parts: list[str] = [
            "# PULL REQUEST REVIEW REQUEST\n",
            "## 1. PULL REQUEST DIFF HUNKS TO REVIEW\n",
        ]

        if not diff_hunks:
            prompt_parts.append("No diff hunks provided.\n")
        else:
            for idx, hunk in enumerate(diff_hunks, start=1):
                prompt_parts.append(
                    f"### Hunk {idx}: {hunk.file_path} ({hunk.change_type.value})\n"
                    f"- Language: {hunk.language.value}\n"
                    f"- New Line Range: {hunk.new_start} to {hunk.new_end}\n"
                    f"```\n{hunk.diff_content}\n```\n"
                )

        prompt_parts.append("\n## 2. RELEVANT CODEBASE CONTEXT (SIMILAR FUNCTIONS)\n")
        if not retrieval_results:
            prompt_parts.append("No related codebase context retrieved from vector index.\n")
        else:
            for res in retrieval_results:
                q_func = res.query_function
                prompt_parts.append(
                    f"### Context for modified function `{q_func.function_name}` in `{q_func.file_path}`:\n"
                )
                if not res.similar_functions:
                    prompt_parts.append("  (No similar functions found)\n")
                for sim, score in zip(res.similar_functions, res.similarity_scores):
                    prompt_parts.append(
                        f"  - **{sim.function_name}** in `{sim.file_path}` (similarity score: {score:.3f}):\n"
                        f"    ```\n    {sim.code_snippet.strip()}\n    ```\n"
                    )

        prompt_parts.append(
            "\n## 3. REQUIRED OUTPUT\n"
            "Produce a JSON array of `ReviewComment` objects analyzing the diff hunks above.\n"
        )

        return "\n".join(prompt_parts)

    def parse_review_response(self, raw_text: str) -> list[ReviewComment]:
        """Extract and validate ReviewComment objects from raw Gemini output."""
        cleaned = raw_text.strip()

        # Strip markdown code blocks if present
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini output as JSON: %s\nRaw output: %s", e, raw_text)
            return []

        if not isinstance(data, list):
            logger.error("Expected JSON list of review comments, got %s", type(data))
            return []

        comments: list[ReviewComment] = []
        for item in data:
            try:
                comment = ReviewComment.model_validate(item)
                comments.append(comment)
            except Exception as e:
                logger.warning("Skipping invalid review comment entry (%s): %s", item, e)

        return comments

    def generate_review(
        self,
        diff_hunks: list[DiffHunk],
        retrieval_results: list[RetrievalResult],
    ) -> list[ReviewComment]:
        """Call Gemini model with assembled prompt and return validated review comments."""
        if not self._configured:
            logger.error("GeminiReviewer called without configured GEMINI_API_KEY.")
            return []

        prompt = self.build_prompt(diff_hunks, retrieval_results)

        candidate_models = list(
            dict.fromkeys([self.model_name, "gemini-flash-latest", "gemini-2.5-flash", "gemini-1.5-flash"])
        )

        for model_id in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=model_id,
                    system_instruction=REVIEWER_SYSTEM_PROMPT,
                    generation_config={"response_mime_type": "application/json"},
                )
                response = model.generate_content(prompt)
                raw_text = response.text or ""
                return self.parse_review_response(raw_text)
            except Exception as e:
                logger.warning("Gemini generation with '%s' failed: %s. Trying fallback...", model_id, e)
                continue

        logger.error("All candidate Gemini models failed to generate review.")
        return []
