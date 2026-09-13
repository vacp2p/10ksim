import pytest

from src.deployments.experiments.libp2p import nimlibp2p
from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, publish
from src.deployments.pod_api_requester.pod_api_requester import (
    PodApiApplicationError,
    PodApiClientError,
)


@pytest.mark.asyncio
async def test_a_delivered_publish_reports_success(mocker):
    mocker.patch.object(nimlibp2p, "libp2p_dst_node_publish", return_value=None)
    assert await publish(ExpConfig(), "ns", "pod-0") is True


@pytest.mark.parametrize(
    "error",
    [PodApiClientError("timed out"), PodApiApplicationError("node said no"), RuntimeError("boom")],
)
@pytest.mark.asyncio
async def test_a_lost_publish_is_reported_not_swallowed(mocker, error):
    """Every failure used to be logged and discarded, so the count came out right anyway."""
    mocker.patch.object(nimlibp2p, "libp2p_dst_node_publish", side_effect=error)
    assert await publish(ExpConfig(), "ns", "pod-0") is False


def test_no_publish_may_fail_by_default():
    assert ExpConfig().max_failed_publishes == 0


def test_the_tolerance_can_be_raised_for_a_run_that_expects_losses():
    assert ExpConfig(max_failed_publishes=10).max_failed_publishes == 10
