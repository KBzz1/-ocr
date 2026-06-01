import threading
import time
from contextlib import contextmanager
from typing import Callable


class GpuStageQueue:
    def __init__(self, event_logger: Callable[..., None] | None = None, enabled: bool = True):
        self._event_logger = event_logger
        self._enabled = enabled
        self._lock = threading.Lock()

    @contextmanager
    def stage(self, task_id: str, stage: str):
        if not self._enabled:
            yield
            return

        waiting_started = time.monotonic()
        self._emit("gpu_stage_waiting", task_id=task_id, stage=stage)
        self._lock.acquire()
        stage_started = time.monotonic()
        self._emit(
            "gpu_stage_started",
            task_id=task_id,
            stage=stage,
            wait_ms=int((stage_started - waiting_started) * 1000),
        )
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            elapsed_ms = int((time.monotonic() - stage_started) * 1000)
            self._lock.release()
            self._emit(
                "gpu_stage_finished",
                task_id=task_id,
                stage=stage,
                elapsed_ms=elapsed_ms,
                status=status,
            )

    def _emit(self, event: str, **payload) -> None:
        if self._event_logger is not None:
            self._event_logger(event, **payload)
