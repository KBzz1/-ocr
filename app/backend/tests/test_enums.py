import pytest

from app.backend.enums import FieldStatus, TaskStatus


def test_task_status_values_are_mvp_only():
    assert [status.value for status in TaskStatus] == [
        "uploading",
        "processing",
        "review",
        "done",
        "failed",
    ]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("uploading", "processing"),
        ("uploading", "failed"),
        ("processing", "review"),
        ("processing", "failed"),
        ("review", "processing"),
        ("review", "done"),
        ("review", "failed"),
        ("done", "processing"),
        ("failed", "processing"),
    ],
)
def test_mvp_task_status_transitions_are_allowed(current, target):
    assert TaskStatus.is_valid_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("failed", "uploading"),
        ("done", "failed"),
        ("uploading", "review"),
        ("processing", "done"),
        ("review", "uploading"),
    ],
)
def test_invalid_mvp_task_status_transitions_are_rejected(current, target):
    assert not TaskStatus.is_valid_transition(current, target)


@pytest.mark.parametrize("legacy_status", ["capturing", "uploaded", "ready_for_review", "confirmed", "exported"])
def test_legacy_task_status_values_are_rejected(legacy_status):
    with pytest.raises(ValueError):
        TaskStatus(legacy_status)


def test_field_status_values_are_mvp_only():
    assert [status.value for status in FieldStatus] == [
        "unreviewed",
        "confirmed",
        "modified",
    ]


@pytest.mark.parametrize("legacy_status", ["suspicious", "empty", "confirmed_empty"])
def test_legacy_field_status_values_are_rejected(legacy_status):
    with pytest.raises(ValueError):
        FieldStatus(legacy_status)
