# Drives shadow-gossipsub at multiple scales via the Multiple meta-experiment.
# Run with: uv run python deployment.py multi-shadow-gossipsub --skip-check
from typing import Any, Iterable, List, Optional

from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.experiments.libp2p.shadow_gossipsub import ShadowGossipsubExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment


@experiment(name="multi-shadow-gossipsub")
class MultiShadowGossipsub(Multiple):
    experiment_name: Optional[str] = ShadowGossipsubExperiment.name

    def model_post_init(self, __context: Any) -> None:
        # Shadow runs finish in seconds wall clock, so we don't need the long
        # default between iterations. Bump if a sim leaves cluster state behind.
        self.delay_between_exps = 60
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run shadow-gossipsub multiple times at different scales."
        )
        BaseExperiment.add_args(subparser)
        subparser.set_defaults(namespace="zerotesting-shadow")

    def get_params_list(self) -> List[dict]:
        return list(self.exp_params())

    def exp_params(self) -> Iterable[dict]:
        for num_nodes in (10, 30, 100):
            yield {"num_nodes": num_nodes}

    def get_name_from_params(self, params: dict) -> str:
        return f"num_nodes_{params['num_nodes']}"
