from typing import Iterable, List, Optional

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment

# nim-libp2p regression matrix: each version x muxer is one full kad-dht run.
IMAGES = {
    "2.0.0": Image(repo="radiken/dst-test-node-regression", tag="v2.0.0-kad"),
    "2.1.0": Image(repo="radiken/dst-test-node-regression", tag="v2.1.0-kad"),
}
VERSIONS = ["2.1.0", "2.0.0"]
MUXERS = ["mplex", "yamux", "quic"]
MESSAGE_SIZES = [1000]  # add 50_000 for the 50KB sweep


@experiment(name="multi_nimlibp2p_kad")
class MultiNimlibp2pKad(Multiple):
    def model_post_init(self, __context) -> None:
        self.config.name = NimLibp2pExperiment.name
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="nim-libp2p regression sweep: kad-dht, version x muxer."
        )
        Multiple.add_args(subparser)
        BaseExperiment.add_args(subparser)

    def get_params_paths(self) -> Optional[dict]:
        return None

    def exp_params(self) -> Iterable[dict]:
        # Match the v2.0.0 regression config: 1000 nodes, 600 msgs @ 1/s.
        # delay_cold_start covers the node STARTSLEEP (180s) + kad-dht mesh formation
        # before the publisher starts.
        base = {
            "discovery": "kad-dht",
            "bootstrap_nodes": 1,
            "num_nodes": 1000,
            "num_messages": 600,
            "delay_after_publish": 1,  # 1 msg/s
            "delay_cold_start": 7 * 60,
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
            f"__nodes_{params['num_nodes']}"
        )
