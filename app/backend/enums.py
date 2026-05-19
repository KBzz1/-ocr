from enum import Enum


TASK_STATUS_TRANSITIONS = {
    "uploading": ["processing", "failed"],
    "processing": ["review", "failed"],
    "review": ["processing", "done", "failed"],
    "done": ["processing"],
    "failed": ["processing"],
}


class TaskStatus(Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"

    @classmethod
    def _resolve(cls, value):
        if isinstance(value, cls):
            return value
        return cls(value)

    @classmethod
    def allowed_transitions(cls, current):
        current = cls._resolve(current)
        return [cls(v) for v in TASK_STATUS_TRANSITIONS.get(current.value, [])]

    @classmethod
    def is_valid_transition(cls, current, target):
        try:
            current = cls._resolve(current)
            target = cls._resolve(target)
        except ValueError:
            return False
        return target in cls.allowed_transitions(current)


class FieldStatus(Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
