"""Per-task reextract job registry used for in-flight cancellation.

The reextract endpoint can run model-backed work synchronously inside the
Flask request thread. The frontend aborts the HTTP fetch on 取消, but an
in-flight model call may not stop immediately, so the GPU can keep running
until the current call returns. A small per-task threading.Event lets the
reextract service stop at the next safe boundary. A second HTTP endpoint
(POST /api/tasks/<id>/cancel-reextract) flips the event from the request that
handled 取消, so the user-visible "GPU keeps running" window shrinks from
minutes to roughly one model call.
"""

from threading import Event, Lock
from typing import Dict, Optional


class ReextractJobRegistry:
    """In-memory registry of in-flight reextract jobs keyed by task_id.

    The registry is intentionally tiny: one Event per active job, no
    persistence. On service restart any in-flight job is already gone, and
    the registry simply starts empty. Only one reextract per task_id is
    supported at a time; if a second request arrives it is rejected by the
    route layer (status check), so we don't need to model queued jobs.
    """

    def __init__(self) -> None:
        self._events: Dict[str, Event] = {}
        self._lock = Lock()

    def register(self, task_id: str) -> Event:
        with self._lock:
            event = self._events.get(task_id)
            if event is None:
                event = Event()
                self._events[task_id] = event
            return event

    def unregister(self, task_id: str) -> None:
        with self._lock:
            self._events.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            event = self._events.get(task_id)
            if event is None:
                return False
            event.set()
            return True

    def get(self, task_id: str) -> Optional[Event]:
        with self._lock:
            return self._events.get(task_id)
