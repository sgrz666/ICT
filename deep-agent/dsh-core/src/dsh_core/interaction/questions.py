"""User question seam and ask_user_question manager (@deepseek-ai/dsh-user-questions & @deepseek-ai/dsh-tool-ask-user).

Allows the agent to ask structured multiple-choice or free-text questions during
a step and logs the interaction in the session event stream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..session.state_machine import Session


class UserQuestion(BaseModel):
    """Structured question presented to the user."""

    question: str
    options: list[str] = Field(default_factory=list)
    allow_multiple: bool = False


class UserQuestionResponse(BaseModel):
    """User's answer to a structured question."""

    question: str
    selected_options: list[str]
    custom_text: str = ""


class UserQuestionManager:
    """Manages dispatching `ask_user_question` requests and logging answers."""

    def __init__(
        self,
        question_handler: Callable[[UserQuestion], UserQuestionResponse] | None = None,
    ):
        self.question_handler = question_handler

    def ask(
        self,
        session: Session,
        question: str,
        options: list[str] | None = None,
        allow_multiple: bool = False,
    ) -> UserQuestionResponse:
        """Present a question to the user (or select default option in headless mode)."""
        cleaned_q = question.strip()
        if not cleaned_q:
            raise ValueError("ask_user_question: question must be non-empty")

        opts = [o.strip() for o in (options or []) if o.strip()]
        q_obj = UserQuestion(
            question=cleaned_q,
            options=opts,
            allow_multiple=allow_multiple,
        )

        if self.question_handler is not None:
            response = self.question_handler(q_obj)
        else:
            default_pick = [opts[0]] if opts else ["Proceed with default"]
            response = UserQuestionResponse(
                question=cleaned_q,
                selected_options=default_pick,
                custom_text="(Headless auto-selected recommended option)",
            )

        session.append(
            "user/question",
            {
                "question": q_obj.model_dump(),
                "response": response.model_dump(),
            },
        )
        return response
