from enum import Enum


TASK_STATUS_TRANSITIONS = {
    "created": ["uploading", "failed"],
    "uploading": ["uploaded", "failed"],
    "uploaded": ["processing", "failed"],
    "processing": ["ready_for_review", "failed"],
    "ready_for_review": ["confirmed", "processing", "failed"],
    "confirmed": ["exported"],
    "exported": [],
    "failed": ["processing"],
}

SESSION_STATUS_TRANSITIONS = {
    "active": ["locked", "cancelled", "expired"],
    "expired": [],
    "locked": [],
    "cancelled": [],
}


class TaskStatus(Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    EXPORTED = "exported"
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
        current = cls._resolve(current)
        target = cls._resolve(target)
        return target in cls.allowed_transitions(current)


class SessionStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LOCKED = "locked"
    CANCELLED = "cancelled"

    @classmethod
    def _resolve(cls, value):
        if isinstance(value, cls):
            return value
        return cls(value)

    @classmethod
    def allowed_transitions(cls, current):
        current = cls._resolve(current)
        return [cls(v) for v in SESSION_STATUS_TRANSITIONS.get(current.value, [])]

    @classmethod
    def is_valid_transition(cls, current, target):
        current = cls._resolve(current)
        target = cls._resolve(target)
        return target in cls.allowed_transitions(current)


class FieldStatus(Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    SUSPICIOUS = "suspicious"
    EMPTY = "empty"
