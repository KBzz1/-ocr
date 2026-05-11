import pytest
from app.backend.enums import TaskStatus, SessionStatus, FieldStatus


class TestTaskStatus:
    def test_member_values(self):
        assert TaskStatus.CREATED.value == "created"
        assert TaskStatus.UPLOADING.value == "uploading"
        assert TaskStatus.UPLOADED.value == "uploaded"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.READY_FOR_REVIEW.value == "ready_for_review"
        assert TaskStatus.CONFIRMED.value == "confirmed"
        assert TaskStatus.EXPORTED.value == "exported"
        assert TaskStatus.FAILED.value == "failed"

    def test_allowed_transitions_from_created(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.CREATED)
        assert TaskStatus.UPLOADING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 2

    def test_allowed_transitions_from_ready_for_review(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.READY_FOR_REVIEW)
        assert TaskStatus.CONFIRMED in targets
        assert TaskStatus.PROCESSING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 3

    def test_allowed_transitions_from_exported_is_empty(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.EXPORTED)
        assert targets == []

    def test_allowed_transitions_from_failed(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.FAILED)
        assert TaskStatus.PROCESSING in targets
        assert len(targets) == 1

    def test_valid_transition_returns_true(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CREATED, TaskStatus.UPLOADING) is True
        assert TaskStatus.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.FAILED) is True
        assert TaskStatus.is_valid_transition(TaskStatus.FAILED, TaskStatus.PROCESSING) is True

    def test_invalid_transition_returns_false(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CREATED, TaskStatus.EXPORTED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.EXPORTED, TaskStatus.CREATED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.CONFIRMED, TaskStatus.CREATED) is False

    def test_allowed_transitions_with_string_arg(self):
        targets = TaskStatus.allowed_transitions("created")
        assert TaskStatus.UPLOADING in targets


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

    def test_allowed_transitions_from_locked_is_empty(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.LOCKED)
        assert targets == []

    def test_valid_transition(self):
        assert SessionStatus.is_valid_transition(SessionStatus.ACTIVE, SessionStatus.LOCKED) is True
        assert SessionStatus.is_valid_transition(SessionStatus.LOCKED, SessionStatus.ACTIVE) is False


class TestFieldStatus:
    def test_member_values(self):
        assert FieldStatus.UNREVIEWED.value == "unreviewed"
        assert FieldStatus.CONFIRMED.value == "confirmed"
        assert FieldStatus.MODIFIED.value == "modified"
        assert FieldStatus.SUSPICIOUS.value == "suspicious"
        assert FieldStatus.EMPTY.value == "empty"
