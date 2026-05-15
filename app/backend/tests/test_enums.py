import pytest
from app.backend.enums import TaskStatus, SessionStatus, FieldStatus


class TestTaskStatus:
    def test_member_values(self):
        assert TaskStatus.CAPTURING.value == "capturing"
        assert TaskStatus.UPLOADED.value == "uploaded"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.READY_FOR_REVIEW.value == "ready_for_review"
        assert TaskStatus.CONFIRMED.value == "confirmed"
        assert TaskStatus.EXPORTED.value == "exported"
        assert TaskStatus.FAILED.value == "failed"

    def test_task_status_uses_capturing_as_business_start(self):
        assert TaskStatus.CAPTURING.value == "capturing"
        assert [item.value for item in TaskStatus.allowed_transitions("capturing")] == [
            "uploaded",
            "failed",
        ]

    def test_revision_transitions_return_to_capturing_except_processing(self):
        assert TaskStatus.is_valid_transition("uploaded", "capturing")
        assert TaskStatus.is_valid_transition("ready_for_review", "capturing")
        assert TaskStatus.is_valid_transition("confirmed", "capturing")
        assert TaskStatus.is_valid_transition("exported", "capturing")
        assert TaskStatus.is_valid_transition("failed", "capturing")
        assert not TaskStatus.is_valid_transition("processing", "capturing")

    def test_allowed_transitions_from_capturing(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.CAPTURING)
        assert TaskStatus.UPLOADED in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 2

    def test_allowed_transitions_from_uploaded(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.UPLOADED)
        assert TaskStatus.PROCESSING in targets
        assert TaskStatus.CAPTURING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 3

    def test_allowed_transitions_from_ready_for_review(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.READY_FOR_REVIEW)
        assert TaskStatus.CONFIRMED in targets
        assert TaskStatus.PROCESSING in targets
        assert TaskStatus.CAPTURING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 4

    def test_allowed_transitions_from_confirmed(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.CONFIRMED)
        assert TaskStatus.EXPORTED in targets
        assert TaskStatus.CAPTURING in targets
        assert len(targets) == 2

    def test_allowed_transitions_from_exported(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.EXPORTED)
        assert TaskStatus.CAPTURING in targets
        assert len(targets) == 1

    def test_allowed_transitions_from_failed(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.FAILED)
        assert TaskStatus.PROCESSING in targets
        assert TaskStatus.CAPTURING in targets
        assert len(targets) == 2

    def test_valid_transition_returns_true(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CAPTURING, TaskStatus.UPLOADED) is True
        assert TaskStatus.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.FAILED) is True
        assert TaskStatus.is_valid_transition(TaskStatus.FAILED, TaskStatus.PROCESSING) is True
        assert TaskStatus.is_valid_transition(TaskStatus.FAILED, TaskStatus.CAPTURING) is True
        assert TaskStatus.is_valid_transition(TaskStatus.CONFIRMED, TaskStatus.EXPORTED) is True
        assert TaskStatus.is_valid_transition(TaskStatus.CONFIRMED, TaskStatus.CAPTURING) is True
        assert TaskStatus.is_valid_transition(TaskStatus.EXPORTED, TaskStatus.CAPTURING) is True

    def test_invalid_transition_returns_false(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CAPTURING, TaskStatus.EXPORTED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.EXPORTED, TaskStatus.CONFIRMED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.CONFIRMED, TaskStatus.PROCESSING) is False
        assert TaskStatus.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.CAPTURING) is False

    def test_allowed_transitions_with_string_arg(self):
        targets = TaskStatus.allowed_transitions("capturing")
        assert TaskStatus.UPLOADED in targets


class TestSessionStatus:
    def test_member_values(self):
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.EXPIRED.value == "expired"
        assert SessionStatus.LOCKED.value == "locked"
        assert SessionStatus.CANCELLED.value == "cancelled"

    def test_allowed_transitions_from_active(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.ACTIVE)
        assert SessionStatus.LOCKED in targets
        assert SessionStatus.CANCELLED in targets
        assert SessionStatus.EXPIRED in targets
        assert len(targets) == 3

    def test_session_unlock_transition_is_locked_to_active(self):
        assert SessionStatus.is_valid_transition("locked", "active")
        assert not SessionStatus.is_valid_transition("cancelled", "active")
        assert not SessionStatus.is_valid_transition("expired", "active")

    def test_allowed_transitions_from_locked(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.LOCKED)
        assert SessionStatus.ACTIVE in targets
        assert len(targets) == 1

    def test_allowed_transitions_from_expired(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.EXPIRED)
        assert targets == []

    def test_allowed_transitions_from_cancelled(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.CANCELLED)
        assert targets == []

    def test_valid_transition(self):
        assert SessionStatus.is_valid_transition(SessionStatus.ACTIVE, SessionStatus.LOCKED) is True
        assert SessionStatus.is_valid_transition(SessionStatus.ACTIVE, SessionStatus.CANCELLED) is True
        assert SessionStatus.is_valid_transition(SessionStatus.LOCKED, SessionStatus.ACTIVE) is True


class TestFieldStatus:
    def test_member_values(self):
        assert FieldStatus.UNREVIEWED.value == "unreviewed"
        assert FieldStatus.CONFIRMED.value == "confirmed"
        assert FieldStatus.MODIFIED.value == "modified"
        assert FieldStatus.SUSPICIOUS.value == "suspicious"
        assert FieldStatus.EMPTY.value == "empty"

    def test_confirmed_empty_field_status_exists(self):
        assert FieldStatus.CONFIRMED_EMPTY.value == "confirmed_empty"
