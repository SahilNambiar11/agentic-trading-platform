from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.queue.preview_queue import PreviewQueue
from app.services import preview_job_service


class RecordingSession:
    def __init__(self) -> None:
        self.rollback_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1

    def invalidate(self) -> None:
        raise AssertionError("A successful lock release must not invalidate the session.")


def test_submission_rolls_back_failed_transaction_before_releasing_lock(
    monkeypatch: Any,
) -> None:
    session = RecordingSession()
    released_after_rollback: list[bool] = []
    monkeypatch.setattr(
        preview_job_service,
        "acquire_preview_job_lock",
        lambda *args, **kwargs: True,
    )

    def fail_create(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise RuntimeError("insert failed")

    monkeypatch.setattr(preview_job_service, "create_job", fail_create)
    monkeypatch.setattr(
        preview_job_service,
        "release_preview_job_lock",
        lambda _session, _job_id: released_after_rollback.append(session.rollback_count == 1),
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        preview_job_service.submit_preview_job(
            cast(Session, session),
            cast(PreviewQueue, object()),
            user_id=uuid4(),
            strategy_text="Buy SPY.",
        )

    assert released_after_rollback == [True]
