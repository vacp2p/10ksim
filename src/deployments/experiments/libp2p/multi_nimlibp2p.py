from typing import Any, Iterable, List, Optional

from pydantic import BaseModel

from src.deployments.core.configs.container import Image
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.registry import experiment


def shallow_merge(a: BaseModel, b: BaseModel):
    data = {**a.model_dump(), **b.model_dump()}
    return a.__class__.model_validate(data)


@experiment(name="multi_nimlibp2p")
class MultiNimlibp2p(Multiple):
    experiment_name: Optional[str] = NimLibp2pExperiment.name

    def model_post_init(self, __context: Any) -> None:
        self.delay_between_exps = 6 * 60
        super().model_post_init(__context)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run nimlibp2p multiple times with different parameters."
        )
        Multiple.add_args(subparser)
        BaseExperiment.add_args(subparser)

    def get_params_paths(self) -> Optional[dict]:
        """Return dict mapping keys to values.yaml paths"""
        return None

    def exp_params(self) -> Iterable[dict]:
        images = {
            "1.16.0": Image(
                repo="pearsonwhite/dst-nimlibp2p-logging",
                tag="wip-4.1-1.16.0",
            ),
            "1.15.0": Image(
                repo="pearsonwhite/dst-nimlibp2p-logging",
                tag="wip-5-v1.15.0",
            ),
        }
        base = {
            "delay_after_publish": 1,
            "delay_cold_start": 2 * 60,
            "message_size_bytes": 1000,  # 1kb
            "num_messages": 1000,
            "node_start_delay": 5 * 60,  # 5 min,
        }
        version = "1.16.0"
        base["image"] = images[version]
        base["version"] = version

        yield {
            **base,
            "muxer": "yamux",
            "num_nodes": 1000,
            "connect_to": 10,
        }
        yield {
            **base,
            "muxer": "quic",
            "num_nodes": 1000,
            "connect_to": 10,
        }

    def get_params_list(self) -> List[dict]:
        return [item for item in self.exp_params()]

    def get_name_from_params(self, params: dict) -> str:
        version = params["version"]
        keys = ["num_nodes", "num_messages"]
        used_keys = filter(lambda item: item in keys, params.items())
        param_list = [f"{key}_{value}" for key, value in used_keys]
        param_list.append(f"version_{version}")
        return "__".join(param_list)
