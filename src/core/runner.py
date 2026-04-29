from __future__ import annotations

from collections.abc import Callable
from queue import Queue
from threading import Event, Lock, Thread

from core.logger import get_logger


TaskCallback = Callable[[str, str], None]
TaskCallable = Callable[[], None]


class TaskRunner:
    def __init__(self) -> None:
        self._queue: Queue[tuple[str, TaskCallable]] = Queue()
        self._callbacks: list[TaskCallback] = []
        self._callbacks_lock = Lock()
        self._stop_event = Event()
        self._logger = get_logger("task_runner")
        self._worker = Thread(target=self._run_forever, name="task-runner", daemon=True)
        self._worker.start()

    def register_callback(self, callback: TaskCallback) -> None:
        with self._callbacks_lock:
            self._callbacks.append(callback)

    def submit(self, task_id: str, task: TaskCallable) -> None:
        self._queue.put((task_id, task))
        self._notify(task_id, "queued")

    def shutdown(self) -> None:
        self._stop_event.set()
        self._queue.put(("__shutdown__", lambda: None))
        self._worker.join(timeout=1)

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            task_id, task = self._queue.get()

            if task_id == "__shutdown__":
                return

            self._notify(task_id, "running")
            try:
                task()
            except Exception as error:
                self._logger.exception("Task %s failed: %s", task_id, error)
                self._notify(task_id, "failed")
            else:
                self._notify(task_id, "completed")

    def _notify(self, task_id: str, status: str) -> None:
        with self._callbacks_lock:
            callbacks = list(self._callbacks)

        for callback in callbacks:
            callback(task_id, status)