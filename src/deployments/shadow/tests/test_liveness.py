import pytest

from src.deployments.shadow.liveness import StallWatch, simulated_time_s

PROGRESS = (
    "Progress: 49% — simulated: 00:09:52.847/00:20:00, realtime: 00:57:00, processes failed: 0"
)
WORKER = (
    "00:57:50.361079 [114:shadow-worker] 00:10:06.976000000 [WARN] "
    "[pod-31:11.100.31.10] [regular_file.c:393] [regularfile_op] something"
)


def test_reads_the_progress_line():
    assert simulated_time_s(PROGRESS) == pytest.approx(592.847)


def test_falls_back_to_worker_lines_when_progress_is_off():
    assert simulated_time_s(WORKER) == pytest.approx(606.976)


def test_prefers_the_progress_line_over_worker_lines():
    assert simulated_time_s(f"{WORKER}\n{PROGRESS}") == pytest.approx(592.847)


def test_takes_the_latest_of_several():
    later = PROGRESS.replace("00:09:52.847", "00:11:00.000")
    assert simulated_time_s(f"{PROGRESS}\n{later}") == pytest.approx(660.0)


def test_none_before_the_clock_starts():
    assert simulated_time_s("shadow starting up\nparsing config\n") is None


def test_advancing_time_never_raises():
    watch = StallWatch(stall_timeout_s=100)
    for i in range(20):
        watch.check(float(i), i * 60.0)


def test_stalled_time_raises_once_past_the_timeout():
    watch = StallWatch(stall_timeout_s=100)
    watch.check(500.0, 0.0)
    watch.check(500.0, 99.0)  # still inside the allowance
    with pytest.raises(RuntimeError, match="livelocked, not slow"):
        watch.check(500.0, 101.0)


def test_recovery_resets_the_clock():
    """A slow but advancing run must not trip the check."""
    watch = StallWatch(stall_timeout_s=100)
    watch.check(500.0, 0.0)
    watch.check(500.0, 90.0)
    watch.check(501.0, 95.0)  # advanced, so the allowance restarts
    watch.check(501.0, 180.0)


def test_never_starting_raises_after_the_grace_period():
    watch = StallWatch(stall_timeout_s=100, startup_grace_s=300)
    watch.check(None, 0.0)
    watch.check(None, 299.0)
    with pytest.raises(RuntimeError, match="no simulated time"):
        watch.check(None, 301.0)


def test_unreadable_logs_do_not_trip_it_once_running():
    """A transient log-read failure returns None; that must not look like a stall."""
    watch = StallWatch(stall_timeout_s=100, startup_grace_s=300)
    watch.check(500.0, 0.0)
    watch.check(None, 50.0)
    watch.check(501.0, 60.0)


def test_an_extended_read_outage_does_not_kill_a_running_sim():
    """An API outage longer than the startup grace is still not a startup failure."""
    watch = StallWatch(stall_timeout_s=100, startup_grace_s=300)
    watch.check(500.0, 0.0)
    watch.check(None, 400.0)
    watch.check(None, 900.0)
    watch.check(501.0, 950.0)


def test_a_stall_is_still_caught_after_a_read_outage():
    """Unreadable samples must not forgive a stall either: the clock keeps its value."""
    watch = StallWatch(stall_timeout_s=100, startup_grace_s=300)
    watch.check(500.0, 0.0)
    watch.check(None, 400.0)
    with pytest.raises(RuntimeError, match="livelocked, not slow"):
        watch.check(500.0, 500.0)


def test_default_timeout_tolerates_the_observed_progress_rate():
    """The 50KB quic cell emits a progress line about every two minutes, so the default
    allowance has to sit well above that or a healthy heavy run gets killed."""
    from src.deployments.shadow.runtime import wait_for_job_complete

    default = wait_for_job_complete.__kwdefaults__["stall_timeout_s"]
    assert default >= 600, "a livelock should still be caught well inside the job timeout"
    assert default >= 6 * 120, "must survive several progress intervals on the slowest cell"
