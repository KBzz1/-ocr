"""Per-task reextract job registry used for in-flight cancellation.

The reextract endpoint runs the LLM synchronously inside the Flask request
thread. The frontend aborts the HTTP fetch on 取消, but the LLM call itself
has no native cancellation hook in llama-cpp-python's high-level API, so the
GPU keeps running for the duration of the in-flight completion. To cut
that tail off at the next section-group boundary we keep a small
per-task threading.Event that the reextract service checks between LLM
calls. A second HTTP endpoint (POST /api/tasks/<id>/cancel-reextract)
flips the event from the request that handled 取消, so the user-visible
"GPU keeps running" window shrinks from minutes to ~one LLM call.
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
