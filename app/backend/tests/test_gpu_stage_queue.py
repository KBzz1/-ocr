import threading
import time

from app.backend.services.gpu_stage_queue import GpuStageQueue


def test_gpu_stage_queue_emits_events_for_single_stage():
    events = []
    queue = GpuStageQueue(event_logger=lambda event, **payload: events.append((event, payload)))

    with queue.stage(task_id="task-001", stage="document_parsing"):
        pass

    assert [event for event, _payload in events] == [
        "gpu_stage_waiting",
        "gpu_stage_started",
        "gpu_stage_finished",
    ]
    assert events[0][1]["task_id"] == "task-001"
    assert events[0][1]["stage"] == "document_parsing"
    assert events[2][1]["status"] == "success"


def test_gpu_stage_queue_serializes_threads():
    queue = GpuStageQueue()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def run_stage(task_id):
        nonlocal active, max_active
        with queue.stage(task_id=task_id, stage="field_extraction"):
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    threads = [threading.Thread(target=run_stage, args=(f"task-{idx}",)) for idx in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_gpu_stage_queue_marks_exception_status():
    events = []
    queue = GpuStageQueue(event_logger=lambda event, **payload: events.append((event, payload)))

    try:
        with queue.stage(task_id="task-001", stage="document_parsing"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert events[-1][0] == "gpu_stage_finished"
    assert events[-1][1]["status"] == "error"
