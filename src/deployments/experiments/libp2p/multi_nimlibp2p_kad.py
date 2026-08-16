import os
from typing import Iterable, List, Optional

from src.deployments.core.configs.container import Image
from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment

# nim-libp2p regression matrix: each version x muxer is one full kad-dht run.
# The sweep is env-configurable so the same experiment drives a smoke test, a
# single-version pass (runs are sequential to keep measurements clean), or the
# full matrix -- see REGRESSION_* below.
IMAGES = {
    "2.0.0": Image(repo="radiken/dst-test-node-regression", tag="v2.0.0-kad"),
    "2.1.0": Image(repo="radiken/dst-test-node-regression", tag="v2.1.0-kad"),
    "2.2.0": Image(repo="radiken/dst-test-node-regression", tag="v2.2.0"),
    # v2.2.0 with ping-all keepalive, the config-parity baseline (same build as the quic rerun).
    "2.2.0-keepalive": Image(repo="radiken/dst-test-node-regression", tag="v2.2.0-pingall3"),
    "2.3.0": Image(repo="radiken/dst-test-node-regression", tag="v2.3.0-2"),
    # Same build plus -d:chronosFutureTracking, for diagnosing the kad bootstrap stall.
    "2.3.0-futures": Image(repo="radiken/dst-test-node-regression", tag="v2.3.0-futures"),
    # release/v2.3 plus PR 2929, which landed on master only.
    "2.3.0-2929": Image(repo="radiken/dst-test-node-regression", tag="v2.3.0-2929"),
    # ...and the node listening on its routable interface rather than 0.0.0.0.
    "2.3.0-noloop": Image(repo="radiken/dst-test-node-regression", tag="v2.3.0-2929-noloop"),
    # ...and optimistic kad admission while the routing table is small.
    "2.3.0-kadfix": Image(repo="radiken/dst-test-node-regression", tag="v2.3.0-kadfix"),
    # 0eb435f8, the commit p2p gave us, plus notice-level admission probe logging.
    "2.3.0-diag": Image(
        repo="radiken/dst-test-node-regression", tag="v2.3.0-0eb435f8-diag"
    ),
    # d7ba9db1, their PR 2936 probe-timeout fix, same logging.
    "2.3.0-diag2": Image(
        repo="radiken/dst-test-node-regression", tag="v2.3.0-d7ba9db1-diag"
    ),
    # ...plus optimistic admission while the routing table is below replication.
    "2.3.0-coldstart": Image(
        repo="radiken/dst-test-node-regression", tag="v2.3.0-coldstart"
    ),
}


def _env_list(name: str, default: str) -> list:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


VERSIONS = _env_list("REGRESSION_VERSIONS", "2.1.0,2.0.0")
MUXERS = _env_list("REGRESSION_MUXERS", "mplex,yamux,quic")
MESSAGE_SIZES = [int(x) for x in _env_list("REGRESSION_SIZES", "1000")]
NUM_NODES = int(os.environ.get("REGRESSION_NUM_NODES", "1000"))
NUM_MESSAGES = int(os.environ.get("REGRESSION_NUM_MESSAGES", "600"))
# delay_cold_start is how long we wait after the nodes are deployed (their start
# delay + kad-dht mesh formation) before the publisher fires; shorten it via the
# env var for small smoke runs.
COLD_START = int(os.environ.get("REGRESSION_COLD_START", str(7 * 60)))


@experiment(name="multi_nimlibp2p_kad")
class MultiNimlibp2pKad(Multiple):
    """nim-libp2p regression sweep: kad-dht, version x muxer."""

    def model_post_init(self, __context) -> None:
        self.config.name = NimLibp2pExperiment.name
        super().model_post_init(__context)

    def get_params_paths(self) -> Optional[dict]:
        return None

    def exp_params(self) -> Iterable[dict]:
        base = {
            "discovery": "kad-dht",
            "bootstrap_nodes": 1,
            "num_relay_nodes": NUM_NODES,
            "num_messages": NUM_MESSAGES,
            "delay_after_publish": 1,  # 1 msg/s
            "delay_cold_start": COLD_START,
            "node_start_delay": 5 * 60,
        }
        for version in VERSIONS:
            for size in MESSAGE_SIZES:
                for muxer in MUXERS:
                    yield {
                        **base,
                        "image": IMAGES[version],
                        "version": version,
                        "muxer": muxer,
                        "message_size_bytes": size,
                    }

    def get_params_list(self) -> List[dict]:
        return list(self.exp_params())

    def get_name_from_params(self, params: dict) -> str:
        return (
            f"version_{params['version']}"
            f"__muxer_{params['muxer']}"
            f"__size_{params['message_size_bytes']}"
            f"__nodes_{params['num_relay_nodes']}"
        )
