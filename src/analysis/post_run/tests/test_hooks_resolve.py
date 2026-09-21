"""The suite otherwise never imports the scenario experiments, so a broken one stays green."""

import pytest

from src.analysis.post_run_analysis import load_post_run_analysis
from src.deployments.experiments.libp2p.churn import NodeChurn
from src.deployments.experiments.libp2p.degraded import DegradedNetwork
from src.deployments.experiments.libp2p.partition import NetworkPartition

SCENARIOS = [DegradedNetwork, NodeChurn, NetworkPartition]


@pytest.mark.parametrize("experiment", SCENARIOS, ids=lambda c: c.__name__)
def test_scenario_declares_a_resolvable_post_run_analysis(experiment):
    assert callable(load_post_run_analysis(experiment.post_run_analysis))


@pytest.mark.parametrize("experiment", SCENARIOS, ids=lambda c: c.__name__)
def test_post_run_analysis_stays_out_of_the_model_fields(experiment):
    """A ClassVar, or it would be serialized into the run metadata and break the reload."""
    assert "post_run_analysis" not in experiment.model_fields
