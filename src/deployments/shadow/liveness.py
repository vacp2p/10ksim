"""Detect a Shadow run whose simulated clock has stopped.

Shadow prints progress and we leave `progress: True` on, but nothing reads it, so a
livelocked run is indistinguishable from a slow one until the job timeout fires hours
later. Watching simulated time turns that into a fast, specific failure.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# "Progress: 49% - simulated: 00:09:52.847/00:20:00, realtime: 00:57:00, ..."
_PROGRESS = re.compile(r"Progress:.*?simulated:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
# Fallback: every worker line carries the simulated time as its third field.
_WORKER = re.compile(r"^[\d:.]+\s+\[\d+:[^\]]+\]\s+(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", re.MULTILINE)


def simulated_time_s(log_text: str) -> Optional[float]:
    """Latest simulated time in the log, or None if it has not started yet."""
    for pattern in (_PROGRESS, _WORKER):
        matches = pattern.findall(log_text)
        if matches:
            h, m, s = matches[-1]
            return int(h) * 3600 + int(m) * 60 + float(s)
    return None


class StallWatch:
    """Raises once simulated time has failed to advance for `stall_timeout_s`."""

    def __init__(self, *, stall_timeout_s: int = 600, startup_grace_s: int = 900):
        self.stall_timeout_s = stall_timeout_s
        self.startup_grace_s = startup_grace_s
        self._last_sim: Optional[float] = None
        self._last_change_at: Optional[float] = None

    def check(self, sim_time: Optional[float], now: float) -> None:
        """Feed the current simulated time and wall-clock reading."""
        if self._last_change_at is None:
            self._last_change_at = now

        if sim_time is None:
            # Only a signal before the clock has ever been seen, since Shadow builds the
            # network first. After that, no reading means an unreadable log, not a stall,
            # so leave the stall clock where it was.
            if self._last_sim is None and now - self._last_change_at > self.startup_grace_s:
                raise RuntimeError(
                    f"Shadow reported no simulated time in {self.startup_grace_s}s; "
                    "the run is stuck before the simulation started"
                )
            return

        if self._last_sim is None or sim_time > self._last_sim:
            self._last_sim, self._last_change_at = sim_time, now
            return

        stalled = now - self._last_change_at
        if stalled > self.stall_timeout_s:
            raise RuntimeError(
                f"Shadow simulated time stuck at {sim_time:.3f}s for {stalled:.0f}s; "
                "the run is livelocked, not slow"
            )
