from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import signature
from queue import Queue
from threading import Event, Lock, Thread
from typing import cast

from core.logger import get_logger
from tests.base_strategy import BaseEvalStrategy, EvalResult


TaskCallback = Callable[..., None]
TaskCallable = Callable[[], None]
FinalTaskStatus = frozenset({"completed", "failed", "cancelled"})
TransientResultStatus = frozenset({"idle", "prepared", "queued", "preparing", "running"})


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: str
    strategy_name: str
    status: str
    result: EvalResult | None = None
    error_message: str | None = None


class TaskRunner:
    def __init__(self) -> None:
        self._queue: Queue[tuple[str, str, object]] = Queue()
        self._callbacks: list[TaskCallback] = []
        self._callbacks_lock = Lock()
        self._state_lock = Lock()
        self._stop_event = Event()
        self._task_events: dict[str, Event] = {}
        self._task_snapshots: dict[str, TaskSnapshot] = {}
        self._logger = get_logger("task_runner")
        self._worker = Thread(target=self._run_forever, name="task-runner", daemon=True)
        self._worker.start()

    def register_callback(self, callback: TaskCallback) -> None:
        with self._callbacks_lock:
            self._callbacks.append(callback)

    def submit(self, task_id: str, task: TaskCallable) -> None:
        self._track_task(task_id=task_id, strategy_name="callable")
        self._queue.put(("callable", task_id, task))

    def submit_strategy(self, task_id: str, strategy: BaseEvalStrategy) -> None:
        self._track_task(task_id=task_id, strategy_name=type(strategy).__name__)
        self._queue.put(("strategy", task_id, strategy))

    def wait_for_task(self, task_id: str, timeout: float | None = None) -> bool:
        with self._state_lock:
            task_event = self._task_events.get(task_id)

        if task_event is None:
            return False

        return task_event.wait(timeout=timeout)

    def get_task_snapshot(self, task_id: str) -> TaskSnapshot | None:
        with self._state_lock:
            return self._task_snapshots.get(task_id)

    def shutdown(self) -> None:
        self._stop_event.set()
        self._queue.put(("shutdown", "__shutdown__", lambda: None))
        self._worker.join(timeout=1)

    def _run_forever(self) -> None:
        while not self._stop_event.is_set():
            task_kind, task_id, task_payload = self._queue.get()

            if task_id == "__shutdown__":
                return

            if task_kind == "strategy":
                self._run_strategy(task_id, cast(BaseEvalStrategy, task_payload))
                continue

            self._run_callable(task_id, cast(TaskCallable, task_payload))

    def _run_callable(self, task_id: str, task: TaskCallable) -> None:
        self._notify(task_id, "running")
        try:
            task()
        except Exception as error:
            self._logger.exception("Task %s failed: %s", task_id, error)
            self._finalize_task(
                task_id=task_id,
                status="failed",
                result=EvalResult(status="failed", error_message=str(error)),
                error_message=str(error),
            )
        else:
            self._finalize_task(
                task_id=task_id,
                status="completed",
                result=EvalResult(status="completed"),
                error_message=None,
            )

    def _run_strategy(self, task_id: str, strategy: BaseEvalStrategy) -> None:
        if strategy.is_cancelled:
            self._finalize_task(
                task_id=task_id,
                status="cancelled",
                result=strategy.get_results(),
                error_message=None,
            )
            return

        try:
            self._notify(task_id, "preparing")
            strategy.prepare()

            if strategy.is_cancelled:
                self._finalize_task(
                    task_id=task_id,
                    status="cancelled",
                    result=strategy.get_results(),
                    error_message=None,
                )
                return

            self._notify(task_id, "running")
            strategy.execute()
        except Exception as error:
            self._logger.exception("Task %s failed: %s", task_id, error)
            failure_result = EvalResult(status="failed", error_message=str(error))
            strategy.set_result(failure_result)
            self._finalize_task(
                task_id=task_id,
                status="failed",
                result=failure_result,
                error_message=str(error),
            )
            return

        result = strategy.get_results()
        if strategy.is_cancelled:
            result = EvalResult(status="cancelled")
        elif result.status in TransientResultStatus:
            result = result.with_status("completed")
            strategy.set_result(result)

        self._finalize_task(
            task_id=task_id,
            status=result.status,
            result=result,
            error_message=result.error_message,
        )

    def _track_task(self, task_id: str, strategy_name: str) -> None:
        with self._state_lock:
            self._task_events[task_id] = Event()
            self._task_snapshots[task_id] = TaskSnapshot(
                task_id=task_id,
                strategy_name=strategy_name,
                status="queued",
            )

        self._notify(task_id, "queued")

    def _finalize_task(
        self,
        task_id: str,
        status: str,
        result: EvalResult | None,
        error_message: str | None,
    ) -> None:
        self._notify(task_id, status, result=result, error_message=error_message)

    def _notify(
        self,
        task_id: str,
        status: str,
        result: EvalResult | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._state_lock:
            previous_snapshot = self._task_snapshots.get(task_id)
            strategy_name = "unknown" if previous_snapshot is None else previous_snapshot.strategy_name
            snapshot = TaskSnapshot(
                task_id=task_id,
                strategy_name=strategy_name,
                status=status,
                result=result,
                error_message=error_message,
            )
            self._task_snapshots[task_id] = snapshot
            task_event = self._task_events.get(task_id)

        with self._callbacks_lock:
            callbacks = list(self._callbacks)

        if task_event is not None and status in FinalTaskStatus:
            task_event.set()

        for callback in callbacks:
            parameter_count = len(signature(callback).parameters)
            if parameter_count <= 1:
                callback(snapshot)
                continue

            callback(task_id, status)