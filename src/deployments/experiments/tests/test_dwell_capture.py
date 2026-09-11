import asyncio

import pytest
from kubernetes.client import ApiClient

from src.deployments.experiments.libp2p import nimlibp2p
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment

CAPTURE_SECONDS = 30


def _experiment(tmp_path, **config):
    exp = NimLibp2pExperiment(
        api_client=ApiClient(),
        config=ExpConfig(**config),
        namespace="ns",
        output_folder=tmp_path / "run",
    )
    exp.events_log_path = tmp_path / "events.log"
    return exp


class Clock:
    """Fake clock so sleeps and the capture cost time without the test waiting."""

    def __init__(self):
        self.now = 0.0
        self.events = []

    async def sleep(self, seconds):
        self.events.append(("sleep", seconds))
        self.now += seconds

    def capture(self, *_, **__):
        self.events.append(("capture", CAPTURE_SECONDS))
        self.now += CAPTURE_SECONDS
        return 7

    def monotonic(self):
        return self.now

    @property
    def kinds(self):
        return [kind for kind, _ in self.events]


@pytest.fixture
def clock(mocker):
    fake = Clock()
    mocker.patch.object(asyncio, "sleep", fake.sleep)
    mocker.patch.object(nimlibp2p, "capture_pod_logs", fake.capture)
    mocker.patch.object(nimlibp2p.time, "monotonic", fake.monotonic)
    return fake


@pytest.mark.asyncio
async def test_the_capture_lands_inside_the_dwell_not_after_it(tmp_path, clock):
    """Cleanup starts the second the dwell ends, and 1000 logs take longer than that."""
    await _experiment(tmp_path, post_publish_dwell=90, log_capture_lead=45)._dwell_and_capture()

    assert clock.kinds == ["sleep", "capture", "sleep"]
    assert clock.events[0] == ("sleep", 45)


@pytest.mark.asyncio
async def test_the_dwell_is_not_extended_by_the_capture(tmp_path, clock):
    await _experiment(tmp_path, post_publish_dwell=90, log_capture_lead=45)._dwell_and_capture()
    assert clock.now == 90


@pytest.mark.asyncio
async def test_a_slow_capture_does_not_shorten_the_dwell(tmp_path, clock):
    """If the capture overruns its lead the dwell is already satisfied, not run negative."""
    await _experiment(tmp_path, post_publish_dwell=40, log_capture_lead=20)._dwell_and_capture()
    assert clock.now >= 40
    assert all(seconds >= 0 for kind, seconds in clock.events if kind == "sleep")


@pytest.mark.asyncio
async def test_capture_can_be_turned_off(tmp_path, clock):
    exp = _experiment(tmp_path, post_publish_dwell=90, capture_pod_logs=False)
    await exp._dwell_and_capture()
    assert clock.events == [("sleep", 90)]


@pytest.mark.asyncio
async def test_a_lead_longer_than_the_dwell_does_not_sleep_negative(tmp_path, clock):
    await _experiment(tmp_path, post_publish_dwell=30, log_capture_lead=45)._dwell_and_capture()
    assert clock.events[0] == ("sleep", 0)
    assert all(seconds >= 0 for kind, seconds in clock.events if kind == "sleep")
