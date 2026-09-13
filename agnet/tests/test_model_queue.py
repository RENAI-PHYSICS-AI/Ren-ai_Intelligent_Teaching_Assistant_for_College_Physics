from __future__ import annotations

import threading
import time
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from model_queue import FairSingleSlotQueue, ModelQueueFull, ModelQueueTimeout


def _wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached before timeout")


def test_queue_admits_waiters_in_fifo_order() -> None:
    queue = FairSingleSlotQueue(max_waiters=4, poll_interval=0.01)
    first = queue.acquire()
    order: list[int] = []
    errors: list[BaseException] = []
    threads: list[threading.Thread] = []

    def worker(number: int) -> None:
        try:
            with queue.acquire(timeout=1):
                order.append(number)
                time.sleep(0.01)
        except BaseException as exc:  # surface worker failures in the test thread
            errors.append(exc)

    for number in range(3):
        thread = threading.Thread(target=worker, args=(number,))
        thread.start()
        threads.append(thread)
        _wait_until(lambda expected=number + 1: queue.snapshot().waiting == expected)

    first.release()
    for thread in threads:
        thread.join(timeout=1)
        assert not thread.is_alive()
    assert errors == []
    assert order == [0, 1, 2]
    assert queue.snapshot().active is False


def test_timeout_removes_waiter() -> None:
    queue = FairSingleSlotQueue(max_waiters=1, poll_interval=0.005)
    lease = queue.acquire()
    with pytest.raises(ModelQueueTimeout):
        queue.acquire(timeout=0.02)
    assert queue.snapshot().waiting == 0
    lease.release()


def test_waiting_room_is_bounded() -> None:
    queue = FairSingleSlotQueue(max_waiters=1, poll_interval=0.01)
    lease = queue.acquire()
    blocker = threading.Event()
    errors: list[BaseException] = []

    def wait_for_slot() -> None:
        try:
            with queue.acquire(timeout=1):
                pass
        except BaseException as exc:
            errors.append(exc)
        finally:
            blocker.set()

    thread = threading.Thread(target=wait_for_slot)
    thread.start()
    _wait_until(lambda: queue.snapshot().waiting == 1)
    with pytest.raises(ModelQueueFull):
        queue.acquire(timeout=0.1)
    lease.release()
    blocker.wait(1)
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert errors == []


def test_lease_release_is_idempotent() -> None:
    queue = FairSingleSlotQueue()
    lease = queue.acquire()
    lease.release()
    lease.release()
    assert queue.snapshot().active is False
