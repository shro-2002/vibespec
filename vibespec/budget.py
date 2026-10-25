"""Process-local daily Qloo call budget with reservations.

Two numbers are kept apart: `dispatched` (HTTP requests actually sent to Qloo today, retries included) and `reserved`
(headroom held by runs still in progress). A run takes a Lease, spends from it, and closes it exactly once with what it
really used; the unused remainder returns to the pool.

LIMITS: the counter lives in this process. A restart or redeploy resets it, and it knows nothing about Qloo's real quota
or other clients using the same key. It protects the key from this app's own traffic; it is not durable quota protection.
"""
from __future__ import annotations

import threading
import time
from typing import Callable


def _today() -> str:
    return time.strftime("%Y-%m-%d")


class Lease:
    def __init__(self, owner: "DailyBudget", grant: int, day: str):
        self._owner, self.grant, self.day, self._open = owner, grant, day, True

    def close(self, used: int) -> bool:
        """Release the lease. Idempotent: only the first call has any effect. Returns True if it did."""
        return self._owner._release(self, used)


class DailyBudget:
    def __init__(self, cap: int, per_run: int, today: Callable[[], str] = _today):
        self.cap, self.per_run, self._today = max(cap, 0), max(per_run, 0), today
        self._lock = threading.Lock()
        self._day, self.dispatched, self.reserved = today(), 0, 0

    def _roll(self) -> None:
        if self._day != self._today():
            self._day, self.dispatched = self._today(), 0  # outstanding reservations carry over until their runs close

    def reserve(self) -> Lease:
        """Hold up to per_run calls for one run. The grant is 0 when the day's budget is spent: such a run can still be
        answered from the private cache (cache hits cost nothing) but cannot dispatch to Qloo."""
        with self._lock:
            self._roll()
            grant = max(0, min(self.per_run, self.cap - self.dispatched - self.reserved))
            self.reserved += grant
            return Lease(self, grant, self._day)

    def _release(self, lease: Lease, used: int) -> bool:
        with self._lock:
            if not lease._open:
                return False
            lease._open = False
            self.reserved = max(0, self.reserved - lease.grant)
            self._roll()
            if lease.day == self._day:  # usage from a previous day does not count against today
                self.dispatched += min(max(int(used), 0), lease.grant)
            return True

    def snapshot(self) -> dict:
        with self._lock:
            self._roll()
            return {"day": self._day, "cap": self.cap, "dispatched": self.dispatched, "reserved": self.reserved,
                    "available": max(0, self.cap - self.dispatched - self.reserved), "scope": "this process only; resets on restart"}
