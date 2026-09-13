"""Fair, bounded admission control for a single-slot local model service."""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass
from typing import Callable


class ModelQueueError(RuntimeError):
    """Base class for model admission failures."""


class ModelQueueFull(ModelQueueError):
    """Raised when the bounded waiting room has reached capacity."""


class ModelQueueTimeout(ModelQueueError):
    """Raised when a caller does not reach the model before its deadline."""


@dataclass(frozen=True)
class QueueSnapshot:
    active: bool
    waiting: int
    capacity: int


class ModelLease:
    """An idempotently releasable reservation for the model slot."""

    def __init__(self, queue: "FairSingleSlotQueue", ticket: int) -> None:
        self._queue = queue
        self.ticket = ticket
        self._released = False
        self._release_lock = threading.Lock()

    def release(self) -> None:
        with self._release_lock:
            if self._released:
                return
            self._released = True
        self._queue._release(self.ticket)

    def __enter__(self) -> "ModelLease":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


class FairSingleSlotQueue:
    """FIFO admission queue with bounded waiters and observable progress.

    This coordinates every Streamlit session in one application process.  A
    deployment that runs multiple web processes should replace it with a
    shared broker while keeping the same bounded/FIFO contract.
    """

    def __init__(self, *, max_waiters: int = 32, poll_interval: float = 1.0) -> None:
        if max_waiters < 1:
            raise ValueError("max_waiters must be at least 1")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        self.max_waiters = max_waiters
        self.poll_interval = poll_interval
        self._condition = threading.Condition()
        self._waiting: collections.deque[int] = collections.deque()
        self._active_ticket: int | None = None
        self._next_ticket = 1

    def snapshot(self) -> QueueSnapshot:
        with self._condition:
            return QueueSnapshot(
                active=self._active_ticket is not None,
                waiting=len(self._waiting),
                capacity=self.max_waiters,
            )

    def acquire(
        self,
        *,
        timeout: float | None = None,
        on_wait: Callable[[float, int], None] | None = None,
    ) -> ModelLease:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout

        with self._condition:
            if len(self._waiting) >= self.max_waiters:
                raise ModelQueueFull("本地教研模型排队人数已达上限，请稍后重试。")
            ticket = self._next_ticket
            self._next_ticket += 1
            self._waiting.append(ticket)

        try:
            while True:
                with self._condition:
                    if self._active_ticket is None and self._waiting[0] == ticket:
                        self._waiting.popleft()
                        self._active_ticket = ticket
                        return ModelLease(self, ticket)

                    now = time.monotonic()
                    if deadline is not None and now >= deadline:
                        raise ModelQueueTimeout("等待本地教研模型超时，请稍后重试。")
                    wait_for = self.poll_interval
                    if deadline is not None:
                        wait_for = min(wait_for, max(0.001, deadline - now))
                    position = list(self._waiting).index(ticket) + 1
                    self._condition.wait(wait_for)

                if on_wait is not None:
                    on_wait(time.monotonic() - started, position)
        except BaseException:
            with self._condition:
                try:
                    self._waiting.remove(ticket)
                except ValueError:
                    pass
                self._condition.notify_all()
            raise

    def _release(self, ticket: int) -> None:
        with self._condition:
            if self._active_ticket != ticket:
                raise ModelQueueError("attempted to release a model slot not owned by this lease")
            self._active_ticket = None
            self._condition.notify_all()
