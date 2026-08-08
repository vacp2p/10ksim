"""Regression scenario: a degraded link (latency, jitter, packet loss)."""

import logging
from typing import ClassVar

from pydantic import Field, NonNegativeInt

from src.deployments.experiments.libp2p.nimlibp2p import ExpConfig, NimLibp2pExperiment
from src.deployments.registry import experiment

logger = logging.getLogger(__name__)


class DegradedConfig(ExpConfig):
    network_delay: NonNegativeInt = 200
    network_jitter: NonNegativeInt = 50
    network_loss_pct: float = Field(default=1, ge=0, le=100)


@experiment(name="nimlibp2p-degraded")
class DegradedNetwork(NimLibp2pExperiment):
    """Regression run over a high-latency, jittery, lossy link."""

    config: DegradedConfig
    post_run_analysis: ClassVar[str] = "src.analysis.post_run.degraded:run_degraded_analysis"
